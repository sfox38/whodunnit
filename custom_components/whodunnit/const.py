"""Constants for the Whodunnit integration."""

DOMAIN = "whodunnit"
PLATFORMS = ["sensor"]

# Attribute keys
ATTR_SOURCE_TYPE = "source_type"
ATTR_SOURCE_ID = "source_id"
ATTR_SOURCE_NAME = "source_name"
ATTR_CONTEXT_ID = "context_id"
ATTR_USER_ID = "user_id"
ATTR_EVENT_TIME = "event_time"
ATTR_CONFIDENCE = "confidence"
ATTR_HISTORY_LOG = "history_log"

# Confidence levels
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

# Threshold (seconds): a context cache entry older than this on a hardware
# platform entity is considered possibly stale (ESPHome context bleed window).
# ESPHome reuses the last HA-sent context for approximately 5 seconds after
# receiving a command - empirically verified. Within that 5-second window,
# a physical button press may inherit the prior HA context and be misclassified.
# So: cache_age < 5s on an ESPHome entity = CONFIDENCE_LOW (inside bleed window).
#     cache_age > 5s on an ESPHome entity = CONFIDENCE_HIGH (bleed window passed,
#     ESPHome will report its own fresh context for any genuine HA-triggered event).
ESPHOME_BLEED_THRESHOLD = 5.0

# Number of trigger events retained in the history log attribute.
HISTORY_LOG_SIZE = 25

# Hardware integration platforms whose context may bleed from prior HA commands.
# ESPHome is the known offender; others can be added here if observed.
BLEED_PLATFORMS = frozenset({"esphome"})

# Identity Constants
ID_INDIRECT_AUTOMATION = "automation.indirect"
NAME_INDIRECT_AUTOMATION = "Automation (Indirect)"
NAME_PHYSICAL_INTERNAL = "Physical / Internal"
NAME_READY = "None"
NAME_UNKNOWN_USER = "Unknown User"
NAME_SYSTEM_SOURCE = "System (Time/Event)"
NAME_TRACKER_PREFIX = "Whodunnit"
NAME_SERVICE_ACCOUNT = "Service Account"

# State Slugs (Matching strings.json)
STATE_AUTOMATION = "automation"
STATE_MANUAL = "manual"
STATE_UI = "ui"
STATE_MONITORING = "monitoring"
STATE_SYSTEM = "system"
STATE_SCENE = "scene"
STATE_SCRIPT = "script"
STATE_SERVICE = "service"

# Default Values
EVENT_TIME_DEFAULT = "None"
SOURCE_TYPE_DEFAULT = "None"
SOURCE_ID_DEFAULT = "None"
USER_ID_DEFAULT = "None"
CONTEXT_ID_DEFAULT = "None"

SUPPORTED_DOMAINS = [
    # Physical device domains
    "switch", "light", "fan", "media_player",
    "cover", "lock", "vacuum", "siren", "humidifier", "climate",
    "remote", "water_heater", "valve",
    # Number / select / text - device-side
    "number", "select",
    # Button entities - device-side and Helper
    "button", "input_button",
    # Helper domains
    "input_boolean", "input_number", "input_select", "input_text",
    # Other meaningful trackable domains
    "alarm_control_panel", "timer",
]