<<<<<<< HEAD
"""Read-only LV1 state sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    LV1Coordinator,
    signal_global_update,
    signal_scene_update,
    signal_topology_update,
    signal_track_update,
    signal_user_key_update,
)
from .entity import LV1Entity
from .protocol.tracks import user_key_label


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up read-only state sensors."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    entities: list[SensorEntity] = [
        LV1CurrentSceneSensor(coordinator),
        LV1TempoSensor(coordinator),
        LV1FlipSensor(coordinator),
        LV1TopologySensor(coordinator, "channels"),
        LV1TopologySensor(coordinator, "auxes"),
    ]
    for group, ch in coordinator.enumerate_tracks():
        entities.extend(
            (LV1TrackNameSensor(coordinator, group, ch), LV1TrackColorSensor(coordinator, group, ch))
        )
    entities.extend(LV1UserKeySensor(coordinator, index) for index in range(16))
    async_add_entities(entities)


class LV1CurrentSceneSensor(SensorEntity):
    """Current scene name and index sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_current_scene"
        self._attr_name = "Current Scene"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "scene").device_info

    @property
    def native_value(self) -> str | None:
        return self._coordinator.current_scene_name

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {"scene_index": self._coordinator.current_scene}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_scene_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class LV1TopologySensor(SensorEntity):
    """Detected input or aux total."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LV1Coordinator, kind: str) -> None:
        self._coordinator = coordinator
        self._kind = kind
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_total"
        self._attr_name = f"{kind.title()} Total"
        self._attr_native_unit_of_measurement = "channels"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "topology").device_info

    @property
    def native_value(self) -> int:
        return (
            self._coordinator.effective_channels()
            if self._kind == "channels"
            else self._coordinator.effective_auxes()
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_topology_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class LV1TrackNameSensor(LV1Entity, SensorEntity):
    """Read-only track name sensor."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, group: int, ch: int) -> None:
        super().__init__(coordinator, group, ch, "sensor_name", control_label="Track Name")

    @property
    def native_value(self) -> str | None:
        return self._track_name


class LV1TrackColorSensor(LV1Entity, SensorEntity):
    """Track color represented as a hexadecimal RGB string."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, group: int, ch: int) -> None:
        super().__init__(coordinator, group, ch, "color", control_label="Color")

    @property
    def native_value(self) -> str | None:
        color = self._coordinator.channels.get((self._group, self._ch))
        if not color or color.color is None:
            return None
        red, green, blue = (max(0, min(255, round(value * 255))) for value in color.color)
        return f"#{red:02x}{green:02x}{blue:02x}"


class LV1UserKeySensor(SensorEntity):
    """Assignment and function for one user key."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, index: int) -> None:
        self._coordinator = coordinator
        self._index = index
        self._attr_unique_id = f"{coordinator.entry_id}_user_key_{index}"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "user_key").device_info

    @property
    def name(self) -> str:
        info = self._coordinator.user_keys.get(self._index)
        label = user_key_label(info.func if info else None)
        return f"UK{self._index + 1} {label} Info"

    @property
    def native_value(self) -> str | None:
        info = self._coordinator.user_keys.get(self._index)
        return f"{info.name}: {info.func}" if info else None

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        info = self._coordinator.user_keys.get(self._index)
        return {"assigned": info.assigned} if info else {"assigned": False}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_user_key_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, index: int) -> None:
        if index == self._index:
            self.async_write_ha_state()


class LV1TempoSensor(SensorEntity):
    """Current LV1 tempo in beats per minute."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "BPM"

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_tempo"
        self._attr_name = "Tempo"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "tempo").device_info

    @property
    def native_value(self) -> float | None:
        return self._coordinator.current_tempo

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_global_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class LV1FlipSensor(SensorEntity):
    """Current track assigned to the flip fader strip."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_flip"
        self._attr_name = "Flip Target"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "flip").device_info

    @property
    def native_value(self) -> str:
        target = self._coordinator.current_flip_target
        if target is None:
            return "LR"
        state = self._coordinator.channels.get((target.group, target.ch))
        return state.name if state and state.name else f"Group {target.group}, Channel {target.ch + 1}"

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        target = self._coordinator.current_flip_target
        return {
            "group": target.group if target else 3,
            "channel": target.ch if target else 0,
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_global_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
=======
"""Read-only LV1 state sensors."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import (
    LV1Coordinator,
    signal_global_update,
    signal_scene_update,
    signal_topology_update,
    signal_track_update,
    signal_user_key_update,
)
from .entity import LV1Entity
from .protocol.tracks import user_key_label


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up read-only state sensors."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    entities: list[SensorEntity] = [
        LV1CurrentSceneSensor(coordinator),
        LV1TempoSensor(coordinator),
        LV1FlipSensor(coordinator),
        LV1TopologySensor(coordinator, "channels"),
        LV1TopologySensor(coordinator, "auxes"),
    ]
    for group, ch in coordinator.enumerate_tracks():
        entities.extend(
            (LV1TrackNameSensor(coordinator, group, ch), LV1TrackColorSensor(coordinator, group, ch))
        )
    entities.extend(LV1UserKeySensor(coordinator, index) for index in range(16))
    async_add_entities(entities)


class LV1CurrentSceneSensor(SensorEntity):
    """Current scene name and index sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_current_scene"
        self._attr_name = "Current Scene"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "scene").device_info

    @property
    def native_value(self) -> str | None:
        return self._coordinator.current_scene_name

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        return {"scene_index": self._coordinator.current_scene}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_scene_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class LV1TopologySensor(SensorEntity):
    """Detected input or aux total."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LV1Coordinator, kind: str) -> None:
        self._coordinator = coordinator
        self._kind = kind
        self._attr_unique_id = f"{coordinator.entry_id}_{kind}_total"
        self._attr_name = f"{kind.title()} Total"
        self._attr_native_unit_of_measurement = "channels"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "topology").device_info

    @property
    def native_value(self) -> int:
        return (
            self._coordinator.effective_channels()
            if self._kind == "channels"
            else self._coordinator.effective_auxes()
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_topology_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class LV1TrackNameSensor(LV1Entity, SensorEntity):
    """Read-only track name sensor."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, group: int, ch: int) -> None:
        super().__init__(coordinator, group, ch, "sensor_name", control_label="Track Name")

    @property
    def native_value(self) -> str | None:
        return self._track_name


class LV1TrackColorSensor(LV1Entity, SensorEntity):
    """Track color represented as a hexadecimal RGB string."""

    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, group: int, ch: int) -> None:
        super().__init__(coordinator, group, ch, "color", control_label="Color")

    @property
    def native_value(self) -> str | None:
        color = self._coordinator.channels.get((self._group, self._ch))
        if not color or color.color is None:
            return None
        red, green, blue = (max(0, min(255, round(value * 255))) for value in color.color)
        return f"#{red:02x}{green:02x}{blue:02x}"


class LV1UserKeySensor(SensorEntity):
    """Assignment and function for one user key."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: LV1Coordinator, index: int) -> None:
        self._coordinator = coordinator
        self._index = index
        self._attr_unique_id = f"{coordinator.entry_id}_user_key_{index}"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "user_key").device_info

    @property
    def name(self) -> str:
        info = self._coordinator.user_keys.get(self._index)
        label = user_key_label(info.func if info else None)
        return f"UK{self._index + 1} {label} Info"

    @property
    def native_value(self) -> str | None:
        info = self._coordinator.user_keys.get(self._index)
        return f"{info.name}: {info.func}" if info else None

    @property
    def extra_state_attributes(self) -> dict[str, bool]:
        info = self._coordinator.user_keys.get(self._index)
        return {"assigned": info.assigned} if info else {"assigned": False}

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_user_key_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self, index: int) -> None:
        if index == self._index:
            self.async_write_ha_state()


class LV1TempoSensor(SensorEntity):
    """Current LV1 tempo in beats per minute."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_native_unit_of_measurement = "BPM"

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_tempo"
        self._attr_name = "Tempo"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "tempo").device_info

    @property
    def native_value(self) -> float | None:
        return self._coordinator.current_tempo

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_global_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class LV1FlipSensor(SensorEntity):
    """Current track assigned to the flip fader strip."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: LV1Coordinator) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry_id}_flip"
        self._attr_name = "Flip Target"
        self._attr_device_info = LV1Entity(coordinator, 0, 0, "flip").device_info

    @property
    def native_value(self) -> str:
        target = self._coordinator.current_flip_target
        if target is None:
            return "LR"
        state = self._coordinator.channels.get((target.group, target.ch))
        return state.name if state and state.name else f"Group {target.group}, Channel {target.ch + 1}"

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        target = self._coordinator.current_flip_target
        return {
            "group": target.group if target else 3,
            "channel": target.ch if target else 0,
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_global_update(self._coordinator.entry_id),
                self._handle_update,
            )
        )

    @callback
    def _handle_update(self) -> None:
>>>>>>> a4d4b88771db852133a7c171f5bef0d2e6b101d5
        self.async_write_ha_state()