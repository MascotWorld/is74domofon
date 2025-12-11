"""Button platform for IS74 Domofon integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    ICON_DOOR_OPEN,
    ICON_WEB_PANEL,
    EVENT_DOOR_OPENED,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up IS74 Domofon buttons."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    client = hass.data[DOMAIN][entry.entry_id]["client"]
    
    entities = []
    
    # Add buttons for each device
    for device in coordinator.data.get("devices", []):
        entities.append(IS74OpenDoorButton(coordinator, client, entry, device))
    
    # Add web panel button
    entities.append(IS74WebPanelButton(coordinator, entry))
    
    async_add_entities(entities)


class IS74OpenDoorButton(CoordinatorEntity, ButtonEntity):
    """Button to open door."""

    _attr_has_entity_name = True
    _attr_icon = ICON_DOOR_OPEN

    def __init__(self, coordinator, client, entry: ConfigEntry, device: dict[str, Any]) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._client = client
        self._device = device
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{device['id']}_open"
        self._attr_name = "Открыть дверь"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device["id"])},
            name=self._device.get("name", "IS74 Домофон"),
            manufacturer="IS74",
            model="Intercom",
        )

    async def async_press(self) -> None:
        """Handle button press."""
        result = await self._client.open_door(self._device["id"])
        if result.get("success"):
            self.hass.bus.async_fire(EVENT_DOOR_OPENED, {
                "device_id": self._device["id"],
                "name": self._device.get("name"),
            })


class IS74WebPanelButton(CoordinatorEntity, ButtonEntity):
    """Button to open web panel."""

    _attr_has_entity_name = True
    _attr_name = "Веб-панель"
    _attr_icon = ICON_WEB_PANEL

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_web_panel"

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
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        from .const import CONF_API_URL
        api_url = self._entry.data.get(CONF_API_URL, "http://localhost:8000")
        return {
            "url": api_url,
        }

    async def async_press(self) -> None:
        """Handle button press."""
        # This button is informational - the URL is in attributes
        # Frontend card will handle opening the URL
        pass

