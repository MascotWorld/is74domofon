"""Config flow for IS74 Domofon integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_API_URL, DEFAULT_API_URL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_URL, default=DEFAULT_API_URL): str,
    }
)


class IS74DomofonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IS74 Domofon."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_url = user_input[CONF_API_URL]
            
            # Test connection
            session = async_get_clientsession(self.hass)
            try:
                async with session.get(f"{api_url}/status", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "running":
                            # Connection successful
                            await self.async_set_unique_id(api_url)
                            self._abort_if_unique_id_configured()
                            
                            return self.async_create_entry(
                                title="IS74 Домофон",
                                data=user_input,
                            )
                        else:
                            errors["base"] = "service_not_ready"
                    elif response.status == 401:
                        errors["base"] = "auth_required"
                    else:
                        errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> IS74DomofonOptionsFlow:
        """Get options flow."""
        return IS74DomofonOptionsFlow(config_entry)


class IS74DomofonOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for IS74 Domofon."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=self.config_entry.options.get("scan_interval", 30),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                    vol.Optional(
                        "auto_open_enabled",
                        default=self.config_entry.options.get("auto_open_enabled", False),
                    ): bool,
                }
            ),
        )

