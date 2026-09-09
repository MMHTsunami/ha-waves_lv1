"""Config flow for Waves eMotion LV1 integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DEFAULT_PORT, DOMAIN
from .discovery import async_discover_lv1

_LOGGER = logging.getLogger(__name__)


class WavesLV1ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Waves eMotion LV1."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow."""
        self._discovered_devices: dict[str, dict[str, Any]] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle initial step: choice between discovered devices or manual entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get("manual_entry"):
                return await self.async_step_manual()

            selected = user_input.get("device")
            if selected and selected in self._discovered_devices:
                device_data = self._discovered_devices[selected]
                await self.async_set_unique_id(
                    f"{device_data['host']}:{device_data['port']}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Waves LV1 ({device_data['host']})",
                    data={
                        "host": device_data["host"],
                        "port": device_data["port"],
                    },
                )

        # Trigger zDNS discovery scan
        discovered = await async_discover_lv1(timeout=3.0)
        self._discovered_devices = {
            f"{dev['host']}:{dev['port']}": dev for dev in discovered
        }

        if self._discovered_devices:
            choices = {
                key: f"{dev['host']}:{dev['port']} ({dev.get('host_name', 'LV1')})"
                for key, dev in self._discovered_devices.items()
            }
            choices["manual"] = "Manually configure IP / Port"

            schema = vol.Schema(
                {
                    vol.Required("device", default=list(choices.keys())[0]): vol.In(
                        choices
                    )
                }
            )
            return self.async_show_form(
                step_id="user", data_schema=schema, errors=errors
            )

        return await self.async_step_manual()

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle manual IP and Port configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input["host"].strip()
            port = user_input["port"]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Waves LV1 ({host})",
                data={"host": host, "port": port},
            )

        schema = vol.Schema(
            {
                vol.Required("host"): str,
                vol.Required("port", default=DEFAULT_PORT): int,
            }
        )

        return self.async_show_form(
            step_id="manual", data_schema=schema, errors=errors
        )
