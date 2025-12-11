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

from .const import DOMAIN, CONF_API_URL, CONF_PHONE

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("use_embedded_server", default=True): bool,
        vol.Optional("server_port", default=10777): int,
        vol.Optional(CONF_API_URL, default=""): str,
        vol.Optional("auto_start_fcm", default=True): bool,
    }
)


class IS74DomofonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IS74 Domofon."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}
        self._api_url: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - server setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            use_embedded = user_input.get("use_embedded_server", True)
            api_url = user_input.get(CONF_API_URL, "")
            port = user_input.get("server_port", 10777)
            
            # Store config for later
            self._data = {
                "use_embedded_server": use_embedded,
                "server_port": port,
                "auto_start_fcm": user_input.get("auto_start_fcm", True),
            }
            
            if use_embedded:
                self._api_url = f"http://localhost:{port}"
                self._data[CONF_API_URL] = self._api_url
                
                # Start embedded server temporarily for auth
                try:
                    from .server import setup_server
                    await setup_server(self.hass, port=port)
                    _LOGGER.info(f"Started embedded server on port {port} for auth")
                except Exception as e:
                    _LOGGER.error(f"Failed to start server: {e}")
                    errors["base"] = "server_start_failed"
                    return self.async_show_form(
                        step_id="user",
                        data_schema=STEP_USER_DATA_SCHEMA,
                        errors=errors,
                    )
                
                # Go to phone step
                return await self.async_step_phone()
            else:
                # External server
                if not api_url:
                    errors["base"] = "no_url"
                else:
                    self._api_url = api_url
                    self._data[CONF_API_URL] = api_url
                    
                    # Test connection
                    session = async_get_clientsession(self.hass)
                    try:
                        async with session.get(f"{api_url}/status", timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                if data.get("authenticated"):
                                    # Already authenticated, skip auth steps
                                    await self.async_set_unique_id(api_url)
                                    self._abort_if_unique_id_configured()
                                    return self.async_create_entry(
                                        title="IS74 Домофон",
                                        data=self._data,
                                    )
                                else:
                                    # Need authentication
                                    return await self.async_step_phone()
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
                "default_port": "10777",
            },
        )

    async def async_step_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle phone number input step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input.get(CONF_PHONE, "").strip()
            
            if not phone:
                errors["base"] = "phone_required"
            else:
                # Request SMS code
                session = async_get_clientsession(self.hass)
                try:
                    async with session.post(
                        f"{self._api_url}/auth/login",
                        json={"phone": phone},
                        timeout=30
                    ) as response:
                        if response.status == 200:
                            self._data[CONF_PHONE] = phone
                            return await self.async_step_code()
                        else:
                            result = await response.json()
                            error_msg = result.get("error", "Unknown error")
                            _LOGGER.error(f"Failed to request code: {error_msg}")
                            errors["base"] = "sms_failed"
                except aiohttp.ClientError as e:
                    _LOGGER.error(f"Connection error: {e}")
                    errors["base"] = "cannot_connect"
                except Exception as e:
                    _LOGGER.exception(f"Unexpected error: {e}")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="phone",
            data_schema=vol.Schema({
                vol.Required(CONF_PHONE): str,
            }),
            errors=errors,
            description_placeholders={
                "api_url": self._api_url,
            },
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle SMS code verification step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = user_input.get("code", "").strip()
            
            if not code:
                errors["base"] = "code_required"
            else:
                # Verify SMS code
                session = async_get_clientsession(self.hass)
                try:
                    async with session.post(
                        f"{self._api_url}/auth/verify",
                        json={
                            "phone": self._data.get(CONF_PHONE),
                            "code": code
                        },
                        timeout=30
                    ) as response:
                        if response.status == 200:
                            # Success! Create entry
                            port = self._data.get("server_port", 10777)
                            await self.async_set_unique_id(f"is74_domofon_{port}")
                            self._abort_if_unique_id_configured()
                            
                            return self.async_create_entry(
                                title="IS74 Домофон",
                                data=self._data,
                            )
                        else:
                            result = await response.json()
                            error_msg = result.get("error", "Invalid code")
                            _LOGGER.error(f"Code verification failed: {error_msg}")
                            errors["base"] = "invalid_code"
                except aiohttp.ClientError as e:
                    _LOGGER.error(f"Connection error: {e}")
                    errors["base"] = "cannot_connect"
                except Exception as e:
                    _LOGGER.exception(f"Unexpected error: {e}")
                    errors["base"] = "unknown"

        phone = self._data.get(CONF_PHONE, "")
        # Mask phone for display
        masked_phone = phone[:3] + "****" + phone[-2:] if len(phone) > 5 else phone

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({
                vol.Required("code"): str,
            }),
            errors=errors,
            description_placeholders={
                "phone": masked_phone,
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

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle re-authentication."""
        return await self.async_step_reauth_phone()

    async def async_step_reauth_phone(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle phone input for re-auth."""
        errors: dict[str, str] = {}

        api_url = self.config_entry.data.get(CONF_API_URL, "http://localhost:10777")

        if user_input is not None:
            phone = user_input.get(CONF_PHONE, "").strip()
            
            if phone:
                session = async_get_clientsession(self.hass)
                try:
                    async with session.post(
                        f"{api_url}/auth/login",
                        json={"phone": phone},
                        timeout=30
                    ) as response:
                        if response.status == 200:
                            self._phone = phone
                            return await self.async_step_reauth_code()
                        else:
                            errors["base"] = "sms_failed"
                except Exception:
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_phone",
            data_schema=vol.Schema({
                vol.Required(CONF_PHONE): str,
            }),
            errors=errors,
        )

    async def async_step_reauth_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle code verification for re-auth."""
        errors: dict[str, str] = {}

        api_url = self.config_entry.data.get(CONF_API_URL, "http://localhost:10777")

        if user_input is not None:
            code = user_input.get("code", "").strip()
            
            if code:
                session = async_get_clientsession(self.hass)
                try:
                    async with session.post(
                        f"{api_url}/auth/verify",
                        json={"phone": self._phone, "code": code},
                        timeout=30
                    ) as response:
                        if response.status == 200:
                            return self.async_create_entry(title="", data={})
                        else:
                            errors["base"] = "invalid_code"
                except Exception:
                    errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="reauth_code",
            data_schema=vol.Schema({
                vol.Required("code"): str,
            }),
            errors=errors,
        )
