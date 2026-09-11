"""Switch entities for LV1 mutes, solos, sends, and mute groups."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import GROUP_AUX_SENDS, GROUP_MUTE_GROUPS
from .coordinator import LV1Coordinator, signal_connection_update, signal_mute_group_update, signal_send_update
from .entity import LV1Entity, aux_display_name, enabled_groups_from_entry
from .protocol.osc import OscArg
from .protocol.tracks import filter_tracks_by_groups, track_entity_prefix


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up all switch entities for the current mixer topology."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    enabled_groups = enabled_groups_from_entry(entry)
    entities: list[SwitchEntity] = []

    for group, ch in filter_tracks_by_groups(coordinator.enumerate_tracks(), enabled_groups):
        entities.extend(
            (
                LV1TrackSwitch(coordinator, group, ch, "mute"),
                LV1TrackSwitch(coordinator, group, ch, "solo"),
            )
        )

    if GROUP_AUX_SENDS in enabled_groups:
        for ch in range(coordinator.effective_channels()):
            for aux in range(coordinator.effective_auxes()):
                entities.append(LV1SendSwitch(coordinator, ch, aux))

    if GROUP_MUTE_GROUPS in enabled_groups:
        entities.extend(LV1MuteGroupSwitch(coordinator, index) for index in range(8))
    async_add_entities(entities)


class LV1TrackSwitch(LV1Entity, SwitchEntity):
    """Mute or solo switch for one LV1 track."""

    def __init__(self, coordinator: LV1Coordinator, group: int, ch: int, prop: str) -> None:
        control_label = "Mute" if prop == "mute" else "Solo"
        super().__init__(coordinator, group, ch, prop, control_label=control_label)

    @property
    def is_on(self) -> bool:
        state = self._coordinator.channels.get((self._group, self._ch))
        state_attr = "muted" if self._prop == "mute" else "solo"
        return bool(getattr(state, state_attr, False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set_state(False)

    @callback
    def _set_state(self, state: bool) -> None:
        channel = self._coordinator.ensure_channel(self._group, self._ch)
        if self._prop == "mute":
            channel.muted = state
            address = "/Set/Track/Out/Mute"
            args = [
                OscArg("i", self._group),
                OscArg("i", self._ch),
                OscArg("T" if state else "F"),
            ]
        else:
            channel.solo = state
            address = "/Set/Solo"
            args = [OscArg("i", self._group), OscArg("i", self._ch), OscArg("i", int(state))]
        self._coordinator.client.send(address, args)
        self.async_write_ha_state()


class LV1SendSwitch(SwitchEntity):
    """On/off switch for an input channel's send to an aux bus."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, ch: int, aux: int) -> None:
        self._coordinator = coordinator
        self._ch = ch
        self._aux = aux
        self._attr_unique_id = f"{coordinator.entry_id}_0_{ch}_aux_{aux}_on"
        self._attr_device_info = LV1Entity(coordinator, 0, ch, "send").device_info

    @property
    def name(self) -> str:
        parts = [track_entity_prefix(2, self._aux)]
        aux_name = aux_display_name(self._coordinator, self._aux)
        if aux_name:
            parts.append(aux_name)
        parts.append("Send")
        return " ".join(parts)

    @property
    def available(self) -> bool:
        return self._coordinator.connected

    @property
    def is_on(self) -> bool:
        state = self._coordinator.sends.get((0, self._ch, self._aux))
        return state.on if state else False

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_send_update(self._coordinator.entry_id),
                self._handle_send_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_connection_update(self._coordinator.entry_id),
                self._handle_connection_update,
            )
        )

    @callback
    def _handle_send_update(self, group: int, ch: int, aux: int) -> None:
        if group == 0 and ch == self._ch and aux == self._aux:
            self.async_write_ha_state()

    @callback
    def _handle_connection_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set_state(False)

    @callback
    def _set_state(self, state: bool) -> None:
        self._coordinator.ensure_send(0, self._ch, self._aux).on = state
        self._coordinator.client.send(
            "/Set/Aux/Send/On",
            [
                OscArg("i", 0),
                OscArg("i", self._ch),
                OscArg("i", self._aux),
                OscArg("T" if state else "F"),
            ],
        )
        self.async_write_ha_state()


class LV1MuteGroupSwitch(SwitchEntity):
    """Switch for one of the LV1's eight mute groups."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, index: int) -> None:
        self._coordinator = coordinator
        self._index = index
        self._attr_unique_id = f"{coordinator.entry_id}_mute_group_{index}"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "mute_group").device_info

    @property
    def name(self) -> str:
        return f"MG{self._index + 1} Mute"

    @property
    def available(self) -> bool:
        return self._coordinator.connected

    @property
    def is_on(self) -> bool:
        return self._coordinator.mute_groups.get(self._index, False)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_mute_group_update(self._coordinator.entry_id),
                self._handle_mute_group_update,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_connection_update(self._coordinator.entry_id),
                self._handle_connection_update,
            )
        )

    @callback
    def _handle_mute_group_update(self, index: int) -> None:
        if index == self._index:
            self.async_write_ha_state()

    @callback
    def _handle_connection_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set_state(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set_state(False)

    @callback
    def _set_state(self, state: bool) -> None:
        self._coordinator.mute_groups[self._index] = state
        self._coordinator.client.send(
            "/Set/MuteGroup", [OscArg("i", self._index), OscArg("T" if state else "F")]
        )
        self.async_write_ha_state()