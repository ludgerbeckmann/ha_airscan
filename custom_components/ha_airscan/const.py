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
EVENT_SCAN_FAILED = "ha_airscan_scan_failed"
EVENT_PRINTER_OFFLINE = "ha_airscan_printer_offline"
EVENT_BUTTON_REJECTED = "ha_airscan_button_rejected"

CONF_NOTIFY_SERVICES = "notify_services"
CONF_NOTIFY_ENTITIES = "notify_entities"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_NOTIFY_SCAN_TYPES = "notify_scan_types"
CONF_NOTIFY_PAPERLESS_TYPES = "notify_paperless_types"
CONF_PAPERLESS_WEBHOOK = "paperless_webhook"
CONF_PAPERLESS_WEBHOOK_ID = "paperless_webhook_id"
PERSISTENT_NOTIFICATION = "persistent_notification"
DEFAULT_NOTIFY_SCAN_TYPES = ["scan_error", "queued", "batch_stale", "printer_offline", "button_rejected"]
DEFAULT_NOTIFY_PAPERLESS_TYPES = ["neu", "frist"]
SERVICE_RETRY_QUEUE = "retry_queue"
SERVICE_SEND_TEST = "send_test"

CONF_BUTTON_ENTITY = "button_entity"
CONF_BUTTON_MAP = "button_map"
CONF_BUTTON_TOPIC = "button_topic"
