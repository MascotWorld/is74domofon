"""Sensor platform for IS74 Domofon integration."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ICON_INTERCOM,
    ATTR_DEVICE_ID,
    ATTR_MAC_ADDRESS,
    ATTR_ADDRESS,
    ATTR_ENTRANCE,
    ATTR_FLAT,
    ATTR_IS_ONLINE,
    ATTR_HAS_CAMERAS,
    ATTR_CAMERA_COUNT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IS74 Domofon sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    entities = []
    
    # Add device sensors
    for device in coordinator.data.get("devices", []):
        entities.append(IS74DeviceSensor(coordinator, entry, device))
    
    # Add service status sensor
    entities.append(IS74ServiceStatusSensor(coordinator, entry))
    
    # Add FCM status sensor
    entities.append(IS74FCMStatusSensor(coordinator, entry))
    
    async_add_entities(entities)


class IS74DeviceSensor(CoordinatorEntity, SensorEntity):
    """Representation of an IS74 intercom device sensor."""

    _attr_has_entity_name = True
    _attr_icon = ICON_INTERCOM

    def __init__(self, coordinator, entry: ConfigEntry, device: dict[str, Any]) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._device = device
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{device['id']}_status"
        self._attr_name = device.get("name", "Домофон")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device["id"])},
            name=self._device.get("name", "IS74 Домофон"),
            manufacturer="IS74",
            model="Intercom",
            sw_version="1.0",
        )

    @property
    def native_value(self) -> str:
        """Return the state."""
        return self._device.get("status", "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            ATTR_DEVICE_ID: self._device.get("id"),
            ATTR_MAC_ADDRESS: self._device.get("mac"),
            ATTR_ADDRESS: self._device.get("address"),
            ATTR_ENTRANCE: self._device.get("entrance"),
            ATTR_FLAT: self._device.get("flat"),
            ATTR_IS_ONLINE: self._device.get("is_online", False),
            ATTR_HAS_CAMERAS: self._device.get("has_cameras", False),
            ATTR_CAMERA_COUNT: self._device.get("camera_count", 0),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        devices = self.coordinator.data.get("devices", [])
        for device in devices:
            if device["id"] == self._device["id"]:
                self._device = device
                break
        self.async_write_ha_state()


class IS74ServiceStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of IS74 service status sensor."""

    _attr_has_entity_name = True
    _attr_name = "Статус сервиса"
    _attr_icon = "mdi:server"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_service_status"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="IS74 Сервис",
            manufacturer="IS74",
            model="Integration Service",
            sw_version=self.coordinator.data.get("status", {}).get("version", "1.0.0"),
        )

    @property
    def native_value(self) -> str:
        """Return the state."""
        status = self.coordinator.data.get("status", {})
        return status.get("status", "unknown")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        status = self.coordinator.data.get("status", {})
        return {
            "authenticated": status.get("authenticated", False),
            "uptime_seconds": status.get("uptime_seconds", 0),
            "version": status.get("version", "unknown"),
            "components": status.get("components", {}),
        }


class IS74FCMStatusSensor(CoordinatorEntity, SensorEntity):
    """Representation of FCM status sensor."""

    _attr_has_entity_name = True
    _attr_name = "FCM Push"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_fcm_status"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name="IS74 Сервис",
            manufacturer="IS74",
            model="Integration Service",
        )

    @property
    def native_value(self) -> str:
        """Return the state."""
        fcm = self.coordinator.data.get("fcm_status", {})
        if fcm.get("listener_running"):
            return "active"
        elif fcm.get("fcm_initialized"):
            return "initialized"
        else:
            return "not_configured"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        fcm = self.coordinator.data.get("fcm_status", {})
        return {
            "fcm_initialized": fcm.get("fcm_initialized", False),
            "device_id": fcm.get("device_id"),
            "authenticated": fcm.get("authenticated", False),
            "has_fcm_token": fcm.get("has_fcm_token", False),
            "listener_running": fcm.get("listener_running", False),
        }

