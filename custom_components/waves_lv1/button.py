"""Command buttons for common LV1 operations."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import GROUP_GLOBAL, GROUP_SCENES, GROUP_USER_KEYS
from .coordinator import LV1Coordinator, signal_connection_update, signal_track_update
from .entity import LV1Entity, enabled_groups_from_entry
from .protocol.discovery import discover
from .protocol.osc import OscArg
from .protocol.tracks import user_key_label


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up command buttons."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    enabled_groups = enabled_groups_from_entry(entry)
    buttons: list[ButtonEntity] = []
    if GROUP_SCENES in enabled_groups:
        buttons.extend(
            (
                LV1CommandButton(coordinator, "scene_next", "Scene Next"),
                LV1CommandButton(coordinator, "scene_prev", "Scene Previous"),
            )
        )
    if GROUP_GLOBAL in enabled_groups:
        buttons.extend(
            (
                LV1CommandButton(coordinator, "tap_tempo", "Tap Tempo"),
                LV1CommandButton(coordinator, "clear_solos", "Clear Solos"),
                LV1CommandButton(coordinator, "refresh_state", "Refresh State"),
                LV1CommandButton(coordinator, "rescan", "Re-scan Discovery"),
            )
        )
    if GROUP_USER_KEYS in enabled_groups:
        buttons.extend(
            LV1CommandButton(coordinator, f"user_key_{index}", f"User Key {index + 1}")
            for index in range(16)
        )
    async_add_entities(buttons)


class LV1CommandButton(ButtonEntity):
    """A stateless LV1 command exposed as a Home Assistant button."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, command: str, name: str) -> None:
        self._coordinator = coordinator
        self._command = command
        self._static_name = name
        self._attr_unique_id = f"{coordinator.entry_id}_{command}"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "button").device_info

    @property
    def name(self) -> str:
        if self._command.startswith("user_key_"):
            index = int(self._command.rsplit("_", 1)[1])
            info = self._coordinator.user_keys.get(index)
            label = user_key_label(info.func if info else None)
            return f"UK{index + 1} {label}"
        return self._static_name

    @property
    def available(self) -> bool:
        return self._coordinator.connected

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_connection_update(self._coordinator.entry_id),
                self._handle_connection_update,
            )
        )

    @callback
    def _handle_connection_update(self) -> None:
        self.async_write_ha_state()

    async def async_press(self, **kwargs: Any) -> None:
        if self._command == "scene_next":
            self._send_adjacent_scene(1)
        elif self._command == "scene_prev":
            self._send_adjacent_scene(-1)
        elif self._command == "tap_tempo":
            self._coordinator.client.send("/TapTempo", [OscArg("i", 1)])
            self._coordinator.client.send("/TapTempo", [OscArg("i", 0)])
        elif self._command == "clear_solos":
            self._coordinator.client.send("/ClearAllSolo", [])
            for (group, ch), state in self._coordinator.channels.items():
                if state.solo:
                    state.solo = False
                    async_dispatcher_send(
                        self._coordinator.hass,
                        signal_track_update(self._coordinator.entry_id),
                        group,
                        ch,
                    )
        elif self._command == "refresh_state":
            self._coordinator.request_state_refresh()
        elif self._command == "rescan":
            await self._rescan()
        elif self._command.startswith("user_key_"):
            index = int(self._command.rsplit("_", 1)[1])
            self._coordinator.client.send("/Set/UserKey", [OscArg("i", index), OscArg("T")])
            self._coordinator.client.send("/Set/UserKey", [OscArg("i", index), OscArg("F")])

    def _send_adjacent_scene(self, direction: int) -> None:
        indices = sorted(self._coordinator.scenes)
        if not indices:
            return
        current = self._coordinator.current_scene
        position = indices.index(current) if current in indices else (0 if direction > 0 else len(indices) - 1)
        target = indices[(position + direction) % len(indices)]
        self._coordinator.client.send("/Set/CurSceneIndex", [OscArg("i", target)])

    async def _rescan(self) -> None:
        entries = await discover(filter_host_ip=self._coordinator.host)
        match = next((entry for entry in entries if self._coordinator.host in entry.addresses), None)
        if match and match.port is not None:
            self._coordinator.port = match.port
            self._coordinator.client.update_target(self._coordinator.host, match.port)