"""IS74 Domofon integration for Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    CONF_API_URL,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS,
    SERVICE_OPEN_DOOR,
    SERVICE_TOGGLE_AUTO_OPEN,
    SERVICE_START_FCM,
    SERVICE_STOP_FCM,
    EVENT_DOOR_OPENED,
    EVENT_INCOMING_CALL,
    EVENT_AUTO_OPENED,
    ATTR_DEVICE_ID,
)

_LOGGER = logging.getLogger(__name__)

# Default port for embedded server
EMBEDDED_SERVER_PORT = 10777

# Configuration keys
CONF_AUTO_START_FCM = "auto_start_fcm"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IS74 Domofon from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    api_url = entry.data.get(CONF_API_URL, "")
    use_embedded = entry.data.get("use_embedded_server", True)
    auto_start_fcm = entry.data.get(CONF_AUTO_START_FCM, True)
    
    # Start embedded server if enabled
    if use_embedded or not api_url or api_url == "embedded":
        from .server import setup_server
        port = entry.data.get("server_port", EMBEDDED_SERVER_PORT)
        
        try:
            await setup_server(hass, port=port)
            api_url = f"http://localhost:{port}"
            _LOGGER.info(f"Embedded API server started on port {port}")
        except Exception as e:
            _LOGGER.error(f"Failed to start embedded server: {e}")
            # Continue anyway, maybe external server is configured
    
    # Create API client
    session = async_get_clientsession(hass)
    client = IS74DomofonClient(session, api_url)
    
    # Create coordinator
    coordinator = IS74DomofonCoordinator(hass, client)
    
    # Try to fetch initial data (might fail if not authenticated yet)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as e:
        _LOGGER.warning(f"Initial data fetch failed (this is OK if not authenticated yet): {e}")
    
    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "api_url": api_url,
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await async_setup_services(hass, client)
    
    # Auto-start FCM if enabled and authenticated
    if auto_start_fcm:
        try:
            status = await client.get_status()
            if status.get("authenticated"):
                _LOGGER.info("Auto-starting FCM service...")
                await client.start_fcm()
                _LOGGER.info("FCM service auto-started successfully")
        except Exception as e:
            _LOGGER.warning(f"Failed to auto-start FCM (will try again later): {e}")
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Stop embedded server
    use_embedded = entry.data.get("use_embedded_server", True)
    if use_embedded:
        from .server import stop_server
        await stop_server()
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def async_setup_services(hass: HomeAssistant, client: "IS74DomofonClient") -> None:
    """Set up services for IS74 Domofon."""
    
    async def handle_open_door(call: ServiceCall) -> None:
        """Handle open door service call."""
        device_id = call.data.get(ATTR_DEVICE_ID)
        if device_id:
            result = await client.open_door(device_id)
            if result.get("success"):
                hass.bus.async_fire(EVENT_DOOR_OPENED, {"device_id": device_id})
    
    async def handle_toggle_auto_open(call: ServiceCall) -> None:
        """Handle toggle auto-open service call."""
        enabled = call.data.get("enabled", True)
        await client.set_auto_open(enabled)
    
    async def handle_start_fcm(call: ServiceCall) -> None:
        """Handle start FCM service call."""
        await client.start_fcm()
    
    async def handle_stop_fcm(call: ServiceCall) -> None:
        """Handle stop FCM service call."""
        await client.stop_fcm()
    
    hass.services.async_register(DOMAIN, SERVICE_OPEN_DOOR, handle_open_door)
    hass.services.async_register(DOMAIN, SERVICE_TOGGLE_AUTO_OPEN, handle_toggle_auto_open)
    hass.services.async_register(DOMAIN, SERVICE_START_FCM, handle_start_fcm)
    hass.services.async_register(DOMAIN, SERVICE_STOP_FCM, handle_stop_fcm)


class IS74DomofonClient:
    """API client for IS74 Domofon service."""
    
    def __init__(self, session: aiohttp.ClientSession, api_url: str) -> None:
        """Initialize the client."""
        self._session = session
        self._api_url = api_url.rstrip("/") if api_url else "http://localhost:10777"
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make API request."""
        url = f"{self._api_url}{endpoint}"
        try:
            async with self._session.request(method, url, **kwargs) as response:
                if response.status == 401:
                    return {"error": "Not authenticated", "authenticated": False}
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("API request failed: %s", err)
            return {"error": str(err)}
    
    async def get_status(self) -> dict[str, Any]:
        """Get service status."""
        return await self._request("GET", "/status")
    
    async def get_devices(self) -> list[dict[str, Any]]:
        """Get list of devices."""
        response = await self._request("GET", "/devices")
        return response.get("devices", [])
    
    async def get_cameras(self) -> list[dict[str, Any]]:
        """Get list of cameras."""
        response = await self._request("GET", "/cameras")
        return response.get("cameras", [])
    
    async def open_door(self, device_id: str, relay_num: int | None = None) -> dict[str, Any]:
        """Open door."""
        data = {"device_id": device_id}
        if relay_num is not None:
            data["relay_num"] = relay_num
        return await self._request("POST", "/door/open", json=data)
    
    async def get_video_stream(self, camera_uuid: str) -> dict[str, Any]:
        """Get video stream URL."""
        return await self._request("GET", f"/stream/video/{camera_uuid}")
    
    async def get_fcm_status(self) -> dict[str, Any]:
        """Get FCM status."""
        return await self._request("GET", "/fcm/status")
    
    async def start_fcm(self) -> dict[str, Any]:
        """Start FCM push service."""
        return await self._request("POST", "/fcm/start")
    
    async def stop_fcm(self) -> dict[str, Any]:
        """Stop FCM push service."""
        return await self._request("POST", "/fcm/stop")
    
    async def set_auto_open(self, enabled: bool) -> dict[str, Any]:
        """Set auto-open status."""
        return await self._request("POST", "/auto-open", json={"enabled": enabled})
    
    async def get_auto_open(self) -> dict[str, Any]:
        """Get auto-open status."""
        return await self._request("GET", "/auto-open")


class IS74DomofonCoordinator(DataUpdateCoordinator):
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
        """Fetch data from API."""
        try:
            status = await self.client.get_status()
            
            # If not authenticated, return minimal data
            if not status.get("authenticated", False):
                return {
                    "status": status,
                    "devices": [],
                    "cameras": [],
                    "fcm_status": {"listener_running": False},
                    "auto_open": {"enabled": False},
                }
            
            devices = await self.client.get_devices()
            cameras = await self.client.get_cameras()
            fcm_status = await self.client.get_fcm_status()
            auto_open = await self.client.get_auto_open()
            
            return {
                "status": status,
                "devices": devices,
                "cameras": cameras,
                "fcm_status": fcm_status,
                "auto_open": auto_open,
            }
        except Exception as err:
            _LOGGER.warning(f"Error fetching data: {err}")
            return {
                "status": {"status": "error", "authenticated": False},
                "devices": [],
                "cameras": [],
                "fcm_status": {},
                "auto_open": {"enabled": False},
            }
