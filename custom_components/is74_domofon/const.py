"""Constants for IS74 Domofon integration."""

DOMAIN = "is74_domofon"

# Configuration keys
CONF_AUTO_START_FCM = "auto_start_fcm"
CONF_PHONE = "phone"
CONF_CODE = "code"
CONF_SELECTED_ACCOUNTS = "selected_accounts"
CONF_NAME_OVERRIDES = "name_overrides"

# Default values
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

# Services
SERVICE_OPEN_DOOR = "open_door"
SERVICE_START_FCM = "start_fcm"
SERVICE_STOP_FCM = "stop_fcm"

# Event types
EVENT_INCOMING_CALL = "is74_domofon_incoming_call"
EVENT_DOOR_OPENED = "is74_domofon_door_opened"

# Icons
ICON_INTERCOM = "mdi:doorbell-video"
ICON_DOOR_OPEN = "mdi:door-open"
ICON_DOOR_CLOSED = "mdi:door-closed"
ICON_CAMERA = "mdi:cctv"
ICON_COURIER = "mdi:truck-delivery"
ICON_REJECT = "mdi:phone-hangup"
ICON_WEB_PANEL = "mdi:web"
