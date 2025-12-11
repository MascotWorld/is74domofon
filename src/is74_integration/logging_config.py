"""Centralized logging configuration for IS74 Integration Service.

This module provides:
- Structured logging with DEBUG, INFO, WARNING, ERROR levels
- Error logging with stack traces
- API request/response logging with sensitive data masking
- Masking of tokens, passwords, and phone numbers
"""

import logging
import logging.handlers
import re
import sys
import traceback
from pathlib import Path
from typing import Optional, Dict, Any


# Patterns for sensitive data masking
SENSITIVE_PATTERNS = [
    # Tokens
    (re.compile(r'"TOKEN"\s*:\s*"[^"]*"', re.IGNORECASE), '"TOKEN": "***MASKED***"'),
    (re.compile(r'"token"\s*:\s*"[^"]*"', re.IGNORECASE), '"token": "***MASKED***"'),
    (re.compile(r'"access_token"\s*:\s*"[^"]*"', re.IGNORECASE), '"access_token": "***MASKED***"'),
    (re.compile(r'"refresh_token"\s*:\s*"[^"]*"', re.IGNORECASE), '"refresh_token": "***MASKED***"'),
    (re.compile(r'"firebase_token"\s*:\s*"[^"]*"', re.IGNORECASE), '"firebase_token": "***MASKED***"'),
    (re.compile(r'"fcm_token"\s*:\s*"[^"]*"', re.IGNORECASE), '"fcm_token": "***MASKED***"'),
    (re.compile(r'"authid"\s*:\s*"[^"]*"', re.IGNORECASE), '"authid": "***MASKED***"'),
    (re.compile(r'"appInstanceIdToken"\s*:\s*"[^"]*"', re.IGNORECASE), '"appInstanceIdToken": "***MASKED***"'),
    (re.compile(r'"appInstanceId"\s*:\s*"[^"]*"', re.IGNORECASE), '"appInstanceId": "***MASKED***"'),
    
    # Passwords
    (re.compile(r'"PASSWORD"\s*:\s*"[^"]*"', re.IGNORECASE), '"PASSWORD": "***MASKED***"'),
    (re.compile(r'"password"\s*:\s*"[^"]*"', re.IGNORECASE), '"password": "***MASKED***"'),
    (re.compile(r'"pass"\s*:\s*"[^"]*"', re.IGNORECASE), '"pass": "***MASKED***"'),
    (re.compile(r'password="[^"]*"', re.IGNORECASE), 'password="***MASKED***"'),
    (re.compile(r'password=\'[^\']*\'', re.IGNORECASE), 'password=\'***MASKED***\''),
    
    # Phone numbers and codes
    (re.compile(r'"phone"\s*:\s*"[^"]*"', re.IGNORECASE), '"phone": "***MASKED***"'),
    (re.compile(r'"code"\s*:\s*"[^"]*"', re.IGNORECASE), '"code": "***MASKED***"'),
    (re.compile(r'"sms_code"\s*:\s*"[^"]*"', re.IGNORECASE), '"sms_code": "***MASKED***"'),
    
    # Authorization headers
    (re.compile(r'Bearer\s+[A-Za-z0-9\-._~+/]+=*'), 'Bearer ***MASKED***'),
    (re.compile(r'Authorization:\s*Bearer\s+[A-Za-z0-9\-._~+/]+=*', re.IGNORECASE), 'Authorization: Bearer ***MASKED***'),
    
    # API keys
    (re.compile(r'"api_key"\s*:\s*"[^"]*"', re.IGNORECASE), '"api_key": "***MASKED***"'),
    (re.compile(r'"apiKey"\s*:\s*"[^"]*"', re.IGNORECASE), '"apiKey": "***MASKED***"'),
    (re.compile(r'X-API-Key:\s*[^\s]+', re.IGNORECASE), 'X-API-Key: ***MASKED***'),
    
    # User IDs (partial masking - show first 4 digits)
    (re.compile(r'"user_id"\s*:\s*(\d{4})\d+', re.IGNORECASE), r'"user_id": "\1****"'),
    (re.compile(r'"USER_ID"\s*:\s*(\d{4})\d+'), r'"USER_ID": "\1****"'),
]


class SensitiveDataFilter(logging.Filter):
    """Logging filter that masks sensitive data in log records."""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter log record by masking sensitive data.
        
        Args:
            record: Log record to filter
            
        Returns:
            True (always allow record, just mask sensitive data)
        """
        # Mask sensitive data in the message
        if isinstance(record.msg, str):
            record.msg = mask_sensitive_data(record.msg)
        
        # Mask sensitive data in arguments
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: mask_sensitive_data(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, (tuple, list)):
                record.args = tuple(
                    mask_sensitive_data(str(arg)) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        
        # Also mask the formatted message if it exists
        if hasattr(record, 'getMessage'):
            try:
                # Get the formatted message and mask it
                original_msg = record.getMessage()
                masked_msg = mask_sensitive_data(original_msg)
                # Update the message if it was masked
                if masked_msg != original_msg:
                    record.msg = masked_msg
                    record.args = ()
            except Exception:
                # If getMessage fails, just continue
                pass
        
        return True


class ErrorStackTraceFormatter(logging.Formatter):
    """Custom formatter that includes full stack traces for errors."""
    
    def formatException(self, exc_info) -> str:
        """
        Format exception with full stack trace.
        
        Args:
            exc_info: Exception information tuple
            
        Returns:
            Formatted exception string with stack trace
        """
        # Get the full stack trace
        result = super().formatException(exc_info)
        
        # Mask sensitive data in stack trace
        result = mask_sensitive_data(result)
        
        return result
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with enhanced error information.
        
        Args:
            record: Log record to format
            
        Returns:
            Formatted log string
        """
        # Format the base message
        result = super().format(record)
        
        # If this is an error with exception info, ensure stack trace is included
        if record.exc_info and record.levelno >= logging.ERROR:
            # The exception info is already added by formatException
            pass
        
        return result


def mask_sensitive_data(text: str) -> str:
    """
    Mask sensitive data in text for logging.
    
    This function applies all sensitive data patterns to mask:
    - Tokens (access, refresh, Firebase, auth)
    - Passwords
    - Phone numbers
    - SMS codes
    - API keys
    - Authorization headers
    
    Args:
        text: Text that may contain sensitive data
        
    Returns:
        Text with sensitive data masked
    """
    if not isinstance(text, str):
        return text
    
    masked = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        masked = pattern.sub(replacement, masked)
    
    return masked


def load_logging_config(config_file: str = "config/logging.yaml") -> Dict[str, Any]:
    """
    Load logging configuration from YAML file.
    
    Args:
        config_file: Path to logging configuration file
        
    Returns:
        Dictionary with logging configuration
    """
    import yaml
    
    try:
        config_path = Path(config_file)
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                return config or {}
        else:
            # Return default config if file doesn't exist
            return {
                'global_level': 'WARNING',
                'modules': {},
                'console_logging': {'enabled': True},
                'file_logging': {'enabled': False},
                'mask_sensitive_data': True
            }
    except Exception as e:
        print(f"Warning: Could not load logging config from {config_file}: {e}")
        return {
            'global_level': 'WARNING',
            'modules': {},
            'console_logging': {'enabled': True},
            'file_logging': {'enabled': False},
            'mask_sensitive_data': True
        }


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    log_dir: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    format_string: Optional[str] = None,
    config_file: Optional[str] = None,
) -> None:
    """
    Configure logging system for IS74 Integration Service.
    
    Sets up:
    - Console handler with colored output (if available)
    - Optional file handler with rotation
    - Sensitive data filtering
    - Error logging with stack traces
    - Structured log format
    - Module-specific log levels from config file
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR) - overridden by config file
        log_file: Optional log file name (default: is74_integration.log)
        log_dir: Optional log directory (default: ./logs)
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup log files to keep
        format_string: Optional custom format string
        config_file: Optional path to logging config YAML file
    """
    # Load configuration from file if provided
    if config_file:
        config = load_logging_config(config_file)
    else:
        config = load_logging_config()  # Try default location
    
    # Use global level from config or parameter
    global_level = config.get('global_level', level).upper()
    numeric_level = getattr(logging, global_level, logging.WARNING)
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Default format string with timestamp, logger name, level, and message
    if format_string is None:
        format_string = (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s"
        )
    
    # Create formatter with stack trace support
    formatter = ErrorStackTraceFormatter(
        format_string,
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Create sensitive data filter
    sensitive_filter = SensitiveDataFilter()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(sensitive_filter)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file or log_dir:
        # Determine log file path
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            log_file_path = log_path / (log_file or "is74_integration.log")
        else:
            log_file_path = Path(log_file or "is74_integration.log")
        
        # Create rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(sensitive_filter)
        root_logger.addHandler(file_handler)
        
        root_logger.info(f"Logging to file: {log_file_path}")
    
    # Apply module-specific log levels
    module_levels = config.get('modules', {})
    if module_levels:
        for module_name, module_level in module_levels.items():
            if module_level:
                module_logger = logging.getLogger(module_name)
                module_numeric_level = getattr(logging, module_level.upper(), numeric_level)
                module_logger.setLevel(module_numeric_level)
    
    # Log initialization
    root_logger.info(
        f"Logging system initialized with global_level={global_level}, "
        f"handlers={len(root_logger.handlers)}, "
        f"module_overrides={len(module_levels)}"
    )


def log_error_with_context(
    logger: logging.Logger,
    message: str,
    exc_info: Optional[Exception] = None,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log error with full context and stack trace.
    
    This is a convenience function for logging errors with:
    - Custom error message
    - Full exception information and stack trace
    - Additional context data
    
    Args:
        logger: Logger instance to use
        message: Error message
        exc_info: Optional exception to log
        context: Optional dictionary of context data
    """
    # Build error message with context
    error_parts = [message]
    
    if context:
        # Mask sensitive data in context
        masked_context = {
            k: mask_sensitive_data(str(v)) if isinstance(v, str) else v
            for k, v in context.items()
        }
        error_parts.append(f"Context: {masked_context}")
    
    full_message = " | ".join(error_parts)
    
    # Log with exception info if provided
    if exc_info:
        logger.error(full_message, exc_info=exc_info)
    else:
        logger.error(full_message, exc_info=True)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    This is a convenience function that ensures the logger
    inherits the configuration from the root logger.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Example usage and testing
if __name__ == "__main__":
    # Setup logging
    setup_logging(level="DEBUG", log_dir="logs")
    
    # Get logger
    logger = get_logger(__name__)
    
    # Test different log levels
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    
    # Test sensitive data masking
    logger.info('Login request: {"phone": "9030896568", "password": "secret123"}')
    logger.info('Token received: {"TOKEN": "abc123xyz", "USER_ID": 123456789}')
    logger.info('Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9')
    
    # Test error logging with stack trace
    try:
        raise ValueError("Test error with sensitive data: password=secret123")
    except Exception as e:
        log_error_with_context(
            logger,
            "Failed to process request",
            exc_info=e,
            context={
                "user_id": 123456789,
                "token": "secret_token_123",
                "phone": "9030896568"
            }
        )
