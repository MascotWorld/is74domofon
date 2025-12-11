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
    ATTR_DEVICE_ID,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IS74 Domofon from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    api_url = entry.data.get(CONF_API_URL)
    
    # Create API client
    session = async_get_clientsession(hass)
    client = IS74DomofonClient(session, api_url)
    
    # Create coordinator
    coordinator = IS74DomofonCoordinator(hass, client)
    
    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()
    
    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }
    
    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    await async_setup_services(hass, client)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
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
        self._api_url = api_url.rstrip("/")
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make API request."""
        url = f"{self._api_url}{endpoint}"
        try:
            async with self._session.request(method, url, **kwargs) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as err:
            _LOGGER.error("API request failed: %s", err)
            raise
    
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
            raise UpdateFailed(f"Error fetching data: {err}") from err

