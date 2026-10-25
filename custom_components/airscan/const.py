"""Constants for the AirScan integration."""

DOMAIN = "airscan"

CONF_TLS = "tls"
CONF_ROOT = "root"
CONF_RESOLUTION = "resolution"
CONF_COLOR_MODE = "color_mode"
CONF_PAPERLESS_URL = "paperless_url"
CONF_PAPERLESS_TOKEN = "paperless_token"
CONF_TAGS = "tags"
CONF_CORRESPONDENT = "correspondent"
CONF_DOCUMENT_TYPE = "document_type"

DEFAULT_PORT = 80
DEFAULT_ROOT = "eSCL"
DEFAULT_RESOLUTION = 300
DEFAULT_COLOR_MODE = "color"

COLOR_MODES = ["color", "grayscale"]
SOURCES = ["platen", "adf"]
DESTINATIONS = ["paperless", "file"]

SERVICE_SCAN = "scan"
EVENT_SCAN_FINISHED = "airscan_scan_finished"
