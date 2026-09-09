"""Switch platform for Waves eMotion LV1 (Mutes, Solos, and Mute Groups)."""
from __future__ import annotations

import struct
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up Mute, Solo, and Mute Group entities."""
    coordinator: LV1DataUpdateCoordinator = hass.data["waves_lv1"][entry.entry_id]

    entities: list[SwitchEntity] = []

    # Expose Channels 1-80 Mute & Solo
    for ch in range(1, 81):
        entities.append(LV1ChannelMuteSwitch(coordinator, group=0, ch=ch - 1))
        entities.append(LV1ChannelSoloSwitch(coordinator, group=0, ch=ch - 1))

    # Expose Mute Groups 1-8
    for mg in range(8):
        entities.append(LV1MuteGroupSwitch(coordinator, group_idx=mg))

    async_add_entities(entities)


class LV1ChannelMuteSwitch(CoordinatorEntity[LV1DataUpdateCoordinator], SwitchEntity):
    """Mute toggle switch for a specific channel."""

    def __init__(
        self, coordinator: LV1DataUpdateCoordinator, group: int, ch: int
    ) -> None:
        super().__init__(coordinator)
        self.group = group
        self.ch = ch
        self._attr_name = f"LV1 Channel {ch + 1} Mute"
        self._attr_unique_id = (
            f"{coordinator.host}_mute_{self.group}_{self.ch}"
        )

    @property
    def is_on(self) -> bool:
        """Return True if channel is muted."""
        key = f"{self.group}.{self.ch}"
        return self.coordinator.channels.get(key, {}).get("muted", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute channel."""
        # /Set/Track/Mute ,iiii [group, ch, 1, 0]
        payload = struct.pack(">iiii", self.group, self.ch, 1, 0)
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Track/Mute", payload
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute channel."""
        payload = struct.pack(">iiii", self.group, self.ch, 0, 0)
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Track/Mute", payload
        )


class LV1ChannelSoloSwitch(CoordinatorEntity[LV1DataUpdateCoordinator], SwitchEntity):
    """Solo toggle switch for a specific channel."""

    def __init__(
        self, coordinator: LV1DataUpdateCoordinator, group: int, ch: int
    ) -> None:
        super().__init__(coordinator)
        self.group = group
        self.ch = ch
        self._attr_name = f"LV1 Channel {ch + 1} Solo"
        self._attr_unique_id = (
            f"{coordinator.host}_solo_{self.group}_{self.ch}"
        )

    @property
    def is_on(self) -> bool:
        key = f"{self.group}.{self.ch}"
        return self.coordinator.channels.get(key, {}).get("solo", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        payload = struct.pack(">iiii", self.group, self.ch, 1, 0)
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Track/Solo", payload
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        payload = struct.pack(">iiii", self.group, self.ch, 0, 0)
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Track/Solo", payload
        )


class LV1MuteGroupSwitch(CoordinatorEntity[LV1DataUpdateCoordinator], SwitchEntity):
    """Mute Group toggle switch (1-8)."""

    def __init__(
        self, coordinator: LV1DataUpdateCoordinator, group_idx: int
    ) -> None:
        super().__init__(coordinator)
        self.group_idx = group_idx
        self._attr_name = f"LV1 Mute Group {group_idx + 1}"
        self._attr_unique_id = f"{coordinator.host}_mutegroup_{group_idx}"

    @property
    def is_on(self) -> bool:
        return self.coordinator.mute_groups.get(self.group_idx, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        # Group index 13 multiplexes Mute Groups in LV1
        payload = struct.pack(">iiii", 13, self.group_idx, 1, 0)
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Track/Mute", payload
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        payload = struct.pack(">iiii", 13, self.group_idx, 0, 0)
        await self.coordinator.osc_client.send_raw_osc(
            "/Set/Track/Mute", payload
        )
