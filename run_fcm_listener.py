#!/usr/bin/env python
"""Script to run FCM listener standalone."""

import asyncio
import logging
import sys
from is74_integration.callhook import run_fcm_listener

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("Starting FCM Listener")
    logger.info("=" * 60)
    
    try:
        asyncio.run(run_fcm_listener())
    except KeyboardInterrupt:
        logger.info("FCM Listener stopped by user")
    except Exception as e:
        logger.error(f"FCM Listener error: {e}", exc_info=True)
        sys.exit(1)

