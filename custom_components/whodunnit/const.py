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

# Identity Constants
ID_INDIRECT_AUTOMATION = "automation.indirect"
NAME_INDIRECT_AUTOMATION = "Automation (Indirect)"
NAME_PHYSICAL_SWITCH = "Physical Switch"
NAME_READY = "None"
NAME_UNKNOWN = "Unknown"
NAME_UNKNOWN_USER = "Unknown User"
NAME_SYSTEM_SOURCE = "System (Time/Event)"
NAME_TRACKER_PREFIX = "Tracker"

# State Slugs (Matching strings.json)
STATE_AUTOMATION = "automation"
STATE_MANUAL = "manual"
STATE_UI = "ui"
STATE_MONITORING = "monitoring"
STATE_SYSTEM = "system"
STATE_SCENE = "scene"
STATE_SCRIPT = "script"

# Default Values
EVENT_TIME_DEFAULT = "None"
SOURCE_TYPE_DEFAULT = "None"
SOURCE_ID_DEFAULT = "None"
USER_ID_DEFAULT = "None"
CONTEXT_ID_DEFAULT = "None"