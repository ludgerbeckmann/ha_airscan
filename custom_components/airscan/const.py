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
CONF_BATCH_TIMEOUT = "batch_timeout"
CONF_BATCH_AUTO_SEND = "batch_auto_send"

DEFAULT_PORT = 80
DEFAULT_ROOT = "eSCL"
DEFAULT_RESOLUTION = 300
DEFAULT_COLOR_MODE = "color"
DEFAULT_BATCH_TIMEOUT = 30  # minutes, 0 = off

COLOR_MODES = ["color", "grayscale"]
SOURCES = ["platen", "adf"]
DESTINATIONS = ["paperless", "file"]

SERVICE_SCAN = "scan"
EVENT_SCAN_FINISHED = "airscan_scan_finished"
SERVICE_BATCH_ADD = "batch_add"
SERVICE_BATCH_SEND = "batch_send"
SERVICE_BATCH_DISCARD = "batch_discard"
EVENT_BATCH_STALE = "airscan_batch_stale"
