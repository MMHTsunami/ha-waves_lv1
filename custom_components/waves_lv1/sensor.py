"""Sensor platform for Waves eMotion LV1 status and metrics."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LV1DataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tempo and Mixer status sensors."""
    coordinator: LV1DataUpdateCoordinator = hass.data["waves_lv1"][entry.entry_id]
    async_add_entities(
        [
            LV1TempoSensor(coordinator),
            LV1ConnectionSensor(coordinator),
        ]
    )


class LV1TempoSensor(CoordinatorEntity[LV1DataUpdateCoordinator], SensorEntity):
    """BPM Tempo Sensor."""

    _attr_native_unit_of_measurement = "BPM"
    _attr_icon = "mdi:metronome"

    def __init__(self, coordinator: LV1DataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "LV1 Global Tempo"
        self._attr_unique_id = f"{coordinator.host}_tempo"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.last_tempo_bpm


class LV1ConnectionSensor(
    CoordinatorEntity[LV1DataUpdateCoordinator], SensorEntity
):
    """TCP Connection Status Sensor."""

    _attr_icon = "mdi:ethernet"

    def __init__(self, coordinator: LV1DataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "LV1 Connection State"
        self._attr_unique_id = f"{coordinator.host}_connection_state"

    @property
    def native_value(self) -> str:
        return (
            "Connected"
            if self.coordinator.osc_client.is_connected
            else "Disconnected"
        )
