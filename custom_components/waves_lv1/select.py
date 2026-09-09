"""Select platform for Waves eMotion LV1 (Scene Recall)."""
from __future__ import annotations

import struct
from typing import Any

from homeassistant.components.select import SelectEntity
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
    """Set up Scene Selector entity."""
    coordinator: LV1DataUpdateCoordinator = hass.data["waves_lv1"][entry.entry_id]
    async_add_entities([LV1SceneSelect(coordinator)])


class LV1SceneSelect(CoordinatorEntity[LV1DataUpdateCoordinator], SelectEntity):
    """Dropdown for active scene selection."""

    def __init__(self, coordinator: LV1DataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_name = "LV1 Active Scene"
        self._attr_unique_id = f"{coordinator.host}_scene_select"

    @property
    def options(self) -> list[str]:
        """Return available scene names."""
        if not self.coordinator.scenes:
            return ["Scene 1", "Scene 2", "Scene 3"]
        return list(self.coordinator.scenes.values())

    @property
    def current_option(self) -> str | None:
        """Return current scene name."""
        if self.coordinator.current_scene_name:
            return self.coordinator.current_scene_name
        if self.coordinator.current_scene is not None:
            return f"Scene {self.coordinator.current_scene + 1}"
        return None

    async def async_select_option(self, option: str) -> None:
        """Recall selected scene by index."""
        target_idx = 0
        for idx, name in self.coordinator.scenes.items():
            if name == option:
                target_idx = idx
                break

        # /Set/Scene/Recall ,i [scene_idx]
        payload = struct.pack(">i", target_idx)
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Scene/Recall", payload
        )
