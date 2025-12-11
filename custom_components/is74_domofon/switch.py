"""Switch platform for IS74 Domofon integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ICON_AUTO_OPEN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IS74 Domofon switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    entities = []
    
    # Add auto-open switch for each device
    for device in coordinator.data.get("devices", []):
        entities.append(IS74AutoOpenSwitch(coordinator, client, entry, device))
    
    # Add FCM listener switch
    entities.append(IS74FCMSwitch(coordinator, client, entry))
    
    async_add_entities(entities)


class IS74AutoOpenSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for auto-open mode."""

    _attr_has_entity_name = True
    _attr_icon = ICON_AUTO_OPEN

    def __init__(self, coordinator, client, entry: ConfigEntry, device: dict[str, Any]) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._device = device
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{device['id']}_auto_open"
        self._attr_name = "Автооткрытие"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device["id"])},
            name=self._device.get("name", "IS74 Домофон"),
            manufacturer="IS74",
            model="Intercom",
        )

    @property
    def is_on(self) -> bool:
        """Return true if auto-open is enabled."""
        auto_open = self.coordinator.data.get("auto_open", {})
        return auto_open.get("enabled", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on auto-open."""
        await self._client.set_auto_open(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off auto-open."""
        await self._client.set_auto_open(False)
        await self.coordinator.async_request_refresh()


class IS74FCMSwitch(CoordinatorEntity, SwitchEntity):
    """Switch for FCM push service."""

    _attr_has_entity_name = True
    _attr_name = "Push уведомления"
    _attr_icon = "mdi:bell-ring"

    def __init__(self, coordinator, client, entry: ConfigEntry) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_fcm"

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
    def is_on(self) -> bool:
        """Return true if FCM is running."""
        fcm = self.coordinator.data.get("fcm_status", {})
        return fcm.get("listener_running", False)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for FCM."""
        fcm = self.coordinator.data.get("fcm_status", {})
        return {
            "fcm_initialized": fcm.get("fcm_initialized", False),
            "has_fcm_creds": fcm.get("has_fcm_creds", False),
            "fcm_token": fcm.get("fcm_token"),
            "device_id": fcm.get("device_id"),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start FCM service."""
        await self._client.start_fcm()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop FCM service."""
        await self._client.stop_fcm()
        await self.coordinator.async_request_refresh()

