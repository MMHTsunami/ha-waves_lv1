"""LV1Coordinator: owns the TCP connection, decodes `/Notify/...` into state, and
pushes updates out via Home Assistant's dispatcher.

Ported from the state-handling half of `main.ts` (the `InstanceBase` lifecycle
and `handleNotify`). Per the project's push-based architecture, this is a plain
state manager rather than a polling `DataUpdateCoordinator` — the LV1 tells us
about every change (from any client) unprompted, so there is nothing to poll.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONSECUTIVE_FAILURES_BEFORE_REDISCOVER,
    DEFAULT_AUX_CHANNELS,
    DEFAULT_INPUT_CHANNELS,
    DOMAIN,
)
from .protocol.discovery import discover
from .protocol.models import ChannelState, DetectedTopology, FlipTarget, SendState, UserKeyInfo
from .protocol.osc import OscArg, OscMessage, bool_arg, int_arg, string_arg
from .protocol.tcp_client import LV1TcpClient
from .protocol.tracks import MUTE_GROUP_PSEUDO_GROUP, enumerate_tracks

_LOGGER = logging.getLogger(__name__)


def signal_track_update(entry_id: str) -> str:
    """Dispatcher signal fired with (group, ch) whenever a track's state changes."""
    return f"{DOMAIN}_{entry_id}_track_update"


def signal_send_update(entry_id: str) -> str:
    """Dispatcher signal fired with (group, ch, aux) whenever a send changes."""
    return f"{DOMAIN}_{entry_id}_send_update"


def signal_topology_update(entry_id: str) -> str:
    """Fired (no args) when detected input/aux counts or aux names change."""
    return f"{DOMAIN}_{entry_id}_topology_update"


def signal_mute_group_update(entry_id: str) -> str:
    """Fired with (index 0..7) whenever a mute group's engaged state changes."""
    return f"{DOMAIN}_{entry_id}_mute_group_update"


def signal_scene_update(entry_id: str) -> str:
    """Fired (no args) whenever the scene list or the current scene changes."""
    return f"{DOMAIN}_{entry_id}_scene_update"


def signal_user_key_update(entry_id: str) -> str:
    """Fired with (index 0..15) whenever a user key's assignment changes."""
    return f"{DOMAIN}_{entry_id}_user_key_update"


def signal_global_update(entry_id: str) -> str:
    """Dispatcher signal for global LV1 state such as tempo and flip target."""
    return f"{DOMAIN}_{entry_id}_global_update"


def signal_connection_update(entry_id: str) -> str:
    """Fired (no args) whenever the TCP link connects, registers, or drops."""
    return f"{DOMAIN}_{entry_id}_connection_update"


class LV1Coordinator:
    """Owns the `LV1TcpClient`, maintains mixer state, and dispatches updates."""

    def __init__(self, hass: HomeAssistant, entry_id: str, host: str, port: int) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.host = host
        self.port = port

        self.client = LV1TcpClient(host, port)
        self.client.on("connect", self._on_connect)
        self.client.on("registered", self._on_registered)
        self.client.on("close", self._on_close)
        self.client.on("error", self._on_error)
        self.client.on("packet", self._on_packet)

        self.channels: dict[tuple[int, int], ChannelState] = {}
        self.sends: dict[tuple[int, int, int], SendState] = {}
        self.mute_groups: dict[int, bool] = {}
        self.scenes: dict[int, str] = {}
        self.current_scene: int | None = None
        self.current_scene_name: str | None = None
        self.current_tempo: float | None = None
        self.current_flip_target: FlipTarget | None = None
        self.user_keys: dict[int, UserKeyInfo] = {}
        self.detected = DetectedTopology()

        self._consecutive_failures = 0
        self._rediscover_task: Any | None = None
        self._meter_pending_updates: set[tuple[int, int]] = set()
        self._meter_flush_task: Any | None = None

    @property
    def connected(self) -> bool:
        """Whether the TCP link is up and handshaked."""
        return self.client.connected

    def effective_channels(self) -> int:
        """Input channel count to expose, falling back until `/Notify/Layers` arrives."""
        return self.detected.channels or DEFAULT_INPUT_CHANNELS

    def effective_auxes(self) -> int:
        """Aux bus count to expose, falling back until `/Aux/Tracks` arrives."""
        return self.detected.auxes or DEFAULT_AUX_CHANNELS

    def enumerate_tracks(self) -> list[tuple[int, int]]:
        """Every (group, ch) track this LV1 currently exposes."""
        return enumerate_tracks(self.effective_channels(), self.effective_auxes())

    def ensure_channel(self, group: int, ch: int) -> ChannelState:
        """Get-or-create the `ChannelState` for (group, ch)."""
        key = (group, ch)
        state = self.channels.get(key)
        if state is None:
            state = ChannelState()
            self.channels[key] = state
        return state

    def ensure_send(self, group: int, ch: int, aux: int) -> SendState:
        """Get-or-create the `SendState` for (group, ch, aux)."""
        key = (group, ch, aux)
        state = self.sends.get(key)
        if state is None:
            state = SendState()
            self.sends[key] = state
        return state

    # ---- Connection lifecycle ----

    async def async_connect(self) -> None:
        """Open the TCP connection and start the (auto-reconnecting) client."""
        await self.client.connect()

    def disconnect(self) -> None:
        """Tear down the connection; stops auto-reconnect too."""
        self.client.disconnect()

    def _on_connect(self, host: str, port: int) -> None:
        _LOGGER.info("TCP connected to %s:%s, running handshake", host, port)
        self._consecutive_failures = 0
        async_dispatcher_send(self.hass, signal_connection_update(self.entry_id))

    def _on_registered(self, style: str) -> None:
        _LOGGER.info("Registered with the LV1 as %s", style)
        self.request_state_refresh()
        async_dispatcher_send(self.hass, signal_connection_update(self.entry_id))

    def _on_close(self, had_error: bool) -> None:
        _LOGGER.warning("Connection closed (error=%s), will auto-reconnect", had_error)
        # A mixer-mode change can alter the whole topology, so drop it and
        # let the next handshake's /Notify/Layers + /Aux/Tracks repopulate it.
        self.detected = DetectedTopology()
        self._consecutive_failures += 1
        if self._consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_REDISCOVER and self._rediscover_task is None:
            self._consecutive_failures = 0
            self._rediscover_task = self.hass.async_create_task(self._async_rediscover_port())
        async_dispatcher_send(self.hass, signal_connection_update(self.entry_id))

    def _on_error(self, err: Exception) -> None:
        _LOGGER.error("OSC error: %s", err)

    async def _async_rediscover_port(self) -> None:
        """After repeated reconnect failures, suspect a port change and re-scan for it."""
        try:
            _LOGGER.info("Reconnect failing — running a fresh zDNS scan to find %s's new port", self.host)
            entries = await discover(filter_host_ip=self.host)
            match = next((entry for entry in entries if self.host in entry.addresses), None)
            if match is None or match.port is None:
                _LOGGER.warning("No zDNS match for %s — will keep retrying current port", self.host)
                return
            _LOGGER.info("Rediscovered %s on port %s — reconnecting", self.host, match.port)
            self.port = match.port
            self.client.update_target(self.host, match.port)
        finally:
            self._rediscover_task = None

    def request_state_refresh(self) -> None:
        """Ask the LV1 to re-send topology/state it won't spontaneously resend.

        The LV1 doesn't echo `/Set/...` back to the client that sent it and
        won't re-flood the initial state after the first handshake, so this
        nudges it on every (re)connect.
        """
        if not self.client.connected:
            return
        self.client.send("/Get/Aux/Tracks")
        self.client.send("/Get/Layers", [OscArg("i", 0), OscArg("i", 0)])

    # ---- /Notify/... state handling ----

    def _on_packet(self, message: OscMessage) -> None:
        handler = _NOTIFY_HANDLERS.get(message.address)
        if handler is not None:
            handler(self, message)

    def _handle_track_out_mute(self, message: OscMessage) -> None:
        # VERIFIED LIVE: ,iiiT [g, ch, isMuted(0|1), validFlag(always true)].
        # The LV1 multiplexes /Notify/MuteGroup over THIS address with the
        # pseudo-group g=13: args become [13, mg_index(0..7), state(0|1), T].
        group = int_arg(message, 0)
        ch = int_arg(message, 1)
        state = int_arg(message, 2)
        if group is None or ch is None or state is None:
            return
        if group == MUTE_GROUP_PSEUDO_GROUP:
            self._apply_mute_group(int(ch), state != 0)
            return
        channel = self.ensure_channel(int(group), int(ch))
        channel.muted = state != 0
        async_dispatcher_send(self.hass, signal_track_update(self.entry_id), int(group), int(ch))

    def _handle_track_pan(self, message: OscMessage) -> None:
        group, ch, value = int_arg(message, 0), int_arg(message, 1), int_arg(message, 2)
        if group is None or ch is None or value is None:
            return
        self.ensure_channel(int(group), int(ch)).pan = float(value)
        async_dispatcher_send(self.hass, signal_track_update(self.entry_id), int(group), int(ch))

    def _handle_track_width(self, message: OscMessage) -> None:
        group, ch, value = int_arg(message, 0), int_arg(message, 1), int_arg(message, 2)
        if group is None or ch is None or value is None:
            return
        self.ensure_channel(int(group), int(ch)).width = float(value)
        async_dispatcher_send(self.hass, signal_track_update(self.entry_id), int(group), int(ch))

    def _handle_track_gain(self, message: OscMessage) -> None:
        group, ch, db = int_arg(message, 0), int_arg(message, 1), int_arg(message, 2)
        if group is None or ch is None or db is None:
            return
        self.ensure_channel(int(group), int(ch)).gain = float(db)
        async_dispatcher_send(self.hass, signal_track_update(self.entry_id), int(group), int(ch))

    def _handle_solo(self, message: OscMessage) -> None:
        group, ch, state = int_arg(message, 0), int_arg(message, 1), int_arg(message, 2)
        if group is None or ch is None or state is None:
            return
        self.ensure_channel(int(group), int(ch)).solo = state != 0
        async_dispatcher_send(self.hass, signal_track_update(self.entry_id), int(group), int(ch))

    def _handle_track_color(self, message: OscMessage) -> None:
        group, ch = int_arg(message, 0), int_arg(message, 1)
        red, green, blue = int_arg(message, 3), int_arg(message, 4), int_arg(message, 5)
        if group is None or ch is None or red is None or green is None or blue is None:
            return
        self.ensure_channel(int(group), int(ch)).color = (float(red), float(green), float(blue))
        async_dispatcher_send(self.hass, signal_track_update(self.entry_id), int(group), int(ch))

    def _handle_track_name(self, message: OscMessage) -> None:
        group, ch = int_arg(message, 0), int_arg(message, 1)
        name = string_arg(message, 2)
        if group is None or ch is None or name is None:
            return
        self.ensure_channel(int(group), int(ch)).name = name
        async_dispatcher_send(self.hass, signal_track_update(self.entry_id), int(group), int(ch))

    def _handle_meters(self, message: OscMessage) -> None:
        """Accept `/Notify/Meters` payloads in either plain quad or "count + quads" form.

        Each meter is (group, ch, sub, dB-float); `sub` distinguishes mono/left
        (0) from the right channel of a stereo track (1) — only sub=0 is
        exposed as the track's VU level, matching the Companion module.
        """
        args = message.args
        if not args:
            return

        total_quads = None
        if args[0].type == "i":
            maybe_count = args[0].value
            if isinstance(maybe_count, int) and maybe_count > 0 and len(args) - 1 == maybe_count * 4:
                total_quads = maybe_count
                start = 1
            else:
                start = 0
        else:
            start = 0

        if total_quads is None:
            total_quads = (len(args) - start) // 4

        updated: set[tuple[int, int]] = set()
        for idx in range(total_quads):
            base = start + idx * 4
            if base + 3 >= len(args):
                break
            group_arg, ch_arg, sub_arg, value_arg = args[base], args[base + 1], args[base + 2], args[base + 3]
            if group_arg.type not in ("i", "f", "d") or ch_arg.type not in ("i", "f", "d"):
                continue
            if sub_arg.type not in ("i", "f", "d") or value_arg.type not in ("i", "f", "d"):
                continue
            if int(sub_arg.value) != 0:
                continue
            group, ch = int(group_arg.value), int(ch_arg.value)
            value = float(value_arg.value)
            self.ensure_channel(group, ch).meter = value
            updated.add((group, ch))

        if not updated:
            return
        self._meter_pending_updates.update(updated)
        if self._meter_flush_task is None or self._meter_flush_task.done():
            self._meter_flush_task = self.hass.async_create_task(self._async_flush_meter_updates())

    async def _async_flush_meter_updates(self) -> None:
        """Coalesce rapid meter bursts into a low-frequency refresh (~0.8 Hz)."""
        await asyncio.sleep(1.25)
        pending = self._meter_pending_updates
        self._meter_pending_updates = set()
        self._meter_flush_task = None
        for group, ch in pending:
            async_dispatcher_send(self.hass, signal_track_update(self.entry_id), group, ch)

    def _handle_user_key_info(self, message: OscMessage) -> None:
        # ,issi [keyIdx, shortName, function, assigned(0|1)] — 16 keys, sent
        # during the initial state flood.
        key = int_arg(message, 0)
        name = string_arg(message, 1)
        func = string_arg(message, 2)
        assigned = int_arg(message, 3)
        if key is None or name is None or func is None or assigned is None:
            return
        key = int(key)
        if key < 0 or key > 31:
            return
        self.user_keys[key] = UserKeyInfo(name=name, func=func, assigned=assigned != 0)
        async_dispatcher_send(self.hass, signal_user_key_update(self.entry_id), key)

    def _handle_tempo(self, message: OscMessage) -> None:
        tempo = int_arg(message, 0)
        if tempo is None:
            return
        self.current_tempo = float(tempo)
        async_dispatcher_send(self.hass, signal_global_update(self.entry_id))

    def _handle_internal_assign(self, message: OscMessage) -> None:
        group = int_arg(message, 0)
        ch = int_arg(message, 1)
        assign_type = int_arg(message, 2)
        state = int_arg(message, 4)
        if group is None or ch is None or assign_type != 7 or state is None:
            return
        if state == 1:
            self.current_flip_target = None if (group == 3 and ch == 0) else FlipTarget(int(group), int(ch))
        elif self.current_flip_target and (
            self.current_flip_target.group == group and self.current_flip_target.ch == ch
        ):
            self.current_flip_target = None
        async_dispatcher_send(self.hass, signal_global_update(self.entry_id))

    def _handle_aux_send_on(self, message: OscMessage) -> None:
        group, ch, aux = int_arg(message, 0), int_arg(message, 1), int_arg(message, 2)
        on = bool_arg(message, 3)
        if group is None or ch is None or aux is None or on is None:
            return
        self.ensure_send(int(group), int(ch), int(aux)).on = on
        async_dispatcher_send(self.hass, signal_send_update(self.entry_id), int(group), int(ch), int(aux))

    def _handle_aux_send_gain(self, message: OscMessage) -> None:
        group, ch, aux, db = (
            int_arg(message, 0),
            int_arg(message, 1),
            int_arg(message, 2),
            int_arg(message, 3),
        )
        if group is None or ch is None or aux is None or db is None:
            return
        self.ensure_send(int(group), int(ch), int(aux)).gain = float(db)
        async_dispatcher_send(self.hass, signal_send_update(self.entry_id), int(group), int(ch), int(aux))

    def _handle_cur_scene_index(self, message: OscMessage) -> None:
        idx = int_arg(message, 0)
        if idx is None:
            return
        self.current_scene = int(idx)
        self.current_scene_name = self.scenes.get(self.current_scene)
        async_dispatcher_send(self.hass, signal_scene_update(self.entry_id))

    def _handle_scene_name(self, message: OscMessage) -> None:
        # Broadcast for the CURRENT scene only (e.g. on a rename or recall).
        name = string_arg(message, 0)
        if name is None:
            return
        self.current_scene_name = name
        if self.current_scene is not None:
            self.scenes[self.current_scene] = name
        async_dispatcher_send(self.hass, signal_scene_update(self.entry_id))

    def _handle_scene_list(self, message: OscMessage) -> None:
        # ,i (i s)*N — first int = count, then (idx, name) pairs.
        count = int_arg(message, 0)
        if count is None or count < 0 or count > 999:
            return
        fresh: dict[int, str] = {}
        args = message.args
        i = 0
        while i + 1 < int(count) * 2 and 1 + i + 1 < len(args):
            idx_arg = args[1 + i]
            name_arg = args[1 + i + 1]
            if idx_arg.type == "i" and name_arg.type == "s":
                fresh[idx_arg.value] = name_arg.value
            i += 2
        self.scenes = fresh
        if self.current_scene is not None:
            self.current_scene_name = self.scenes.get(self.current_scene)
        async_dispatcher_send(self.hass, signal_scene_update(self.entry_id))

    def _handle_aux_tracks(self, message: OscMessage) -> None:
        # Reply to /Get/Aux/Tracks: first int is the aux count, then per aux (idx, group, name).
        count = int_arg(message, 0)
        if count is None:
            return
        names: list[str] = []
        args = message.args
        i = 1
        while i + 2 < len(args):
            name_arg = args[i + 2]
            if name_arg.type == "s":
                names.append(name_arg.value)
            i += 3
        changed = self.detected.auxes != int(count)
        self.detected.auxes = int(count)
        self.detected.aux_names = names
        if changed:
            _LOGGER.info("LV1 reports %s aux buses", count)
            async_dispatcher_send(self.hass, signal_topology_update(self.entry_id))

    def _handle_layers(self, message: OscMessage) -> None:
        # ,ii i (s i (i i)*)*layerCount — [page, isCustom, layerCount], then per
        # layer: name, entryCount, (group, ch)*entryCount. Empty slot = (-1, -1).
        # Custom user-defined layers aren't mixer topology, so they're skipped.
        args = message.args
        if len(args) < 3:
            return
        is_custom = int_arg(message, 1)
        layer_count = int_arg(message, 2)
        if is_custom is None or layer_count is None or not (0 < layer_count <= 32):
            return
        if int(is_custom) == 1:
            return
        idx = 3
        input_channels: set[int] = set()
        aux_channels: set[int] = set()
        for _ in range(int(layer_count)):
            if idx + 1 >= len(args) or args[idx].type != "s" or args[idx + 1].type != "i":
                break
            entry_count = args[idx + 1].value
            idx += 2
            for _ in range(entry_count):
                if idx + 1 >= len(args):
                    break
                group, ch = args[idx].value, args[idx + 1].value
                idx += 2
                if group == -1 and ch == -1:
                    continue
                if group == 0:
                    input_channels.add(ch)
                elif group == 2:
                    aux_channels.add(ch)
        changed = False
        if input_channels and self.detected.channels != len(input_channels):
            self.detected.channels = len(input_channels)
            changed = True
        if aux_channels and self.detected.auxes != len(aux_channels):
            self.detected.auxes = len(aux_channels)
            changed = True
        if changed:
            async_dispatcher_send(self.hass, signal_topology_update(self.entry_id))

    def _handle_channels(self, message: OscMessage) -> None:
        # ,i s iidd iiiiiiiiiiii hd × N — server floods the full track topology
        # (name + group + ch, plus other fields we don't need yet) after every
        # handshake. Each track record is 19 args wide.
        count = int_arg(message, 0)
        if count is None or not (0 < count <= 256):
            return
        args = message.args
        updated = False
        for i in range(int(count)):
            base = 1 + i * 19
            if base + 2 >= len(args):
                break
            name_arg, group_arg, ch_arg = args[base], args[base + 1], args[base + 2]
            if name_arg.type != "s" or group_arg.type != "i" or ch_arg.type != "i":
                continue
            channel = self.ensure_channel(group_arg.value, ch_arg.value)
            if channel.name != name_arg.value:
                channel.name = name_arg.value
                updated = True
        if updated:
            async_dispatcher_send(self.hass, signal_topology_update(self.entry_id))

    def _apply_mute_group(self, index: int, engaged: bool) -> None:
        self.mute_groups[index] = engaged
        async_dispatcher_send(self.hass, signal_mute_group_update(self.entry_id), index)


# Dispatch table for /Notify/... addresses, keyed exactly as broadcast on the wire.
_NOTIFY_HANDLERS: dict[str, Any] = {
    "/Notify/Track/Out/Mute": LV1Coordinator._handle_track_out_mute,
    "/Notify/Track/Pan": LV1Coordinator._handle_track_pan,
    "/Notify/Track/Pan/Width": LV1Coordinator._handle_track_width,
    "/Notify/PanArcWidth": LV1Coordinator._handle_track_width,
    "/Notify/Track/Out/Gain": LV1Coordinator._handle_track_gain,
    "/Notify/Solo": LV1Coordinator._handle_solo,
    "/Notify/TrackColor": LV1Coordinator._handle_track_color,
    "/Notify/Track/Name": LV1Coordinator._handle_track_name,
    "/Notify/TrackName": LV1Coordinator._handle_track_name,
    "/Notify/Meters": LV1Coordinator._handle_meters,
    "/Notify/UserKeyInfo": LV1Coordinator._handle_user_key_info,
    "/Notify/Tempo": LV1Coordinator._handle_tempo,
    "/Notify/InternalAssign": LV1Coordinator._handle_internal_assign,
    "/Notify/Aux/Send/On": LV1Coordinator._handle_aux_send_on,
    "/Notify/Aux/Send/Gain": LV1Coordinator._handle_aux_send_gain,
    "/Notify/CurSceneIndex": LV1Coordinator._handle_cur_scene_index,
    "/Notify/Scene/Name": LV1Coordinator._handle_scene_name,
    "/Notify/SceneList": LV1Coordinator._handle_scene_list,
    "/Aux/Tracks": LV1Coordinator._handle_aux_tracks,
    "/Notify/Layers": LV1Coordinator._handle_layers,
    "/Channels": LV1Coordinator._handle_channels,
}
