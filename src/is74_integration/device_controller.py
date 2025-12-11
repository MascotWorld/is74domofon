"""Device controller for IS74 intercom operations."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass

from .api_client import IS74ApiClient, IS74ApiError

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


@dataclass
class Device:
    """Represents an intercom device."""
    
    id: str  # Unique identifier (MAC address)
    name: str
    mac: str
    relay_id: int
    relay_num: int
    status: str  # online/offline
    address: Optional[str] = None
    building_id: Optional[int] = None
    entrance: Optional[str] = None
    flat: Optional[str] = None
    camera_uuids: Optional[List[str]] = None  # Associated camera UUIDs
    raw_data: Optional[Dict[str, Any]] = None
    
    @property
    def is_online(self) -> bool:
        """Check if device is online."""
        return self.status.lower() == "online"
    
    @property
    def has_cameras(self) -> bool:
        """Check if device has associated cameras."""
        return bool(self.camera_uuids and len(self.camera_uuids) > 0)


@dataclass
class DoorLockStatus:
    """Represents door lock status."""
    
    device_id: str
    is_locked: bool
    timestamp: datetime
    error: Optional[str] = None


@dataclass
class DeviceStatus:
    """Represents device online/offline status."""
    
    device_id: str
    is_online: bool
    timestamp: datetime
    last_seen: Optional[datetime] = None


class DeviceControlError(Exception):
    """Exception raised for device control failures."""
    
    def __init__(self, message: str, device_id: Optional[str] = None, error_code: Optional[str] = None):
        self.message = message
        self.device_id = device_id
        self.error_code = error_code
        super().__init__(self.message)


class DeviceController:
    """
    Controls IS74 intercom devices.
    
    Features:
    - Get list of intercom devices
    - Open door command
    - Door lock status synchronization with Home Assistant
    - Automatic lock status reset after 5 seconds
    - Error handling and notification
    - Device status monitoring (online/offline)
    - Connection loss detection with 30 second timeout
    """
    
    LOCK_RESET_DELAY_SECONDS = 5
    CONNECTION_TIMEOUT_SECONDS = 30
    STATUS_CHECK_INTERVAL_SECONDS = 10
    
    def __init__(
        self,
        api_client: IS74ApiClient,
        status_callback: Optional[Callable[[DoorLockStatus], None]] = None,
        device_status_callback: Optional[Callable[[DeviceStatus], None]] = None
    ):
        """
        Initialize DeviceController.
        
        Args:
            api_client: IS74ApiClient instance for making API requests
            status_callback: Optional callback for door lock status updates
            device_status_callback: Optional callback for device online/offline status updates
        """
        self.api_client = api_client
        self.status_callback = status_callback
        self.device_status_callback = device_status_callback
        self._devices_cache: Optional[List[Device]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._lock_reset_tasks: Dict[str, asyncio.Task] = {}
        
        # Device status monitoring
        self._device_status: Dict[str, DeviceStatus] = {}
        self._last_successful_connection: Dict[str, datetime] = {}
        self._status_monitor_task: Optional[asyncio.Task] = None
        self._monitoring_enabled = False
        
        logger.info("DeviceController initialized")
    
    async def get_devices(self, force_refresh: bool = False) -> List[Device]:
        """
        Get list of intercom devices.
        
        Implements GET /api/intercoms endpoint.
        Results are cached for 30 seconds to reduce API calls.
        
        Args:
            force_refresh: Force refresh from API, ignoring cache
        
        Returns:
            List of Device objects
        
        Raises:
            DeviceControlError: If request fails
        """
        # Check cache (30 second TTL)
        if not force_refresh and self._devices_cache and self._cache_timestamp:
            cache_age = (datetime.now() - self._cache_timestamp).total_seconds()
            if cache_age < 30:
                logger.debug(f"Returning cached devices (age: {cache_age:.1f}s)")
                return self._devices_cache
        
        try:
            logger.info("Fetching intercom device list")
            
            # First get main devices (isShared=1)
            response_main = await self.api_client.get(
                "/domofon/relays",
                params={
                    "pagination": "1",
                    "pageSize": "30",
                    "page": "1",
                    "isShared": "1"
                }
            )
            
            # Parse response into Device objects
            devices = []
            
            # Response can be a list or dict with a list
            device_list = response_main if isinstance(response_main, list) else response_main.get("items", [])
            
            # If main list is empty, try secondary list (isShared=0)
            if not device_list or len(device_list) == 0:
                logger.info("Main device list is empty, trying secondary list")
                
                # Get building IDs from user profile if available
                # For now, we'll try without buildingIds parameter
                response_secondary = await self.api_client.get(
                    "/domofon/relays",
                    params={
                        "mainFirst": "1",
                        "pagination": "1",
                        "pageSize": "30",
                        "page": "1",
                        "isShared": "0"
                    }
                )
                
                device_list = response_secondary if isinstance(response_secondary, list) else response_secondary.get("items", [])
            
            for item in device_list:
                # Extract device information
                # The API response structure may vary, handle common formats
                mac = item.get("MAC_ADDR") or item.get("MAC") or item.get("mac") or item.get("id")
                
                # Get name from RELAY_TYPE or RELAY_DESCR, fallback to ADDRESS
                name = (item.get("RELAY_TYPE") or 
                       item.get("RELAY_DESCR") or 
                       item.get("NAME") or 
                       item.get("name") or 
                       item.get("ADDRESS") or 
                       item.get("address") or 
                       "Unknown")
                
                # Get relay info from OPENER if available, otherwise from top level
                opener = item.get("OPENER", {})
                relay_id = (opener.get("relay_id") or 
                           item.get("RELAY_ID") or 
                           item.get("relay_id") or 
                           item.get("relayId", 0))
                
                relay_num = (opener.get("relay_num") or 
                            item.get("RELAY_NUM") or 
                            item.get("relay_num") or 
                            item.get("relayNum", 1))
                
                # Parse status from STATUS_CODE or STATUS_TEXT
                status_code = item.get("STATUS_CODE")
                status_text = item.get("STATUS_TEXT")
                if status_code == "0" or status_text == "OK":
                    status = "online"
                else:
                    status = item.get("STATUS") or item.get("status") or "unknown"
                
                address = item.get("ADDRESS") or item.get("address")
                building_id = item.get("BUILDING_ID") or item.get("building_id") or item.get("buildingId")
                entrance = item.get("ENTRANCE_UID") or item.get("ENTRANCE") or item.get("entrance")
                flat = item.get("FLAT") or item.get("flat")
                
                if not mac:
                    logger.warning(f"Skipping device without MAC address: {item}")
                    continue
                
                device = Device(
                    id=mac,
                    name=name,
                    mac=mac,
                    relay_id=relay_id,
                    relay_num=relay_num,
                    status=status,
                    address=address,
                    building_id=building_id,
                    entrance=entrance,
                    flat=flat,
                    raw_data=item
                )
                devices.append(device)
            
            # Update cache
            self._devices_cache = devices
            self._cache_timestamp = datetime.now()
            
            # Update device status tracking
            for device in devices:
                await self.update_device_status(device.id, device.is_online)
            
            logger.info(f"Retrieved {len(devices)} intercom devices")
            return devices
            
        except IS74ApiError as e:
            logger.error(f"Failed to get device list: {e}")
            raise DeviceControlError(f"Failed to get device list: {e}") from e
    
    async def get_device_by_id(self, device_id: str) -> Optional[Device]:
        """
        Get device by ID (MAC address).
        
        Args:
            device_id: Device ID (MAC address)
        
        Returns:
            Device object or None if not found
        """
        devices = await self.get_devices()
        return next((d for d in devices if d.id == device_id), None)
    
    async def _notify_status_change(self, status: DoorLockStatus) -> None:
        """
        Notify status change via callback.
        
        Args:
            status: DoorLockStatus object
        """
        if self.status_callback:
            try:
                if asyncio.iscoroutinefunction(self.status_callback):
                    await self.status_callback(status)
                else:
                    self.status_callback(status)
            except Exception as e:
                logger.error(f"Error in status callback: {e}", exc_info=True)
    
    async def _reset_lock_status(self, device_id: str) -> None:
        """
        Reset lock status to locked after delay.
        
        Args:
            device_id: Device ID
        """
        try:
            await asyncio.sleep(self.LOCK_RESET_DELAY_SECONDS)
            
            logger.info(f"Resetting lock status for device {device_id} to locked")
            status = DoorLockStatus(
                device_id=device_id,
                is_locked=True,
                timestamp=datetime.now()
            )
            await self._notify_status_change(status)
            
            # Remove task from tracking
            if device_id in self._lock_reset_tasks:
                del self._lock_reset_tasks[device_id]
                
        except asyncio.CancelledError:
            logger.debug(f"Lock reset task cancelled for device {device_id}")
        except Exception as e:
            logger.error(f"Error resetting lock status for device {device_id}: {e}", exc_info=True)
    
    async def open_door(self, device_id: str, relay_num: Optional[int] = None) -> bool:
        """
        Open door by sending command to intercom.
        
        Implements POST /api/open/{mac}/{relay_num} endpoint.
        
        Requirements:
        - 4.1: Send door open command
        - 4.2: Update status to "unlocked" on success
        - 4.3: Notify on failure with error description
        - 4.4: Auto-reset to "locked" after 5 seconds
        
        Args:
            device_id: Device ID (MAC address)
            relay_num: Optional relay number (defaults to device's relay_num)
        
        Returns:
            True if command was successful
        
        Raises:
            DeviceControlError: If command fails
        """
        try:
            # Get device info
            device = await self.get_device_by_id(device_id)
            if not device:
                error_msg = f"Device not found: {device_id}"
                logger.error(error_msg)
                
                # Notify error
                status = DoorLockStatus(
                    device_id=device_id,
                    is_locked=True,
                    timestamp=datetime.now(),
                    error=error_msg
                )
                await self._notify_status_change(status)
                
                raise DeviceControlError(error_msg, device_id=device_id, error_code="DEVICE_NOT_FOUND")
            
            # Use provided relay_num or device's default
            relay = relay_num if relay_num is not None else device.relay_num
            
            logger.info(f"Opening door for device {device_id} (MAC: {device.mac}, relay: {relay})")
            
            # Build request payload
            payload = {
                "relay_id": device.relay_id
            }
            
            # Send open door command
            # POST /domofon/relays/{relay_id}/open?from=app
            endpoint = f"/domofon/relays/{device.relay_id}/open"
            response = await self.api_client.post(
                endpoint,
                params={"from": "app"},
                json={}  # Empty body as per Postman collection
            )
            
            logger.info(f"Door open command sent successfully for device {device_id}")
            
            # Update status to unlocked (Requirement 4.2)
            status = DoorLockStatus(
                device_id=device_id,
                is_locked=False,
                timestamp=datetime.now()
            )
            await self._notify_status_change(status)
            
            # Cancel any existing reset task for this device
            if device_id in self._lock_reset_tasks:
                self._lock_reset_tasks[device_id].cancel()
            
            # Schedule automatic lock status reset after 5 seconds (Requirement 4.4)
            reset_task = asyncio.create_task(self._reset_lock_status(device_id))
            self._lock_reset_tasks[device_id] = reset_task
            
            return True
            
        except IS74ApiError as e:
            error_msg = f"Failed to open door for device {device_id}: {e.message}"
            logger.error(error_msg)
            
            # Notify error (Requirement 4.3)
            status = DoorLockStatus(
                device_id=device_id,
                is_locked=True,
                timestamp=datetime.now(),
                error=error_msg
            )
            await self._notify_status_change(status)
            
            raise DeviceControlError(
                error_msg,
                device_id=device_id,
                error_code=str(e.status_code) if e.status_code else "API_ERROR"
            ) from e
        except DeviceControlError:
            raise
        except Exception as e:
            error_msg = f"Unexpected error opening door for device {device_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Notify error
            status = DoorLockStatus(
                device_id=device_id,
                is_locked=True,
                timestamp=datetime.now(),
                error=error_msg
            )
            await self._notify_status_change(status)
            
            raise DeviceControlError(error_msg, device_id=device_id, error_code="UNEXPECTED_ERROR") from e
    
    async def get_device_status(self, device_id: str) -> Optional[str]:
        """
        Get current status of a device.
        
        Args:
            device_id: Device ID (MAC address)
        
        Returns:
            Device status string or None if device not found
        """
        device = await self.get_device_by_id(device_id)
        return device.status if device else None
    
    async def _notify_device_status_change(self, status: DeviceStatus) -> None:
        """
        Notify device status change via callback.
        
        Args:
            status: DeviceStatus object
        """
        if self.device_status_callback:
            try:
                if asyncio.iscoroutinefunction(self.device_status_callback):
                    await self.device_status_callback(status)
                else:
                    self.device_status_callback(status)
            except Exception as e:
                logger.error(f"Error in device status callback: {e}", exc_info=True)
    
    async def update_device_status(self, device_id: str, is_online: bool) -> None:
        """
        Update device online/offline status and notify Home Assistant.
        
        Validates:
            - Requirements 9.1: Reports "online" status when connected
            - Requirements 9.2: Reports "offline" status on connection loss
        
        Args:
            device_id: Device ID (MAC address)
            is_online: Whether device is online
        """
        now = datetime.now()
        
        # Get current status
        current_status = self._device_status.get(device_id)
        
        # Check if status changed
        status_changed = (
            current_status is None or 
            current_status.is_online != is_online
        )
        
        if status_changed:
            logger.info(
                f"Device {device_id} status changed: "
                f"{'online' if is_online else 'offline'}"
            )
        
        # Update status
        new_status = DeviceStatus(
            device_id=device_id,
            is_online=is_online,
            timestamp=now,
            last_seen=self._last_successful_connection.get(device_id)
        )
        self._device_status[device_id] = new_status
        
        # Update last seen if online
        if is_online:
            self._last_successful_connection[device_id] = now
        
        # Notify if status changed
        if status_changed:
            await self._notify_device_status_change(new_status)
    
    async def _check_device_connections(self) -> None:
        """
        Periodically check device connections and update offline status.
        
        Monitors devices for connection loss and updates status to offline
        if no successful connection within CONNECTION_TIMEOUT_SECONDS.
        
        Validates:
            - Requirements 9.2: Updates to offline within 30 seconds
        """
        while self._monitoring_enabled:
            try:
                now = datetime.now()
                timeout_threshold = timedelta(seconds=self.CONNECTION_TIMEOUT_SECONDS)
                
                # Check each tracked device
                for device_id, last_seen in list(self._last_successful_connection.items()):
                    time_since_last_seen = now - last_seen
                    
                    # Check if device has timed out
                    if time_since_last_seen > timeout_threshold:
                        current_status = self._device_status.get(device_id)
                        
                        # Only update if currently marked as online
                        if current_status and current_status.is_online:
                            logger.warning(
                                f"Device {device_id} connection lost "
                                f"(last seen {time_since_last_seen.total_seconds():.1f}s ago)"
                            )
                            await self.update_device_status(device_id, is_online=False)
                
                # Wait before next check
                await asyncio.sleep(self.STATUS_CHECK_INTERVAL_SECONDS)
                
            except asyncio.CancelledError:
                logger.debug("Device connection monitoring cancelled")
                break
            except Exception as e:
                logger.error(f"Error in device connection monitoring: {e}", exc_info=True)
                await asyncio.sleep(self.STATUS_CHECK_INTERVAL_SECONDS)
    
    def start_monitoring(self) -> None:
        """
        Start device status monitoring.
        
        Begins periodic checks for device connection timeouts.
        """
        if self._monitoring_enabled:
            logger.warning("Device monitoring already started")
            return
        
        self._monitoring_enabled = True
        self._status_monitor_task = asyncio.create_task(self._check_device_connections())
        logger.info("Device status monitoring started")
    
    def stop_monitoring(self) -> None:
        """
        Stop device status monitoring.
        
        Cancels the monitoring task.
        """
        if not self._monitoring_enabled:
            return
        
        self._monitoring_enabled = False
        
        if self._status_monitor_task:
            self._status_monitor_task.cancel()
            self._status_monitor_task = None
        
        logger.info("Device status monitoring stopped")
    
    def get_monitored_device_status(self, device_id: str) -> Optional[DeviceStatus]:
        """
        Get the monitored status of a device.
        
        Args:
            device_id: Device ID (MAC address)
        
        Returns:
            DeviceStatus object or None if device not monitored
        """
        return self._device_status.get(device_id)
    
    def cancel_all_reset_tasks(self) -> None:
        """Cancel all pending lock reset tasks."""
        for task in self._lock_reset_tasks.values():
            task.cancel()
        self._lock_reset_tasks.clear()
        logger.info("All lock reset tasks cancelled")
    
    async def close(self) -> None:
        """Cleanup resources."""
        self.stop_monitoring()
        self.cancel_all_reset_tasks()
        logger.info("DeviceController closed")
