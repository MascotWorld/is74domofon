#!/usr/bin/env python
"""Script to run the IS74 Integration Service API."""

import asyncio
from is74_integration.callhook import run_fcm_listener
import uvicorn
import os
import logging
import sys
import threading

# Setup logging BEFORE importing the app to ensure Firebase logs are visible
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,
    force=True
)

# Set Firebase loggers to INFO explicitly
logging.getLogger("is74_integration.firebase_registration").setLevel(logging.INFO)
logging.getLogger("is74_integration.firebase_listener").setLevel(logging.INFO)

print("=" * 60)
print("Firebase logging configured for console output")
print(f"Log level: {log_level}")
print("=" * 60)

def run_fcm_in_background():
    """Run FCM listener in a separate thread."""
    try:
        print("[FCM] Starting FCM listener in background thread...")
        asyncio.run(run_fcm_listener())
    except Exception as e:
        print(f"[FCM] Error in FCM listener: {e}")
        logging.error(f"FCM listener error: {e}", exc_info=True)

if __name__ == "__main__":
    # Get configuration from environment
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "10777"))
    uvicorn_log_level = os.getenv("API_LOG_LEVEL", "info").lower()
    reload = os.getenv("API_RELOAD", "false").lower() == "true"
    enable_fcm = os.getenv("ENABLE_FCM", "true").lower() == "true"
    
    print(f"Starting IS74 Integration Service API on {host}:{port}")
    print(f"Uvicorn log level: {uvicorn_log_level}")
    print(f"Application log level: {log_level}")
    print(f"Auto-reload: {reload}")
    print(f"FCM listener: {'enabled' if enable_fcm else 'disabled'}")
    print(f"API Documentation: http://{host}:{port}/docs")
    print(f"ReDoc Documentation: http://{host}:{port}/redoc")
    print("=" * 60)
    
    # Start FCM listener in background thread if enabled
    if enable_fcm:
        fcm_thread = threading.Thread(target=run_fcm_in_background, daemon=True)
        fcm_thread.start()
        print("[FCM] FCM listener thread started")
    
    uvicorn.run(
        "src.is74_integration.api:app",
        host=host,
        port=port,
        reload=reload,
        log_level=uvicorn_log_level  # Uvicorn's own log level (separate from app logging)
    )
    
