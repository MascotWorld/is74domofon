"""Config flow for IS74 Domofon integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api_wrapper import get_cameras, get_devices, load_tokens, request_auth_code, verify_auth_code
from .const import CONF_NAME_OVERRIDES, CONF_PHONE, CONF_SELECTED_ACCOUNTS, DOMAIN

_LOGGER = logging.getLogger(__name__)

def _confirmation_hint(result: dict[str, Any] | None) -> str:
    """Return a user-facing confirmation hint."""
    if not result:
        return "Введите последние 4 цифры номера, с которого поступил звонок."

    if result.get("confirmType") == 1:
        return "Введите последние 4 цифры номера, с которого поступил звонок."

    return "Введите код из SMS."


def _request_error_code(err: Exception) -> str:
    """Map request-auth exceptions to Home Assistant error keys."""
    message = str(err).lower()
    if "429" in message or "too many requests" in message:
        return "rate_limited"
    if "wait a minute" in message or "получили ранее" in message:
        return "confirmation_cooldown"
    return "sms_failed"


def _verify_error_code(err: Exception) -> str:
    """Map verify-auth exceptions to Home Assistant error keys."""
    message = str(err).lower()
    if "no authid available" in message:
        return "confirmation_expired"
    return "invalid_code"


def _account_label(account: dict[str, Any]) -> str:
    """Return a readable account label."""
    address = account.get("address") or f"USER_ID {account.get('user_id')}"
    suffix = f"#{account.get('user_id')}"
    if account.get("is_primary"):
        return f"{address} [основной, {suffix}]"
    return f"{address} [{suffix}]"


def _filter_by_selected_accounts(
    items: list[dict[str, Any]], selected_accounts: set[str]
) -> list[dict[str, Any]]:
    """Filter devices or cameras by selected account IDs."""
    if not selected_accounts:
        return items

    return [
        item for item in items if str(item.get("account_user_id")) in selected_accounts
    ]


class IS74DomofonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IS74 Domofon."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._data: dict[str, Any] = {}
        self._phone: str | None = None
        self._accounts: list[dict[str, Any]] = []
        self._account_field_map: dict[str, str] = {}
        self._confirmation_hint = _confirmation_hint(None)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        return await self.async_step_phone(user_input)

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
                try:
                    await self.async_set_unique_id(DOMAIN)
                    self._abort_if_unique_id_configured()

                    result = await request_auth_code(phone)
                    self._phone = phone
                    self._data[CONF_PHONE] = phone
                    self._confirmation_hint = _confirmation_hint(result)
                    return await self.async_step_code()
                except Exception as err:
                    _LOGGER.error("Failed to request confirmation code: %s", err)
                    errors["base"] = _request_error_code(err)

        return self.async_show_form(
            step_id="phone",
            data_schema=vol.Schema({vol.Required(CONF_PHONE): str}),
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle confirmation code verification step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = user_input.get("code", "").strip()

            if not code:
                errors["base"] = "code_required"
            else:
                try:
                    result = await verify_auth_code(self._phone or self._data[CONF_PHONE], code)
                    self._accounts = result.get("accounts", [])
                    if self._accounts:
                        return await self.async_step_accounts()

                    return self.async_create_entry(
                        title="IS74 Домофон",
                        data=self._data,
                    )
                except Exception as err:
                    _LOGGER.error("Code verification failed: %s", err)
                    errors["base"] = _verify_error_code(err)

        phone = self._data.get(CONF_PHONE, "")
        masked_phone = phone[:3] + "****" + phone[-2:] if len(phone) > 5 else phone

        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders={
                "phone": masked_phone,
                "verification_hint": self._confirmation_hint,
            },
        )

    async def async_step_accounts(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Choose which account addresses to include."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_accounts = [
                user_id
                for label, user_id in self._account_field_map.items()
                if user_input.get(label, True)
            ]
            if not selected_accounts:
                errors["base"] = "no_account_selected"
            else:
                self._data[CONF_SELECTED_ACCOUNTS] = selected_accounts
                return self.async_create_entry(
                    title="IS74 Домофон",
                    data=self._data,
                )

        self._account_field_map = {}
        schema_fields: dict[Any, Any] = {}
        selected_accounts = {
            str(item)
            for item in self._data.get(
                CONF_SELECTED_ACCOUNTS,
                [account.get("user_id") for account in self._accounts],
            )
        }

        for account in self._accounts:
            label = _account_label(account)
            self._account_field_map[label] = str(account.get("user_id"))
            schema_fields[
                vol.Optional(
                    label,
                    default=str(account.get("user_id")) in selected_accounts,
                )
            ] = bool

        return self.async_show_form(
            step_id="accounts",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "IS74DomofonOptionsFlow":
        """Get options flow."""
        return IS74DomofonOptionsFlow(config_entry)


class IS74DomofonOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for IS74 Domofon."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._phone: str | None = None
        self._data = dict(config_entry.options)
        self._account_field_map: dict[str, str] = {}
        self._rename_field_map: dict[str, str] = {}
        self._confirmation_hint = _confirmation_hint(None)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_accounts = [
                user_id
                for label, user_id in self._account_field_map.items()
                if user_input.get(label, True)
            ]
            if self._account_field_map and not selected_accounts:
                errors["base"] = "no_account_selected"
            else:
                self._data = {
                    "scan_interval": user_input.get(
                        "scan_interval",
                        self.config_entry.options.get("scan_interval", 30),
                    ),
                    CONF_SELECTED_ACCOUNTS: selected_accounts,
                    CONF_NAME_OVERRIDES: self.config_entry.options.get(CONF_NAME_OVERRIDES, {}),
                }
                return await self.async_step_entity_names()

        tokens = await load_tokens() or {}
        accounts = tokens.get("accounts", [])
        self._account_field_map = {}

        schema_fields: dict[Any, Any] = {
            vol.Optional(
                "scan_interval",
                default=self.config_entry.options.get("scan_interval", 30),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
        }

        selected_accounts = {
            str(item)
            for item in self.config_entry.options.get(
                CONF_SELECTED_ACCOUNTS,
                self.config_entry.data.get(CONF_SELECTED_ACCOUNTS, []),
            )
        }
        if not selected_accounts:
            selected_accounts = {str(account.get("user_id")) for account in accounts}

        for account in accounts:
            label = _account_label(account)
            self._account_field_map[label] = str(account.get("user_id"))
            schema_fields[
                vol.Optional(
                    label,
                    default=str(account.get("user_id")) in selected_accounts,
                )
            ] = bool

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    async def async_step_entity_names(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure friendly names for cameras and intercoms."""
        if user_input is not None:
            overrides = dict(self._data.get(CONF_NAME_OVERRIDES, {}))
            for label, override_key in self._rename_field_map.items():
                value = (user_input.get(label) or "").strip()
                if value:
                    overrides[override_key] = value
                else:
                    overrides.pop(override_key, None)

            self._data[CONF_NAME_OVERRIDES] = overrides
            return self.async_create_entry(title="", data=self._data)

        selected_accounts = {
            str(item) for item in self._data.get(CONF_SELECTED_ACCOUNTS, [])
        }
        devices = _filter_by_selected_accounts(await get_devices(), selected_accounts)
        cameras = _filter_by_selected_accounts(await get_cameras(), selected_accounts)
        existing_overrides = self.config_entry.options.get(CONF_NAME_OVERRIDES, {})

        self._rename_field_map = {}
        schema_fields: dict[Any, Any] = {}

        for device in devices:
            label = (
                f"Домофон: {device.get('name')} "
                f"[{device.get('address') or device.get('id')}, {device.get('id')}]"
            )
            self._rename_field_map[label] = f"device:{device['id']}"
            schema_fields[
                vol.Optional(
                    label,
                    default=existing_overrides.get(f"device:{device['id']}", device.get("name", "")),
                )
            ] = str

        for camera in cameras:
            label = (
                f"Камера: {camera.get('name')} "
                f"[{camera.get('address') or camera.get('uuid')}, {camera.get('uuid')[:8]}]"
            )
            self._rename_field_map[label] = f"camera:{camera['uuid']}"
            schema_fields[
                vol.Optional(
                    label,
                    default=existing_overrides.get(f"camera:{camera['uuid']}", camera.get("name", "")),
                )
            ] = str

        if not schema_fields:
            return self.async_create_entry(title="", data=self._data)

        return self.async_show_form(
            step_id="entity_names",
            data_schema=vol.Schema(schema_fields),
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

        if user_input is not None:
            phone = user_input.get(CONF_PHONE, "").strip()
            if not phone:
                errors["base"] = "phone_required"
            else:
                try:
                    result = await request_auth_code(phone)
                    self._phone = phone
                    self._confirmation_hint = _confirmation_hint(result)
                    return await self.async_step_reauth_code()
                except Exception as err:
                    _LOGGER.error("Failed to request re-auth confirmation code: %s", err)
                    errors["base"] = _request_error_code(err)

        return self.async_show_form(
            step_id="reauth_phone",
            data_schema=vol.Schema({vol.Required(CONF_PHONE): str}),
            errors=errors,
        )

    async def async_step_reauth_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle code verification for re-auth."""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = user_input.get("code", "").strip()
            if not code:
                errors["base"] = "code_required"
            else:
                try:
                    await verify_auth_code(self._phone or "", code)
                    return self.async_create_entry(title="", data={})
                except Exception as err:
                    _LOGGER.error("Re-auth verification failed: %s", err)
                    errors["base"] = _verify_error_code(err)

        return self.async_show_form(
            step_id="reauth_code",
            data_schema=vol.Schema({vol.Required("code"): str}),
            errors=errors,
            description_placeholders={"verification_hint": self._confirmation_hint},
        )
