"""Number platform for Waves eMotion LV1 (Channel Faders and Pan)."""
from __future__ import annotations

import struct
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
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
    """Set up Channel Fader entities."""
    coordinator: LV1DataUpdateCoordinator = hass.data["waves_lv1"][entry.entry_id]

    entities: list[NumberEntity] = []
    for ch in range(1, 81):
        entities.append(LV1FaderNumber(coordinator, group=0, ch=ch - 1))

    async_add_entities(entities)


class LV1FaderNumber(CoordinatorEntity[LV1DataUpdateCoordinator], NumberEntity):
    """Fader level entity controlling gain in dB (-144.0 to +10.0)."""

    _attr_native_min_value = -144.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, coordinator: LV1DataUpdateCoordinator, group: int, ch: int
    ) -> None:
        super().__init__(coordinator)
        self.group = group
        self.ch = ch
        self._attr_name = f"LV1 Channel {ch + 1} Fader"
        self._attr_unique_id = f"{coordinator.host}_fader_{group}_{ch}"

    @property
    def native_value(self) -> float:
        key = f"{self.group}.{self.ch}"
        return self.coordinator.channels.get(key, {}).get("gain", -144.0)

    async def async_set_native_value(self, value: float) -> None:
        """Set channel gain in dB."""
        # /Set/Track/Gain ,iif [group, ch, gain_float]
        payload = struct.pack(">iif", self.group, self.ch, float(value))
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Track/Gain", payload
        )
