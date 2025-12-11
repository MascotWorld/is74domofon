#!/usr/bin/with-contenv bashio

# Get config values
LOG_LEVEL=$(bashio::config 'log_level')

# Set environment variables
export LOG_LEVEL="${LOG_LEVEL}"
export CONFIG_DIR="/app/config"

bashio::log.info "Starting IS74 Domofon API Server..."
bashio::log.info "Log level: ${LOG_LEVEL}"

# Link config from Home Assistant
if [ -d "/config/is74_domofon" ]; then
    bashio::log.info "Linking config from /config/is74_domofon"
    ln -sf /config/is74_domofon/* /app/config/ 2>/dev/null || true
fi

# Run the API server
cd /app
exec python3 run_api.py

