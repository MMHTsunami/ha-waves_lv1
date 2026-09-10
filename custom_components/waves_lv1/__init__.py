"""The Waves eMotion LV1 integration.

Entity platforms are added in Phase 5; this sets up the coordinator (TCP
connection + `/Notify/...` state engine) so the config entry has a live link
to the LV1 as soon as it's added.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from homeassistant.const import CONF_HOST, CONF_PORT
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.core import ServiceCall

from .const import DOMAIN, SERVICE_FADE_FADER, SERVICE_SEND_RAW_OSC
from .coordinator import LV1Coordinator
from .protocol.osc import OscArg

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS: list[str] = ["button", "number", "select", "sensor", "switch", "text"]

_FADE_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Required("target"): vol.In(["out", "send"]),
        vol.Required("group"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Required("channel"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Optional("aux"): vol.All(vol.Coerce(int), vol.Range(min=0)),
        vol.Required("target_db"): vol.Coerce(float),
        vol.Required("duration_ms"): vol.All(vol.Coerce(int), vol.Range(min=0)),
    }
)
_RAW_OSC_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Required("address"): vol.All(cv.string, vol.Match(r"^/.*")),
        vol.Optional("args", default=[]): vol.Any([cv.string], cv.string),
    }
)


async def async_setup_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    """Set up Waves LV1 from a config entry."""
    coordinator = LV1Coordinator(
        hass, entry.entry_id, entry.data[CONF_HOST], entry.data[CONF_PORT]
    )
    await coordinator.async_connect()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: "HomeAssistant", entry: "ConfigEntry") -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: LV1Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.disconnect()
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_FADE_FADER)
            hass.services.async_remove(DOMAIN, SERVICE_SEND_RAW_OSC)
    return unloaded


def _register_services(hass: "HomeAssistant") -> None:
    """Register integration services once for the first config entry."""
    if not hass.services.has_service(DOMAIN, SERVICE_FADE_FADER):
        hass.services.async_register(DOMAIN, SERVICE_FADE_FADER, _async_fade_fader, schema=_FADE_SCHEMA)
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_RAW_OSC):
        hass.services.async_register(DOMAIN, SERVICE_SEND_RAW_OSC, _async_send_raw_osc, schema=_RAW_OSC_SCHEMA)


def _get_coordinator(hass: "HomeAssistant", call: ServiceCall) -> LV1Coordinator | None:
    """Resolve a requested entry, or the only configured entry."""
    coordinators: dict[str, LV1Coordinator] = hass.data.get(DOMAIN, {})
    entry_id = call.data.get("entry_id")
    if entry_id:
        return coordinators.get(entry_id)
    return next(iter(coordinators.values()), None)


async def _async_fade_fader(call: ServiceCall) -> None:
    """Ramp a track output or input-to-aux send gain in dB."""
    coordinator = _get_coordinator(call.hass, call)
    if coordinator is None:
        return
    target = call.data["target"]
    group = int(call.data["group"])
    channel = int(call.data["channel"])
    aux = call.data.get("aux")
    if target == "send":
        if aux is None:
            raise vol.Invalid("aux is required when target is send")
        current = coordinator.ensure_send(group, channel, int(aux)).gain
    else:
        current = coordinator.ensure_channel(group, channel).gain
    destination = float(call.data["target_db"])
    duration_ms = int(call.data["duration_ms"])
    steps = max(1, duration_ms // 30) if duration_ms else 1
    for step in range(1, steps + 1):
        value = current + (destination - current) * step / steps
        if target == "send":
            coordinator.ensure_send(group, channel, int(aux)).gain = value
            address = "/Set/Aux/Send/Gain"
            args = [OscArg("i", group), OscArg("i", channel), OscArg("i", int(aux)), OscArg("d", value)]
        else:
            coordinator.ensure_channel(group, channel).gain = value
            address = "/Set/Track/Out/Gain"
            args = [OscArg("i", group), OscArg("i", channel), OscArg("d", value)]
        coordinator.client.send(address, args)
        if step < steps:
            await asyncio.sleep(duration_ms / steps / 1000)


async def _async_send_raw_osc(call: ServiceCall) -> None:
    """Parse and send typed OSC arguments from a service call."""
    coordinator = _get_coordinator(call.hass, call)
    if coordinator is None:
        return
    args: list[OscArg] = []
    raw_args = call.data.get("args", [])
    tokens = raw_args.split() if isinstance(raw_args, str) else raw_args
    for token in tokens:
        match = re.fullmatch(r"([ifsdhTFNI]):?(.*)", token)
        if match is None:
            raise vol.Invalid(f"Invalid OSC argument: {token}")
        arg_type, value = match.groups()
        if arg_type == "i":
            args.append(OscArg("i", int(value)))
        elif arg_type in ("f", "d"):
            args.append(OscArg(arg_type, float(value)))
        elif arg_type == "s":
            args.append(OscArg("s", value))
        elif arg_type in ("T", "F", "N", "I"):
            if value:
                raise vol.Invalid(f"OSC constant cannot have a value: {token}")
            args.append(OscArg(arg_type))
        else:
            raise vol.Invalid(f"Unsupported OSC argument: {token}")
    coordinator.client.send(call.data["address"], args)

