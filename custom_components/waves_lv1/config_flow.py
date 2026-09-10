"""Config flow for the Waves eMotion LV1, ported from config.ts.

Presents a dropdown of zDNS-discovered LV1s plus a manual host/port override
(port ``0`` means "auto-discover the port for this host"), then validates the
choice with a real TCP handshake before the entry is created.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import CONF_SELECTED, DOMAIN, HANDSHAKE_ACK_TIMEOUT, ZDNS_DEFAULT_TIMEOUT
from .protocol.discovery import DiscoveryEntry, discover
from .protocol.tcp_client import LV1TcpClient

_LOGGER = logging.getLogger(__name__)

MANUAL_ENTRY = "__manual__"
CONNECT_VALIDATE_TIMEOUT = HANDSHAKE_ACK_TIMEOUT + 2.0


async def _async_try_connect(host: str, port: int) -> bool:
    """Open a handshake with the LV1 and report whether it registered."""
    result: asyncio.Future[bool] = asyncio.get_event_loop().create_future()

    def on_registered(*_args: Any) -> None:
        if not result.done():
            result.set_result(True)

    def on_error(*_args: Any) -> None:
        if not result.done():
            result.set_result(False)

    client = LV1TcpClient(host, port, auto_reconnect=False)
    client.on("registered", on_registered)
    client.on("error", on_error)
    try:
        await client.connect()
        return await asyncio.wait_for(result, timeout=CONNECT_VALIDATE_TIMEOUT)
    except TimeoutError:
        return False
    finally:
        client.disconnect()


class WavesLv1ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Waves eMotion LV1."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, DiscoveryEntry] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show discovered LV1s and a manual override, then validate the pick."""
        errors: dict[str, str] = {}

        if not self._discovered:
            try:
                entries = await discover(timeout=ZDNS_DEFAULT_TIMEOUT)
            except OSError:
                entries = []
            for entry in entries:
                if not entry.host or not entry.port:
                    continue
                label = f"{entry.host} ({entry.addresses[0] if entry.addresses else entry.source}:{entry.port})"
                self._discovered[label] = entry
            if not self._discovered:
                errors["base"] = "no_devices_found"

        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            port = user_input.get(CONF_PORT) or 0
            selected = user_input.get(CONF_SELECTED)

            if not host and selected and selected != MANUAL_ENTRY:
                entry = self._discovered.get(selected)
                if entry is not None:
                    host = entry.addresses[0] if entry.addresses else entry.source
                    port = entry.port or 0

            if not host:
                errors["base"] = "cannot_connect"
            elif not port:
                # Port 0 = auto-discover: narrow a fresh discovery pass to this host.
                found = await discover(timeout=ZDNS_DEFAULT_TIMEOUT, filter_host_ip=host)
                port = found[0].port if found and found[0].port else 0
                if not port:
                    errors["base"] = "cannot_connect"

            if not errors:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured()
                if await _async_try_connect(host, port):
                    return self.async_create_entry(
                        title=f"Waves LV1 ({host})",
                        data={CONF_HOST: host, CONF_PORT: port},
                    )
                errors["base"] = "cannot_connect"

        schema: dict[Any, Any] = {}
        if self._discovered:
            options = list(self._discovered) + [MANUAL_ENTRY]
            schema[vol.Optional(CONF_SELECTED, default=next(iter(self._discovered)))] = vol.In(options)
        schema[vol.Optional(CONF_HOST, default="")] = str
        schema[vol.Optional(CONF_PORT, default=0)] = int

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(schema),
            errors=errors,
        )
