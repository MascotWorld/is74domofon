"""Main entry point for IS74 Integration Service."""
import os
from .logging_config import setup_logging, get_logger


def main():
    """Main entry point."""
    # Get log level from environment or default to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_dir = os.getenv("LOG_DIR", "logs")
    
    # Setup centralized logging system
    setup_logging(
        level=log_level,
        log_dir=log_dir,
    )
    
    logger = get_logger(__name__)
    logger.info("IS74 Integration Service starting...")
    logger.info(f"Log level: {log_level}")


if __name__ == "__main__":
    main()
