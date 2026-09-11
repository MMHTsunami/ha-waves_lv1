"""Shared entity base class: device grouping + `{group}_{ch}_{prop}` unique IDs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import CONF_ENABLED_GROUPS, DEFAULT_ENABLED_GROUPS, DOMAIN
from .coordinator import LV1Coordinator, signal_connection_update, signal_track_update
from .protocol.tracks import track_entity_prefix, track_label

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def enabled_groups_from_entry(entry: "ConfigEntry") -> set[str]:
    """The options-flow group categories the user has chosen to create entities for."""
    return set(entry.options.get(CONF_ENABLED_GROUPS, DEFAULT_ENABLED_GROUPS))


class LV1Entity(Entity):
    """Base entity for a single LV1 track property (e.g. mute, gain, pan).

    The display name is computed dynamically on every read from the LV1's
    reported track name (`{Prefix}{Index} {Track Name} {Control}`), so it
    stays in sync with `/Notify/TrackName` without touching `unique_id`.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: LV1Coordinator,
        group: int,
        ch: int,
        prop: str,
        control_label: str | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._group = group
        self._ch = ch
        self._prop = prop
        self._control_label = control_label if control_label is not None else prop.replace("_", " ").title()
        self._attr_unique_id = f"{coordinator.entry_id}_{group}_{ch}_{prop}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=f"Waves LV1 ({coordinator.host})",
            manufacturer="Waves Audio",
            model="eMotion LV1",
        )

    @property
    def name(self) -> str:
        """`{Prefix}{Index} {Track Name} {Control}`, dropping the name if unreported."""
        parts = [track_entity_prefix(self._group, self._ch)]
        if self._track_name:
            parts.append(self._track_name)
        if self._control_label:
            parts.append(self._control_label)
        return " ".join(parts)

    @property
    def available(self) -> bool:
        """Entities go unavailable while the LV1 link is down."""
        return self._coordinator.connected

    async def async_added_to_hass(self) -> None:
        """Subscribe to this track's dispatcher signal for the entity's lifetime."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_track_update(self._coordinator.entry_id),
                self._handle_track_update,
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
    def _handle_track_update(self, group: int, ch: int) -> None:
        if group == self._group and ch == self._ch:
            self.async_write_ha_state()

    @callback
    def _handle_connection_update(self) -> None:
        self.async_write_ha_state()

    @property
    def _track_name(self) -> str | None:
        state = self._coordinator.channels.get((self._group, self._ch))
        return state.name if state else None

    @property
    def _track_label(self) -> str:
        return track_label(self._group, self._ch, self._track_name)


def aux_display_name(coordinator: LV1Coordinator, aux: int) -> str | None:
    """Best-known name for an aux bus: its own track state, else `/Aux/Tracks`."""
    state = coordinator.channels.get((2, aux))
    if state and state.name:
        return state.name
    aux_names = coordinator.detected.aux_names
    if 0 <= aux < len(aux_names):
        return aux_names[aux] or None
    return None
