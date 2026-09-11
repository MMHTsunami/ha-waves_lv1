"""Editable track-name text entities."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import LV1Coordinator
from .entity import LV1Entity, enabled_groups_from_entry
from .protocol.osc import OscArg
from .protocol.tracks import filter_tracks_by_groups


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up editable name entities for every track."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    enabled_groups = enabled_groups_from_entry(entry)
    async_add_entities(
        LV1TrackName(coordinator, group, ch)
        for group, ch in filter_tracks_by_groups(coordinator.enumerate_tracks(), enabled_groups)
    )


class LV1TrackName(LV1Entity, TextEntity):
    """Track name with an optimistic local update."""

    _attr_native_min = 0
    _attr_native_max = 128

    def __init__(self, coordinator: LV1Coordinator, group: int, ch: int) -> None:
        super().__init__(coordinator, group, ch, "name", control_label="Name")

    @property
    def native_value(self) -> str:
        return self._track_name or ""

    async def async_set_value(self, value: str) -> None:
        name = value.strip()
        if not name:
            return
        self._coordinator.ensure_channel(self._group, self._ch).name = name
        self._coordinator.client.send(
            "/Set/TrackName",
            [OscArg("i", self._group), OscArg("i", self._ch), OscArg("s", name)],
        )
        self.async_write_ha_state()