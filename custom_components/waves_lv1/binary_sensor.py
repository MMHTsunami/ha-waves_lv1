"""Connectivity status for the LV1's TCP link."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import LV1Coordinator, signal_connection_update
from .entity import LV1Entity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the connectivity sensor. Always created, regardless of entity groups."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    async_add_entities([LV1ConnectivitySensor(coordinator)])


class LV1ConnectivitySensor(BinarySensorEntity):
    """Whether the TCP link to the LV1 is currently up."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_connectivity"
        self._attr_name = "Connectivity"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "connectivity").device_info

    @property
    def is_on(self) -> bool:
        return self._coordinator.connected

    @property
    def available(self) -> bool:
        """This entity reports connection state, so it's always available itself."""
        return True

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_connection_update(self._coordinator.entry_id),
                self._handle_connection_update,
            )
        )
        # Re-sync now in case the connection state changed before this subscription existed.
        self.async_write_ha_state()

    @callback
    def _handle_connection_update(self) -> None:
        self.async_write_ha_state()
