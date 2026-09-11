"""Diagnostics support for the Waves LV1 integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry

from .coordinator import LV1Coordinator


async def async_get_config_entry_diagnostics(
    hass: Any, entry: ConfigEntry
) -> dict[str, Any]:
    """Return a compact diagnostic snapshot of the current LV1 state."""
    coordinator: LV1Coordinator = hass.data["waves_lv1"][entry.entry_id]
    tracks: dict[tuple[int, int], dict[str, Any]] = {}
    for (group, ch), state in coordinator.channels.items():
        tracks[(group, ch)] = {
            "muted": state.muted,
            "gain": state.gain,
            "solo": state.solo,
            "name": state.name,
            "pan": state.pan,
            "width": state.width,
            "color": list(state.color) if state.color is not None else None,
            "meter": state.meter,
        }

    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "unique_id": entry.unique_id,
        "host": coordinator.host,
        "port": coordinator.port,
        "connected": coordinator.connected,
        "topology": {
            "channels": coordinator.detected.channels,
            "auxes": coordinator.detected.auxes,
            "aux_names": coordinator.detected.aux_names,
        },
        "tracks": tracks,
        "sends": {
            (group, ch, aux): {
                "on": send.on,
                "gain": send.gain,
            }
            for (group, ch, aux), send in coordinator.sends.items()
        },
        "mute_groups": dict(sorted(coordinator.mute_groups.items())),
        "scene": {
            "current_scene": coordinator.current_scene,
            "current_scene_name": coordinator.current_scene_name,
            "scene_names": dict(sorted(coordinator.scenes.items())),
        },
        "tempo": coordinator.current_tempo,
        "flip": None
        if coordinator.current_flip_target is None
        else {
            "group": coordinator.current_flip_target.group,
            "ch": coordinator.current_flip_target.ch,
        },
        "user_keys": {
            idx: {
                "name": info.name,
                "func": info.func,
                "assigned": info.assigned,
            }
            for idx, info in sorted(coordinator.user_keys.items())
        },
    }
