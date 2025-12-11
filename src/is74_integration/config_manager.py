"""Configuration and credential management."""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from datetime import time
from enum import Enum


logger = logging.getLogger(__name__)


class DayOfWeek(str, Enum):
    """Days of the week for schedule configuration."""
    
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


@dataclass
class AutoOpenSchedule:
    """
    Schedule configuration for conditional auto-open.
    
    Attributes:
        days: List of days when auto-open is active
        time_start: Start time for auto-open window (HH:MM format)
        time_end: End time for auto-open window (HH:MM format)
    """
    
    days: List[DayOfWeek]
    time_start: time
    time_end: time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "days": [day.value for day in self.days],
            "time_start": self.time_start.strftime("%H:%M"),
            "time_end": self.time_end.strftime("%H:%M")
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutoOpenSchedule":
        """Create from dictionary."""
        # Parse days
        days = [DayOfWeek(day) for day in data.get("days", [])]
        
        # Parse times
        time_start_str = data.get("time_start", "00:00")
        time_end_str = data.get("time_end", "23:59")
        
        # Parse time strings (HH:MM format)
        time_start = time.fromisoformat(time_start_str)
        time_end = time.fromisoformat(time_end_str)
        
        return cls(
            days=days,
            time_start=time_start,
            time_end=time_end
        )


@dataclass
class AutoOpenConfig:
    """
    Auto-open configuration.
    
    Attributes:
        enabled: Whether auto-open is enabled
        schedules: List of schedules when auto-open should be active
                  If empty, auto-open is always active when enabled
    """
    
    enabled: bool = False
    schedules: List[AutoOpenSchedule] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "enabled": self.enabled,
            "schedules": [schedule.to_dict() for schedule in self.schedules]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutoOpenConfig":
        """Create from dictionary."""
        enabled = data.get("enabled", False)
        schedules_data = data.get("schedules", [])
        schedules = [AutoOpenSchedule.from_dict(s) for s in schedules_data]
        
        return cls(enabled=enabled, schedules=schedules)


class ConfigManager:
    """
    Manages configuration including auto-open settings.
    
    Features:
    - Auto-open configuration management
    - Schedule-based conditional auto-open
    """
    
    def __init__(self):
        """Initialize ConfigManager."""
        self._auto_open_config: AutoOpenConfig = AutoOpenConfig()
        logger.info("ConfigManager initialized")
    
    def get_auto_open_config(self) -> AutoOpenConfig:
        """
        Get current auto-open configuration.
        
        Returns:
            AutoOpenConfig object
        """
        return self._auto_open_config
    
    def set_auto_open_config(self, config: AutoOpenConfig) -> None:
        """
        Set auto-open configuration.
        
        Args:
            config: AutoOpenConfig object
        """
        self._auto_open_config = config
        logger.info(
            f"Auto-open config updated: enabled={config.enabled}, "
            f"schedules={len(config.schedules)}"
        )
    
    def enable_auto_open(self, enabled: bool = True) -> None:
        """
        Enable or disable auto-open.
        
        Args:
            enabled: True to enable, False to disable
        """
        self._auto_open_config.enabled = enabled
        logger.info(f"Auto-open {'enabled' if enabled else 'disabled'}")
    
    def add_auto_open_schedule(self, schedule: AutoOpenSchedule) -> None:
        """
        Add a schedule to auto-open configuration.
        
        Args:
            schedule: AutoOpenSchedule object
        """
        self._auto_open_config.schedules.append(schedule)
        logger.info(
            f"Added auto-open schedule: days={[d.value for d in schedule.days]}, "
            f"time={schedule.time_start}-{schedule.time_end}"
        )
    
    def clear_auto_open_schedules(self) -> None:
        """Clear all auto-open schedules."""
        count = len(self._auto_open_config.schedules)
        self._auto_open_config.schedules.clear()
        logger.info(f"Cleared {count} auto-open schedules")
