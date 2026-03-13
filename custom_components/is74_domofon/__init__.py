"""IS74 Domofon integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api_wrapper import (
    get_cameras as api_get_cameras,
    get_devices as api_get_devices,
    get_fcm_status as api_get_fcm_status,
    get_video_stream as api_get_video_stream,
    load_tokens,
    open_door as api_open_door,
    refresh_fcm_registration,
    request_auth_code as api_request_auth_code,
    set_fcm_notification_callback,
    start_fcm as api_start_fcm,
    stop_fcm as api_stop_fcm,
    verify_auth_code as api_verify_auth_code,
)
from .const import (
    ATTR_DEVICE_ID,
    CONF_NAME_OVERRIDES,
    CONF_SELECTED_ACCOUNTS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_DOOR_OPENED,
    EVENT_INCOMING_CALL,
    PLATFORMS,
    SERVICE_OPEN_DOOR,
    SERVICE_START_FCM,
    SERVICE_STOP_FCM,
)

_LOGGER = logging.getLogger(__name__)

FCM_MAINTENANCE_INTERVAL = timedelta(hours=12)
FCM_RETRY_DELAY = timedelta(minutes=15)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IS74 Domofon from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    client = IS74DomofonClient(hass, entry)
    coordinator = IS74DomofonCoordinator(hass, client)

    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await client.async_setup()

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning(
            "Initial data fetch failed (this is OK if not authenticated yet): %s",
            err,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    if client.auto_start_fcm:
        await client.async_maintenance(force=True)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    runtime = hass.data[DOMAIN].get(entry.entry_id, {})
    client: IS74DomofonClient | None = runtime.get("client")
    if client is not None:
        await client.async_unload()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for IS74 Domofon."""
    if hass.data[DOMAIN].get("services_registered"):
        return

    def _get_first_client() -> IS74DomofonClient:
        for key, value in hass.data[DOMAIN].items():
            if key == "services_registered":
                continue
            client = value.get("client")
            if client is not None:
                return client
        raise RuntimeError("IS74 Domofon is not configured")

    async def handle_open_door(call: ServiceCall) -> None:
        """Handle open door service call."""
        client = _get_first_client()
        device_id = call.data.get(ATTR_DEVICE_ID)
        if not device_id:
            return

        result = await client.open_door(device_id)
        if result.get("success"):
            hass.bus.async_fire(EVENT_DOOR_OPENED, {"device_id": device_id})

    async def handle_start_fcm(call: ServiceCall) -> None:
        """Handle start FCM service call."""
        client = _get_first_client()
        await client.start_fcm()

    async def handle_stop_fcm(call: ServiceCall) -> None:
        """Handle stop FCM service call."""
        client = _get_first_client()
        await client.stop_fcm()

    hass.services.async_register(DOMAIN, SERVICE_OPEN_DOOR, handle_open_door)
    hass.services.async_register(DOMAIN, SERVICE_START_FCM, handle_start_fcm)
    hass.services.async_register(DOMAIN, SERVICE_STOP_FCM, handle_stop_fcm)
    hass.data[DOMAIN]["services_registered"] = True


class IS74DomofonClient:
    """Direct Home Assistant client for the IS74 API wrapper."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the client."""
        self.hass = hass
        self.entry = entry
        self._fcm_manually_paused = False
        self._maintenance_lock = asyncio.Lock()
        self._last_fcm_maintenance: Any = None
        self._next_fcm_retry_at: Any = None

    @property
    def auto_start_fcm(self) -> bool:
        """Return whether FCM should be kept alive automatically."""
        return True

    @property
    def selected_account_ids(self) -> set[str]:
        """Return the selected account user IDs."""
        selected = self.entry.options.get(
            CONF_SELECTED_ACCOUNTS,
            self.entry.data.get(CONF_SELECTED_ACCOUNTS, []),
        )
        return {str(item) for item in selected or []}

    @property
    def name_overrides(self) -> dict[str, str]:
        """Return configured entity name overrides."""
        return self.entry.options.get(CONF_NAME_OVERRIDES, {})

    async def async_setup(self) -> None:
        """Initialize runtime callbacks."""
        set_fcm_notification_callback(self._handle_fcm_notification)

    async def async_unload(self) -> None:
        """Tear down runtime callbacks."""
        set_fcm_notification_callback(None)
        await self.stop_fcm()

    async def get_status(self) -> dict[str, Any]:
        """Get integration status."""
        tokens = await load_tokens()
        authenticated = bool(tokens and tokens.get("access_token"))
        return {
            "status": "running" if authenticated else "awaiting_auth",
            "authenticated": authenticated,
            "version": "1.2.0",
            "components": {
                "runtime": "direct_home_assistant",
                "auto_start_fcm": self.auto_start_fcm,
            },
        }

    async def request_auth_code(self, phone: str) -> dict[str, Any]:
        """Request a login confirmation code or phone call."""
        return await api_request_auth_code(phone)

    async def verify_auth_code(self, phone: str, code: str) -> dict[str, Any]:
        """Verify the confirmation code and persist the access token."""
        result = await api_verify_auth_code(phone, code)
        self._next_fcm_retry_at = None
        self._last_fcm_maintenance = None

        if self.auto_start_fcm:
            await self.async_maintenance(force=True)

        return result

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get intercom devices."""
        devices = await api_get_devices()
        selected = self.selected_account_ids
        if selected:
            devices = [
                device
                for device in devices
                if str(device.get("account_user_id")) in selected
            ]

        overrides = self.name_overrides
        return [
            {
                **device,
                "name": overrides.get(f"device:{device['id']}", device.get("name")),
            }
            for device in devices
        ]

    async def get_cameras(self) -> list[dict[str, Any]]:
        """Get cameras."""
        cameras = await api_get_cameras()
        selected = self.selected_account_ids
        if selected:
            cameras = [
                camera
                for camera in cameras
                if str(camera.get("account_user_id")) in selected
            ]

        overrides = self.name_overrides
        return [
            {
                **camera,
                "name": overrides.get(f"camera:{camera['uuid']}", camera.get("name")),
            }
            for camera in cameras
        ]

    async def open_door(self, device_id: str) -> dict[str, Any]:
        """Open a door relay."""
        return await api_open_door(device_id)

    async def get_video_stream(self, camera_uuid: str) -> dict[str, Any]:
        """Get a video stream URL."""
        return await api_get_video_stream(camera_uuid)

    async def get_fcm_status(self) -> dict[str, Any]:
        """Get FCM status."""
        return await api_get_fcm_status()

    async def start_fcm(self) -> dict[str, Any]:
        """Start the FCM listener."""
        self._fcm_manually_paused = False
        result = await api_start_fcm()
        self._last_fcm_maintenance = dt_util.utcnow()
        self._next_fcm_retry_at = None
        return result

    async def stop_fcm(self) -> dict[str, Any]:
        """Stop the FCM listener."""
        self._fcm_manually_paused = True
        return await api_stop_fcm()

    async def async_maintenance(self, force: bool = False) -> None:
        """Refresh weekly FCM registration and revive the listener if needed."""
        tokens = await load_tokens()
        if not tokens or not tokens.get("access_token"):
            return

        status = await self.get_fcm_status()
        should_keep_fcm_alive = (
            (self.auto_start_fcm and not self._fcm_manually_paused)
            or status.get("listener_running", False)
        )
        if not should_keep_fcm_alive:
            return

        now = dt_util.utcnow()
        if not force:
            if self._next_fcm_retry_at and now < self._next_fcm_retry_at:
                return

            if status.get("listener_running") and self._last_fcm_maintenance:
                if now - self._last_fcm_maintenance < FCM_MAINTENANCE_INTERVAL:
                    return

        async with self._maintenance_lock:
            status = await self.get_fcm_status()
            try:
                if status.get("listener_running"):
                    await refresh_fcm_registration(force_restart_listener=True)
                else:
                    await self.start_fcm()

                self._last_fcm_maintenance = dt_util.utcnow()
                self._next_fcm_retry_at = None
            except Exception as err:
                self._next_fcm_retry_at = dt_util.utcnow() + FCM_RETRY_DELAY
                _LOGGER.warning("FCM maintenance failed: %s", err)

    def _handle_fcm_notification(self, call_data: dict[str, Any]) -> None:
        """Bridge FCM callbacks into the Home Assistant event loop."""
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_handle_fcm_notification(call_data),
        )

    async def _async_handle_fcm_notification(self, call_data: dict[str, Any]) -> None:
        """Fire Home Assistant events for incoming calls."""
        event_data = {
            "device_id": call_data.get("device_id"),
            "relay_id": call_data.get("relay_id"),
            "address": call_data.get("address"),
            "entrance": call_data.get("entrance"),
            "notification": call_data.get("notification"),
            "data": call_data.get("data"),
        }

        self.hass.bus.async_fire(EVENT_INCOMING_CALL, event_data)


class IS74DomofonCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage data updates."""

    def __init__(self, hass: HomeAssistant, client: IS74DomofonClient) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the IS74 backends."""
        try:
            await self.client.async_maintenance()
            status = await self.client.get_status()

            if not status.get("authenticated", False):
                return {
                    "status": status,
                    "devices": [],
                    "cameras": [],
                    "fcm_status": {"listener_running": False},
                }

            devices = await self.client.get_devices()
            cameras = await self.client.get_cameras()
            fcm_status = await self.client.get_fcm_status()

            return {
                "status": status,
                "devices": devices,
                "cameras": cameras,
                "fcm_status": fcm_status,
            }
        except Exception as err:
            _LOGGER.warning("Error fetching data: %s", err)
            return {
                "status": {"status": "error", "authenticated": False},
                "devices": [],
                "cameras": [],
                "fcm_status": {},
            }
