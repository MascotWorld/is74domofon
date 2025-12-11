"""Camera platform for IS74 Domofon integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ICON_CAMERA

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IS74 Domofon cameras."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    entities = []
    
    for camera in coordinator.data.get("cameras", []):
        entities.append(IS74Camera(coordinator, client, entry, camera))
    
    async_add_entities(entities)


class IS74Camera(CoordinatorEntity, Camera):
    """Representation of an IS74 camera."""

    _attr_has_entity_name = True
    _attr_icon = ICON_CAMERA
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, coordinator, client, entry: ConfigEntry, camera: dict[str, Any]) -> None:
        """Initialize the camera."""
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        
        self._client = client
        self._camera = camera
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{camera['uuid']}"
        self._attr_name = camera.get("name", "Камера")
        self._stream_url = None
        self._snapshot_url = camera.get("snapshot_url")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._camera["uuid"])},
            name=self._camera.get("name", "IS74 Камера"),
            manufacturer="IS74",
            model="Camera",
        )

    @property
    def is_on(self) -> bool:
        """Return true if camera is online."""
        return self._camera.get("is_online", False)

    @property
    def available(self) -> bool:
        """Return true if camera is available."""
        return self._camera.get("is_online", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "uuid": self._camera.get("uuid"),
            "status": self._camera.get("status"),
            "address": self._camera.get("address"),
            "has_stream": self._camera.get("has_stream", False),
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still image from the camera."""
        if not self._snapshot_url:
            return None
        
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            session = async_get_clientsession(self.hass)
            
            async with session.get(self._snapshot_url, timeout=10) as response:
                if response.status == 200:
                    return await response.read()
        except Exception as err:
            _LOGGER.error("Error fetching camera image: %s", err)
        
        return None

    async def stream_source(self) -> str | None:
        """Return the stream source URL."""
        if not self._camera.get("has_stream"):
            return None
        
        try:
            stream_data = await self._client.get_video_stream(self._camera["uuid"])
            if stream_data.get("is_available"):
                return stream_data.get("stream_url")
        except Exception as err:
            _LOGGER.error("Error fetching stream URL: %s", err)
        
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        cameras = self.coordinator.data.get("cameras", [])
        for camera in cameras:
            if camera["uuid"] == self._camera["uuid"]:
                self._camera = camera
                self._snapshot_url = camera.get("snapshot_url")
                break
        self.async_write_ha_state()

