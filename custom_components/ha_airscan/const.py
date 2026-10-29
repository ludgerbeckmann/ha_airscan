"""Constants for the AirScan integration."""

DOMAIN = "ha_airscan"

CONF_TLS = "tls"
CONF_ROOT = "root"
CONF_RESOLUTION = "resolution"
CONF_COLOR_MODE = "color_mode"
CONF_PAPERLESS_URL = "paperless_url"
CONF_PAPERLESS_TOKEN = "paperless_token"
CONF_PAPERLESS_VERIFY_SSL = "paperless_verify_ssl"
CONF_TAGS = "tags"
CONF_CORRESPONDENT = "correspondent"
CONF_DOCUMENT_TYPE = "document_type"
CONF_BATCH_TIMEOUT = "batch_timeout"
CONF_PAGE_SIZE = "page_size"
CONF_ADF_ALIGN = "adf_align"
CONF_BLANK_DETECTION = "blank_detection"
CONF_BLANK_THRESHOLD = "blank_threshold"
CONF_BATCH_AUTO_SEND = "batch_auto_send"

DEFAULT_PORT = 80
DEFAULT_ROOT = "eSCL"
DEFAULT_RESOLUTION = 300
DEFAULT_COLOR_MODE = "color"
DEFAULT_PAGE_SIZE = "a4"
DEFAULT_ADF_ALIGN = "auto"
DEFAULT_BATCH_TIMEOUT = 30  # minutes, 0 = off

COLOR_MODES = ["color", "grayscale"]
SOURCES = ["platen", "adf"]
PAGE_SIZE_OPTIONS = ["a4", "a5", "letter", "legal", "max"]
ADF_ALIGN_OPTIONS = ["auto", "left", "center", "right"]
DESTINATIONS = ["paperless", "file"]

SERVICE_SCAN = "scan"
EVENT_SCAN_FINISHED = "ha_airscan_scan_finished"
SERVICE_BATCH_ADD = "batch_add"
SERVICE_BATCH_SEND = "batch_send"
SERVICE_BATCH_DISCARD = "batch_discard"
EVENT_BATCH_STALE = "ha_airscan_batch_stale"
EVENT_QUEUE_DELIVERED = "ha_airscan_queue_delivered"
SERVICE_RETRY_QUEUE = "retry_queue"
