"""Number entities for LV1 faders, pan, width, and send gain."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import LV1Coordinator
from .entity import LV1Entity, aux_display_name
from .protocol.osc import OscArg
from .protocol.tracks import track_entity_prefix


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up numeric controls for the current mixer topology."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    entities: list[NumberEntity] = []
    for group, ch in coordinator.enumerate_tracks():
        entities.extend(
            LV1TrackNumber(coordinator, group, ch, prop)
            for prop in ("gain", "pan", "width")
        )
    for ch in range(coordinator.effective_channels()):
        for aux in range(coordinator.effective_auxes()):
            entities.append(LV1SendGainNumber(coordinator, ch, aux))
    async_add_entities(entities)


class LV1TrackNumber(LV1Entity, NumberEntity):
    """Numeric output control for one LV1 track."""

    _attr_mode = NumberMode.SLIDER

    _LIMITS = {
        "gain": (-144.0, 10.0, 0.1, "Fader"),
        "pan": (-1.0, 1.0, 0.01, "Pan"),
        "width": (0.0, 1.0, 0.01, "Width"),
    }

    def __init__(self, coordinator: LV1Coordinator, group: int, ch: int, prop: str) -> None:
        minimum, maximum, step, control_label = self._LIMITS[prop]
        super().__init__(coordinator, group, ch, prop, control_label=control_label)
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step

    @property
    def native_value(self) -> float:
        state = self._coordinator.channels.get((self._group, self._ch))
        return float(getattr(state, self._prop, 0.0))

    async def async_set_native_value(self, value: float) -> None:
        value = float(value)
        channel = self._coordinator.ensure_channel(self._group, self._ch)
        setattr(channel, self._prop, value)
        address = {
            "gain": "/Set/Track/Out/Gain",
            "pan": "/Set/Track/Pan",
            "width": "/Set/Track/Pan/Width",
        }[self._prop]
        self._coordinator.client.send(
            address,
            [OscArg("i", self._group), OscArg("i", self._ch), OscArg("d", value)],
        )
        self.async_write_ha_state()


class LV1SendGainNumber(NumberEntity):
    """Numeric send gain control for an input-to-aux route."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_entity_registry_enabled_default = False
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = -144.0
    _attr_native_max_value = 10.0
    _attr_native_step = 0.1

    def __init__(self, coordinator: LV1Coordinator, ch: int, aux: int) -> None:
        self._coordinator = coordinator
        self._ch = ch
        self._aux = aux
        self._attr_unique_id = f"{coordinator.entry_id}_0_{ch}_aux_{aux}_gain"
        self._attr_device_info = LV1Entity(coordinator, 0, ch, "send_gain").device_info

    @property
    def name(self) -> str:
        parts = [track_entity_prefix(2, self._aux)]
        aux_name = aux_display_name(self._coordinator, self._aux)
        if aux_name:
            parts.append(aux_name)
        parts.append("Send Gain")
        return " ".join(parts)

    @property
    def available(self) -> bool:
        return self._coordinator.connected

    @property
    def native_value(self) -> float:
        state = self._coordinator.sends.get((0, self._ch, self._aux))
        return float(state.gain if state else -144.0)

    async def async_added_to_hass(self) -> None:
        from homeassistant.helpers.dispatcher import async_dispatcher_connect

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{self._coordinator.entry_id}_send_update",
                self._handle_send_update,
            )
        )

    def _handle_send_update(self, group: int, ch: int, aux: int) -> None:
        if group == 0 and ch == self._ch and aux == self._aux:
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        value = float(value)
        self._coordinator.ensure_send(0, self._ch, self._aux).gain = value
        self._coordinator.client.send(
            "/Set/Aux/Send/Gain",
            [OscArg("i", 0), OscArg("i", self._ch), OscArg("i", self._aux), OscArg("d", value)],
        )
        self.async_write_ha_state()