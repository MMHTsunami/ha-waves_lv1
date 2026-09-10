"""Scene selection for the LV1."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import LV1Coordinator, signal_scene_update
from .entity import LV1Entity
from .protocol.osc import OscArg


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the current-scene selector."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    async_add_entities([LV1SceneSelect(coordinator)])


class LV1SceneSelect(SelectEntity):
    """Select and recall scenes by their LV1-provided names."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_scene"
        self._attr_name = "Scene"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "scene").device_info

    @property
    def available(self) -> bool:
        return self._coordinator.connected

    @property
    def options(self) -> list[str]:
        return [name for _, name in sorted(self._coordinator.scenes.items())]

    @property
    def current_option(self) -> str | None:
        return self._coordinator.current_scene_name

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_scene_update(self._coordinator.entry_id),
                self._handle_scene_update,
            )
        )

    @callback
    def _handle_scene_update(self) -> None:
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        scene_index = next(
            (index for index, name in self._coordinator.scenes.items() if name == option),
            None,
        )
        if scene_index is None:
            return
        self._coordinator.current_scene = scene_index
        self._coordinator.current_scene_name = option
        self._coordinator.client.send("/Set/CurSceneIndex", [OscArg("i", scene_index)])
        self.async_write_ha_state()