"""Config flow for IS74 Domofon integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_API_URL, DEFAULT_API_URL

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("use_embedded_server", default=True): bool,
        vol.Optional("server_port", default=8099): int,
        vol.Optional(CONF_API_URL, default=""): str,
        vol.Optional("auto_start_fcm", default=True): bool,
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
            use_embedded = user_input.get("use_embedded_server", True)
            api_url = user_input.get(CONF_API_URL, "")
            port = user_input.get("server_port", 8099)
            
            if use_embedded:
                # Embedded server will start on setup
                await self.async_set_unique_id(f"is74_domofon_embedded_{port}")
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title="IS74 Домофон",
                    data={
                        "use_embedded_server": True,
                        "server_port": port,
                        CONF_API_URL: f"http://localhost:{port}",
                        "auto_start_fcm": user_input.get("auto_start_fcm", True),
                    },
                )
            else:
                # External server - test connection
                if not api_url:
                    errors["base"] = "no_url"
                else:
                    session = async_get_clientsession(self.hass)
                    try:
                        async with session.get(f"{api_url}/status", timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get("status") == "running":
                                    await self.async_set_unique_id(api_url)
                                    self._abort_if_unique_id_configured()
                                    
                                    return self.async_create_entry(
                                        title="IS74 Домофон",
                                        data={
                                            "use_embedded_server": False,
                                            CONF_API_URL: api_url,
                                            "auto_start_fcm": user_input.get("auto_start_fcm", True),
                                        },
                                    )
                                else:
                                    errors["base"] = "service_not_ready"
                            elif response.status == 401:
                                errors["base"] = "auth_required"
                            else:
                                errors["base"] = "cannot_connect"
                    except aiohttp.ClientError:
                        errors["base"] = "cannot_connect"
                    except Exception:
                        _LOGGER.exception("Unexpected exception")
                        errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_port": "8099",
            },
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
                    vol.Optional(
                        "auto_start_fcm",
                        default=self.config_entry.options.get(
                            "auto_start_fcm",
                            self.config_entry.data.get("auto_start_fcm", True)
                        ),
                    ): bool,
                }
            ),
        )
