"""Constants for IS74 Domofon integration."""

DOMAIN = "is74_domofon"

# Configuration keys
CONF_API_URL = "api_url"
CONF_PHONE = "phone"
CONF_CODE = "code"

# Default values
DEFAULT_API_URL = "http://localhost:10777"
DEFAULT_SCAN_INTERVAL = 30

# Platforms
PLATFORMS = ["sensor", "switch", "button", "camera"]

# Attributes
ATTR_DEVICE_ID = "device_id"
ATTR_MAC_ADDRESS = "mac_address"
ATTR_ADDRESS = "address"
ATTR_ENTRANCE = "entrance"
ATTR_FLAT = "flat"
ATTR_IS_ONLINE = "is_online"
ATTR_HAS_CAMERAS = "has_cameras"
ATTR_CAMERA_COUNT = "camera_count"
ATTR_LAST_CALL = "last_call"
ATTR_AUTO_OPEN_ENABLED = "auto_open_enabled"

# Services
SERVICE_OPEN_DOOR = "open_door"
SERVICE_TOGGLE_AUTO_OPEN = "toggle_auto_open"
SERVICE_START_FCM = "start_fcm"
SERVICE_STOP_FCM = "stop_fcm"

# Event types
EVENT_INCOMING_CALL = "is74_domofon_incoming_call"
EVENT_DOOR_OPENED = "is74_domofon_door_opened"
EVENT_AUTO_OPENED = "is74_domofon_auto_opened"

# Icons
ICON_INTERCOM = "mdi:doorbell-video"
ICON_DOOR_OPEN = "mdi:door-open"
ICON_DOOR_CLOSED = "mdi:door-closed"
ICON_CAMERA = "mdi:cctv"
ICON_AUTO_OPEN = "mdi:door-sliding-lock"
ICON_COURIER = "mdi:truck-delivery"
ICON_REJECT = "mdi:phone-hangup"
ICON_WEB_PANEL = "mdi:web"

