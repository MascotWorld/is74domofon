"""Simple logging utility with per-module enable/disable."""


class SimpleLogger:
    """Simple logger that can be enabled/disabled per module."""
    
    def __init__(self, module_name: str, enabled: bool = False):
        """
        Initialize logger.
        
        Args:
            module_name: Name of the module
            enabled: Whether logging is enabled
        """
        self.module_name = module_name
        self.enabled = enabled
    
    def _log(self, level: str, message: str):
        """Internal log method."""
        if self.enabled:
            print(f"[{level}] [{self.module_name}] {message}")
    
    def debug(self, message: str):
        """Log debug message."""
        self._log("DEBUG", message)
    
    def info(self, message: str):
        """Log info message."""
        self._log("INFO", message)
    
    def warning(self, message: str):
        """Log warning message."""
        self._log("WARNING", message)
    
    def error(self, message: str, exc_info=None):
        """Log error message."""
        self._log("ERROR", message)
        if exc_info and self.enabled:
            import traceback
            traceback.print_exc()


# Module-specific loggers with enable/disable flags
LOGGERS = {
    "api": SimpleLogger("API", enabled=False),
    "api_client": SimpleLogger("API_CLIENT", enabled=False),
    "auth_manager": SimpleLogger("AUTH", enabled=False),
    "device_controller": SimpleLogger("DEVICE", enabled=False),
    "stream_handler": SimpleLogger("STREAM", enabled=False),
    "event_manager": SimpleLogger("EVENT", enabled=True),
    "firebase_listener": SimpleLogger("FIREBASE", enabled=True),
}


def get_logger(module_name: str) -> SimpleLogger:
    """
    Get logger for module.
    
    Args:
        module_name: Module name (e.g., "api", "auth_manager")
    
    Returns:
        SimpleLogger instance
    """
    # Extract short name from full module path
    short_name = module_name.split(".")[-1]
    
    if short_name in LOGGERS:
        return LOGGERS[short_name]
    
    # Create new logger if not exists (disabled by default)
    logger = SimpleLogger(short_name.upper(), enabled=False)
    LOGGERS[short_name] = logger
    return logger


def enable_logger(module_name: str):
    """Enable logging for specific module."""
    if module_name in LOGGERS:
        LOGGERS[module_name].enabled = True


def disable_logger(module_name: str):
    """Disable logging for specific module."""
    if module_name in LOGGERS:
        LOGGERS[module_name].enabled = False


def enable_all():
    """Enable logging for all modules."""
    for logger in LOGGERS.values():
        logger.enabled = True


def disable_all():
    """Disable logging for all modules."""
    for logger in LOGGERS.values():
        logger.enabled = False
