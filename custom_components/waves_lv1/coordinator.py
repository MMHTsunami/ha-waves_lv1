"""DataUpdateCoordinator managing state and reconnect loops for Waves LV1."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, NamedTuple

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    MAX_RECONNECT_ATTEMPTS_BEFORE_REDISCOVER,
    RECONNECT_DELAY_BASE,
)
from .discovery import async_discover_lv1
from .osc_client import LV1OSCClient

_LOGGER = logging.getLogger(__name__)


class ChannelState(NamedTuple):
    muted: bool = False
    gain: float = 0.0  # dB
    solo: bool = False
    name: str | None = None
    pan: float = 0.0  # -1..+1
    width: float = 1.0  # 0..1


class LV1DataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manages OSC state push updates, active reconnects, and zDNS rediscovery."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # State is maintained via local_push OSC notifications
        )
        self.host = host
        self.port = port

        self.osc_client = LV1OSCClient(
            host=self.host,
            port=self.port,
            on_message=self._handle_osc_message,
            on_disconnect=self._handle_disconnect,
        )

        # Mirroring Companion's internal state maps[cite: 1]
        self.channels: dict[str, dict[str, Any]] = {}
        self.sends: dict[str, dict[str, Any]] = {}
        self.mute_groups: dict[int, bool] = {i: False for i in range(8)}
        self.scenes: dict[int, str] = {}
        self.user_keys: dict[int, dict[str, Any]] = {}

        # Mixer Metadata[cite: 1]
        self.current_scene: int | None = None
        self.current_scene_name: str | None = None
        self.current_layer: int | None = None
        self.last_tempo_bpm: float | None = None
        self.effective_channels: int = 80
        self.effective_auxes: int = 32

        # Reconnection & Fader Ramping State[cite: 1]
        self._consecutive_failures = 0
        self._reconnect_task: asyncio.Task | None = None
        self._active_fades: dict[str, asyncio.Task] = {}

    async def async_start(self) -> None:
        """Start the primary connection loop."""
        connected = await self.osc_client.connect()
        if not connected:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff and rediscovery."""
        if self._reconnect_task and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self) -> None:
        """Auto-reconnect loop with dynamic port rediscovery upon restart/mode change[cite: 1, 3]."""
        while not self.osc_client.is_connected:
            self._consecutive_failures += 1
            delay = min(RECONNECT_DELAY_BASE * (1.5 ** (self._consecutive_failures - 1)), 30.0)

            # Re-discover port after consecutive retries (LV1 changes port on restart/mode change)[cite: 1, 3]
            if self._consecutive_failures >= MAX_RECONNECT_ATTEMPTS_BEFORE_REDISCOVER:
                _LOGGER.info("Attempting zDNS rediscovery for host %s...", self.host)
                discovered = await async_discover_lv1(timeout=3.0)
                for dev in discovered:
                    if dev["host"] == self.host and dev["port"] != self.port:
                        _LOGGER.info("LV1 port change detected: %d -> %d", self.port, dev["port"])
                        self.port = dev["port"]
                        self.osc_client.port = self.port
                        break

            _LOGGER.warning(
                "Reconnecting to LV1 at %s:%d (Attempt %d) in %.1fs...",
                self.host,
                self.port,
                self._consecutive_failures,
                delay,
            )
            await asyncio.sleep(delay)

            if await self.osc_client.connect():
                _LOGGER.info("Successfully reconnected to LV1 at %s:%d", self.host, self.port)
                self._consecutive_failures = 0
                self.async_update_listeners()
                break

    @callback
    def _handle_disconnect(self) -> None:
        """Triggered by low-level socket disconnect."""
        _LOGGER.warning("Disconnected from LV1 mixer")
        self.async_update_listeners()
        self._schedule_reconnect()

    def _handle_osc_message(self, address: str, args: list) -> None:
        """Parse incoming /Notify/ packets and update entity states[cite: 1]."""
        try:
            if address == "/Notify/Track/Out/Mute":
                # [group, ch, is_muted, valid_flag][cite: 1]
                group, ch, is_muted = args[0], args[1], bool(args[2])
                if group == 13:  # Group 13 multiplexes Mute Groups[cite: 1]
                    self.mute_groups[ch] = is_muted
                else:
                    key = f"{group}.{ch}"
                    self.channels.setdefault(key, {})["muted"] = is_muted

            elif address == "/Notify/Track/Out/Gain":
                group, ch, gain_db = args[0], args[1], float(args[2])
                self.channels.setdefault(f"{group}.{ch}", {})["gain"] = gain_db

            elif address == "/Notify/Track/Solo":
                group, ch, is_solo = args[0], args[1], bool(args[2])
                self.channels.setdefault(f"{group}.{ch}", {})["solo"] = is_solo

            elif address == "/Notify/Scene/Current":
                self.current_scene = int(args[0])
                if len(args) > 1:
                    self.current_scene_name = str(args[1])

            elif address == "/Notify/Tempo":
                self.last_tempo_bpm = float(args[0])

            # Dispatch notification updates directly to Home Assistant entities[cite: 1]
            self.async_update_listeners()

        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Error parsing OSC address %s: %s", address, err)

    async def async_start_fade(
        self,
        key: str,
        target_db: float,
        duration_ms: int,
        apply_cb: Callable[[float], None],
    ) -> None:
        """Linearly ramp a fader in dB over time[cite: 1]."""
        if key in self._active_fades:
            self._active_fades[key].cancel()

        current_db = self.channels.get(key, {}).get("gain", 0.0)
        if duration_ms <= 0 or current_db == target_db:
            apply_cb(target_db)
            return

        async def _fade_runner() -> None:
            step_time = 0.03  # 30ms step resolution[cite: 1]
            steps = max(1, int(duration_ms / 1000.0 / step_time))
            delta = (target_db - current_db) / steps

            val = current_db
            for _ in range(steps):
                val += delta
                apply_cb(val)
                await asyncio.sleep(step_time)

            apply_cb(target_db)
            self._active_fades.pop(key, None)

        self._active_fades[key] = asyncio.create_task(_fade_runner())

    async def async_shutdown(self) -> None:
        """Clean up tasks and connection on unload."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
        for fade in self._active_fades.values():
            fade.cancel()
        await self.osc_client.close()
