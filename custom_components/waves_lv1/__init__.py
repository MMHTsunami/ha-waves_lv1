"""The Waves eMotion LV1 Integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import LV1DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Waves LV1 from a config entry."""
    host = entry.data["host"]
    port = entry.data["port"]

    coordinator = LV1DataUpdateCoordinator(hass, host, port)
    await coordinator.async_start()

    hass.data.setdefault("waves_lv1", {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register raw OSC command service
    async def handle_send_raw_osc(call):
        address = call.data.get("address")
        args_bytes = call.data.get("args_bytes", b"")
        await coordinator.osc_client.send_raw_osc(address, args_bytes)

    hass.services.async_register(
        "waves_lv1", "send_raw_osc", handle_send_raw_osc
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        coordinator: LV1DataUpdateCoordinator = hass.data["waves_lv1"].pop(
            entry.entry_id
        )
        await coordinator.async_shutdown()

    return unload_ok
