"""Auto-open manager for conditional door opening on calls."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

from .config_manager import ConfigManager, AutoOpenConfig, AutoOpenSchedule, DayOfWeek
from .device_controller import DeviceController, DeviceControlError
from .event_manager import EventManager, EventType


logger = logging.getLogger(__name__)


@dataclass
class CallEvent:
    """Represents a call event (simplified version without Firebase dependency)."""
    call_id: str
    device_id: str
    timestamp: datetime
    snapshot_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AutoOpenManager:
    """
    Manages automatic door opening on incoming calls.
    
    Features:
    - Automatic door opening when calls are received
    - Schedule-based conditional auto-open
    - Event logging for auto-open actions
    
    Validates Requirements:
    - 6.1: Auto-open on call when enabled
    - 6.2: Conditional auto-open based on schedule
    - 6.3: Only notify without opening when conditions not met
    - 6.4: Log auto-open events with timestamp
    """
    
    def __init__(
        self,
        config_manager: ConfigManager,
        device_controller: DeviceController,
        event_manager: EventManager
    ):
        """
        Initialize AutoOpenManager.
        
        Args:
            config_manager: ConfigManager instance for auto-open configuration
            device_controller: DeviceController instance for door operations
            event_manager: EventManager instance for event logging
        """
        self.config_manager = config_manager
        self.device_controller = device_controller
        self.event_manager = event_manager
        
        logger.info("AutoOpenManager initialized")
    
    def _get_day_of_week(self, dt: datetime) -> DayOfWeek:
        """
        Get DayOfWeek enum from datetime.
        
        Args:
            dt: Datetime object
        
        Returns:
            DayOfWeek enum value
        """
        day_map = {
            0: DayOfWeek.MONDAY,
            1: DayOfWeek.TUESDAY,
            2: DayOfWeek.WEDNESDAY,
            3: DayOfWeek.THURSDAY,
            4: DayOfWeek.FRIDAY,
            5: DayOfWeek.SATURDAY,
            6: DayOfWeek.SUNDAY
        }
        return day_map[dt.weekday()]
    
    def should_auto_open(self, call_time: Optional[datetime] = None) -> bool:
        """
        Check if auto-open should be triggered based on configuration and schedule.
        
        Validates Requirements:
        - 6.1: Returns True when auto-open is enabled (unconditionally if no schedules)
        - 6.2: Returns True only if call time matches schedule conditions
        - 6.3: Returns False when conditions not met
        
        Args:
            call_time: Time of the call (defaults to current time)
        
        Returns:
            True if door should be auto-opened, False otherwise
        """
        config = self.config_manager.get_auto_open_config()
        
        # Check if auto-open is enabled
        if not config.enabled:
            logger.debug("Auto-open disabled")
            return False
        
        # If no schedules configured, auto-open is always active when enabled
        if not config.schedules:
            logger.debug("Auto-open enabled with no schedules (always active)")
            return True
        
        # Check if current time matches any schedule
        call_time = call_time or datetime.now()
        call_day = self._get_day_of_week(call_time)
        call_time_only = call_time.time()
        
        for schedule in config.schedules:
            # Check if day matches
            if call_day not in schedule.days:
                continue
            
            # Check if time is within range
            if schedule.time_start <= call_time_only <= schedule.time_end:
                logger.debug(
                    f"Auto-open schedule match: day={call_day.value}, "
                    f"time={call_time_only}, schedule={schedule.time_start}-{schedule.time_end}"
                )
                return True
        
        logger.debug(
            f"Auto-open schedule mismatch: day={call_day.value}, "
            f"time={call_time_only}"
        )
        return False
    
    async def handle_call_event(self, call_event: CallEvent) -> bool:
        """
        Handle incoming call event and perform auto-open if conditions are met.
        
        Validates Requirements:
        - 6.1: Auto-opens door when enabled
        - 6.2: Checks schedule conditions before opening
        - 6.3: Only notifies without opening when conditions not met
        - 6.4: Logs auto-open events with timestamp
        
        Args:
            call_event: CallEvent with call information
        
        Returns:
            True if door was auto-opened, False otherwise
        """
        logger.info(
            f"Handling call event for auto-open: device_id={call_event.device_id}, "
            f"call_id={call_event.call_id}"
        )
        
        # Check if auto-open should be triggered
        if not self.should_auto_open(call_event.timestamp):
            logger.info(
                f"Auto-open conditions not met for call {call_event.call_id}, "
                "only notifying"
            )
            return False
        
        # Auto-open is enabled and conditions are met, open the door
        try:
            logger.info(
                f"Auto-opening door for device {call_event.device_id} "
                f"(call {call_event.call_id})"
            )
            
            # Open the door
            await self.device_controller.open_door(call_event.device_id)
            
            # Log auto-open event (Requirement 6.4)
            await self.event_manager.log_event(
                event_type=EventType.AUTO_OPEN,
                device_id=call_event.device_id,
                metadata={
                    "call_id": call_event.call_id,
                    "call_timestamp": call_event.timestamp.isoformat(),
                    "snapshot_url": call_event.snapshot_url,
                    "auto_opened": True
                }
            )
            
            logger.info(
                f"Door auto-opened successfully for device {call_event.device_id}"
            )
            return True
            
        except DeviceControlError as e:
            logger.error(
                f"Failed to auto-open door for device {call_event.device_id}: {e.message}"
            )
            
            # Log failed auto-open attempt
            await self.event_manager.log_event(
                event_type=EventType.ERROR,
                device_id=call_event.device_id,
                metadata={
                    "call_id": call_event.call_id,
                    "error": "auto_open_failed",
                    "error_message": e.message,
                    "error_code": e.error_code
                }
            )
            
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error during auto-open for device {call_event.device_id}: {e}",
                exc_info=True
            )
            
            # Log unexpected error
            await self.event_manager.log_event(
                event_type=EventType.ERROR,
                device_id=call_event.device_id,
                metadata={
                    "call_id": call_event.call_id,
                    "error": "auto_open_unexpected_error",
                    "error_message": str(e)
                }
            )
            
            return False
