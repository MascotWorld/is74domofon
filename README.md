# IS74 Intercom Integration for Home Assistant

Integration service for IS74 smart intercom system with Home Assistant.

## 🚀 Quick Start

```bash
# Start the API server
python run_api.py

# Open web interface
open http://localhost:10777/
```

See [QUICKSTART.md](QUICKSTART.md) for detailed instructions.

## Features

- 🔐 Secure authentication with 2FA support
- 🚪 Remote door control
- 📹 Live video streaming
- ⏰ Automatic door opening with schedule support
- 📊 Event logging and history
- 🌐 **Modern web interface** for easy management
- 📱 **Mobile-friendly** responsive design
- 🔄 **Real-time updates** and monitoring

## 🌐 Web Interface

The project includes a modern, user-friendly web interface for managing your intercom system.

### Features
- 🔐 Phone-based authentication with SMS
- 🚪 One-click door opening
- 📹 Live camera viewing
- 📋 Event history tracking
- 📊 Real-time status monitoring
- 📱 Fully responsive design

### Screenshots

See [docs/UI_PREVIEW.md](docs/UI_PREVIEW.md) for interface preview.

### Documentation
- [Web UI Guide](docs/WEB_UI.md) - Complete web interface documentation
- [API Documentation](docs/API.md) - REST API reference
- [Quick Start](QUICKSTART.md) - Get started in 5 minutes

## Installation

### Prerequisites

- Python 3.11 or higher
- Home Assistant instance (optional)
- IS74 intercom account

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd is74-intercom-integration
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Start the service:
```bash
python run_api.py
```

5. Open web interface:
```
http://localhost:10777/
```

## API Endpoints

The service provides a REST API for integration:

- `POST /auth/login` - Request SMS authentication code
- `POST /auth/verify` - Verify code and login
- `GET /devices` - List all intercom devices
- `POST /door/open` - Open door remotely
- `GET /cameras` - List all cameras
- `GET /stream/video/{id}` - Get video stream URL
- `GET /events` - Get event history
- `GET /status` - Service status

Full API documentation available at: http://localhost:10777/docs



## Logging

The service uses configurable logging with module-level control.

### Quick Commands

```bash
# Show current log configuration
python manage_logs.py show

# Set global log level
python manage_logs.py global WARNING

# Enable debug for specific module
python manage_logs.py module src.is74_integration.api DEBUG

# Enable Firebase logs
python manage_logs.py module src.is74_integration.simple_firebase_listener INFO

# Enable all debug logs
python manage_logs.py debug

# Reset to defaults
python manage_logs.py reset
```

See [LOGGING.md](LOGGING.md) for complete logging documentation.

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run only unit tests
pytest -m unit

# Run only property-based tests
pytest -m property
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint
flake8 src/ tests/

# Type checking
mypy src/
```

## Project Structure

```
.
├── src/
│   └── is74_integration/
│       ├── api.py                      # REST API endpoints
│       ├── api_client.py               # HTTP client for IS74 API
│       ├── auth_manager.py             # Authentication management
│       ├── device_controller.py        # Device control
│       ├── stream_handler.py           # Video streaming
│       ├── event_manager.py            # Event logging
│       ├── auto_open_manager.py        # Automatic door opening
│       └── logging_config.py           # Logging configuration
├── static/
│   └── index.html                      # Web interface
├── config/
│   ├── config.example.yaml             # Example configuration
│   ├── logging.yaml                    # Logging configuration
│   └── tokens.json                     # Saved authentication tokens
├── manage_logs.py                      # Log management script
├── run_api.py                          # API server launcher
├── requirements.txt                    # Python dependencies
├── QUICKSTART.md                       # Quick start guide
├── LOGGING.md                          # Logging documentation
└── README.md                           # This file
```

## License

MIT
