"""Event manager for logging and history tracking."""

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
import asyncio


logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Quiet by default


class EventType(str, Enum):
    """Types of events that can be logged."""
    
    CALL = "call"
    CALL_RECEIVED = "call_received"
    DOOR_OPEN = "door_open"
    DOOR_CLOSED = "door_closed"
    DOOR_LOCKED = "door_locked"
    DOOR_UNLOCKED = "door_unlocked"
    AUTO_OPEN = "auto_open"
    CALL_ACCEPTED = "call_accepted"
    CALL_ENDED = "call_ended"
    STREAM_STARTED = "stream_started"
    STREAM_STOPPED = "stream_stopped"
    NOTIFICATION_RECEIVED = "notification_received"
    ERROR = "error"


@dataclass
class Event:
    """
    Represents a system event.
    
    Attributes:
        id: Unique event identifier
        type: Type of event (call, door_open, auto_open, etc.)
        device_id: ID of the device associated with the event
        timestamp: When the event occurred
        metadata: Additional event-specific data
    """
    
    id: str
    type: EventType
    device_id: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert event to dictionary for serialization.
        
        Returns:
            Dictionary representation of the event
        """
        data = asdict(self)
        # Convert datetime to ISO format string
        data["timestamp"] = self.timestamp.isoformat()
        # Convert EventType enum to string
        data["type"] = self.type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """
        Create Event from dictionary.
        
        Args:
            data: Dictionary containing event data
        
        Returns:
            Event instance
        """
        # Parse timestamp
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        
        # Parse event type
        if isinstance(data.get("type"), str):
            data["type"] = EventType(data["type"])
        
        return cls(**data)


class EventManager:
    """
    Manages event logging and history.
    
    Features:
    - Event logging with timestamps
    - Event history storage (last 100 events)
    - Home Assistant notification callbacks
    - Async event processing
    
    Validates Requirements:
    - 9.3: Records events with timestamps
    - 6.4: Logs auto-open events
    """
    
    MAX_HISTORY_SIZE = 100
    
    def __init__(self, max_history: int = MAX_HISTORY_SIZE):
        """
        Initialize EventManager.
        
        Args:
            max_history: Maximum number of events to keep in history (default: 100)
        """
        self.max_history = max_history
        self._history: List[Event] = []
        self._ha_callbacks: List[Callable[[Event], None]] = []
        self._lock = asyncio.Lock()
        
        logger.info(f"EventManager initialized with max_history={max_history}")
    
    async def log_event(
        self,
        event_type: EventType,
        device_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Event:
        """
        Log a new event.
        
        Creates an event with a unique ID and current timestamp, stores it in history,
        and notifies Home Assistant.
        
        Args:
            event_type: Type of event
            device_id: ID of the device associated with the event
            metadata: Optional additional event data
        
        Returns:
            The created Event object
        
        Validates:
            - Requirements 9.3: Records event with timestamp
            - Requirements 6.4: Logs auto-open events
        """
        # Create event
        event = Event(
            id=str(uuid.uuid4()),
            type=event_type,
            device_id=device_id,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        # Store in history (thread-safe)
        async with self._lock:
            self._history.append(event)
            
            # Trim history if it exceeds max size
            if len(self._history) > self.max_history:
                # Keep only the most recent events
                self._history = self._history[-self.max_history:]
        
        logger.info(
            f"Event logged: {event.type.value} for device {device_id}",
            extra={
                "event_id": event.id,
                "event_type": event.type.value,
                "device_id": device_id,
                "timestamp": event.timestamp.isoformat(),
                "metadata": metadata
            }
        )
        
        # Notify Home Assistant (async, don't wait)
        asyncio.create_task(self._notify_callbacks(event))
        
        return event
    
    async def get_history(self, limit: int = MAX_HISTORY_SIZE) -> List[Event]:
        """
        Get event history.
        
        Returns the most recent events up to the specified limit.
        
        Args:
            limit: Maximum number of events to return (default: 100)
        
        Returns:
            List of events, most recent first
        
        Validates:
            - Requirements 9.4: Returns last 100 events
        """
        async with self._lock:
            # Return most recent events up to limit
            events = self._history[-limit:] if limit < len(self._history) else self._history.copy()
            # Reverse to get most recent first
            events.reverse()
        
        logger.debug(f"Retrieved {len(events)} events from history (limit={limit})")
        return events
    
    async def get_history_by_type(
        self,
        event_type: EventType,
        limit: int = MAX_HISTORY_SIZE
    ) -> List[Event]:
        """
        Get event history filtered by type.
        
        Args:
            event_type: Type of events to retrieve
            limit: Maximum number of events to return
        
        Returns:
            List of events of the specified type, most recent first
        """
        async with self._lock:
            filtered = [e for e in self._history if e.type == event_type]
            events = filtered[-limit:] if limit < len(filtered) else filtered.copy()
            events.reverse()
        
        logger.debug(f"Retrieved {len(events)} events of type {event_type.value} (limit={limit})")
        return events
    
    async def get_history_by_device(
        self,
        device_id: str,
        limit: int = MAX_HISTORY_SIZE
    ) -> List[Event]:
        """
        Get event history filtered by device.
        
        Args:
            device_id: Device ID to filter by
            limit: Maximum number of events to return
        
        Returns:
            List of events for the specified device, most recent first
        """
        async with self._lock:
            filtered = [e for e in self._history if e.device_id == device_id]
            events = filtered[-limit:] if limit < len(filtered) else filtered.copy()
            events.reverse()
        
        logger.debug(f"Retrieved {len(events)} events for device {device_id} (limit={limit})")
        return events
    
    def register_home_assistant_callback(self, callback: Callable[[Event], None]) -> None:
        """
        Register a callback to be notified of new events.
        
        The callback will be called asynchronously for each new event.
        
        Args:
            callback: Async function that takes an Event parameter
        """
        self._ha_callbacks.append(callback)
        logger.info(f"Registered Home Assistant callback (total: {len(self._ha_callbacks)})")
    
    def unregister_home_assistant_callback(self, callback: Callable[[Event], None]) -> None:
        """
        Unregister a previously registered callback.
        
        Args:
            callback: The callback function to remove
        """
        if callback in self._ha_callbacks:
            self._ha_callbacks.remove(callback)
            logger.info(f"Unregistered Home Assistant callback (remaining: {len(self._ha_callbacks)})")
    
    async def notify_home_assistant(self, event: Event) -> None:
        """
        Notify Home Assistant about an event.
        
        This method calls all registered callbacks with the event.
        
        Args:
            event: Event to notify about
        
        Validates:
            - Requirements 3.3: Forwards call events to Home Assistant
        """
        await self._notify_callbacks(event)
    
    async def _notify_callbacks(self, event: Event) -> None:
        """
        Internal method to notify all registered callbacks.
        
        Args:
            event: Event to notify about
        """
        if not self._ha_callbacks:
            logger.debug("No Home Assistant callbacks registered")
            return
        
        logger.debug(f"Notifying {len(self._ha_callbacks)} Home Assistant callbacks")
        
        # Call all callbacks
        for callback in self._ha_callbacks:
            try:
                # Check if callback is async
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    # Run sync callback in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, callback, event)
                    
            except Exception as e:
                logger.error(
                    f"Error in Home Assistant callback: {e}",
                    exc_info=True,
                    extra={"event_id": event.id, "callback": callback.__name__}
                )
    
    async def clear_history(self) -> None:
        """Clear all events from history."""
        async with self._lock:
            count = len(self._history)
            self._history.clear()
        
        logger.info(f"Cleared {count} events from history")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about logged events.
        
        Returns:
            Dictionary with event statistics
        """
        stats = {
            "total_events": len(self._history),
            "events_by_type": {},
            "callbacks_registered": len(self._ha_callbacks)
        }
        
        # Count events by type
        for event in self._history:
            event_type = event.type.value
            stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
        
        return stats
