"""IS74 Intercom Integration Service for Home Assistant."""

__version__ = "0.1.0"

from .api_client import IS74ApiClient, IS74ApiError
from .auth_manager import AuthManager, TokenSet, AuthenticationError, RateLimitError
from .device_controller import DeviceController, Device, DoorLockStatus, DeviceStatus, DeviceControlError
from .stream_handler import StreamHandler, Camera, VideoStream, StreamError
from .event_manager import EventManager, Event, EventType
from .config_manager import ConfigManager, AutoOpenConfig, AutoOpenSchedule, DayOfWeek
from .auto_open_manager import AutoOpenManager, CallEvent
# Firebase listener imported separately to avoid circular dependency
# from .firebase_listener import FirebaseListener, FirebaseListenerError
from .logging_config import (
    setup_logging,
    get_logger,
    mask_sensitive_data,
    log_error_with_context,
)

__all__ = [
    "IS74ApiClient",
    "IS74ApiError",
    "AuthManager",
    "TokenSet",
    "AuthenticationError",
    "RateLimitError",
    "DeviceController",
    "Device",
    "DoorLockStatus",
    "DeviceControlError",
    "StreamHandler",
    "Camera",
    "VideoStream",
    "StreamError",
    "EventManager",
    "Event",
    "EventType",
    "ConfigManager",
    "AutoOpenConfig",
    "AutoOpenSchedule",
    "DayOfWeek",
    "AutoOpenManager",
    "CallEvent",
    "setup_logging",
    "get_logger",
    "mask_sensitive_data",
    "log_error_with_context",
]
