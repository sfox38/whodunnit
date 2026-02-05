import logging
import time
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE, EVENT_CALL_SERVICE
from homeassistant.core import EventOrigin
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    ATTR_SOURCE_TYPE,
    ATTR_SOURCE_ID,
    ATTR_SOURCE_NAME,
    ATTR_CONTEXT_ID,
    ATTR_USER_ID,
    ATTR_EVENT_TIME,
    STATE_MONITORING,
    STATE_UI,
    STATE_MANUAL,
    STATE_AUTOMATION,
    STATE_SYSTEM,
    STATE_SCENE,
    STATE_SCRIPT,
    ID_INDIRECT_AUTOMATION,
    NAME_INDIRECT_AUTOMATION,
    NAME_PHYSICAL_SWITCH,
    NAME_READY,
    SOURCE_TYPE_DEFAULT,
    SOURCE_ID_DEFAULT,
    USER_ID_DEFAULT,
    CONTEXT_ID_DEFAULT,
    EVENT_TIME_DEFAULT,
    NAME_UNKNOWN_USER,
    NAME_SYSTEM_SOURCE
)

_LOGGER = logging.getLogger(__name__)

# Global cache to map Home Assistant Context IDs to the logic (automation/script) that created them.
# Structure: { context_id: {"id": entity_id, "name": friendly_name, "type": domain, "timestamp": unix_time} }
CONTEXT_OWNER_CACHE = {}
CACHE_TTL = 120  # Time-to-live for cache entries in seconds

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up sensors from config entry by retrieving target entities and shared device info."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([WhodunnitSensor(ent, data["device_info"]) for ent in data["targets"]])

class WhodunnitSensor(SensorEntity, RestoreEntity):
    """
    Detective sensor that monitors a target entity's state changes.
    It correlates event context IDs with the internal cache to identify the specific trigger source.
    """
    
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "trigger_source"

    def __init__(self, target_entity, device_info):
        """Initialize the sensor with tracking defaults."""
        self._target_entity = target_entity
        self._device_info = device_info
        self._state = STATE_MONITORING
        self._source_type = SOURCE_TYPE_DEFAULT
        self._source_id = SOURCE_ID_DEFAULT
        self._source_name = NAME_READY
        self._context_id = CONTEXT_ID_DEFAULT
        self._user_id = USER_ID_DEFAULT
        self._event_time = EVENT_TIME_DEFAULT
        self._attr_unique_id = f"{target_entity}_whodunnit"

    @property
    def device_info(self): return self._device_info

    @property
    def native_value(self): return self._state

    @property
    def extra_state_attributes(self):
        """Return diagnostic metadata about the last detected trigger."""
        return {
            ATTR_SOURCE_TYPE: self._source_type,
            ATTR_SOURCE_ID: self._source_id,
            ATTR_SOURCE_NAME: self._source_name,
            ATTR_CONTEXT_ID: self._context_id,
            ATTR_USER_ID: self._user_id,
            ATTR_EVENT_TIME: self._event_time
        }

    @property
    def icon(self):
        """Dynamically change the icon based on the current trigger source."""
        icon_map = {
            STATE_MANUAL: "mdi:gesture-tap",
            STATE_UI: "mdi:monitor-dashboard",
            STATE_AUTOMATION: "mdi:robot",
            STATE_SYSTEM: "mdi:cog",
            STATE_MONITORING: "mdi:eye-outline",
            STATE_SCENE: "mdi:palette",
            STATE_SCRIPT: "mdi:script-text-outline",
        }
        return icon_map.get(self._state, "mdi:help-circle-outline")

    async def async_added_to_hass(self):
        """Restore previous state and attach event bus listeners for context capturing."""
        extra_data = await self.async_get_last_state()
        if extra_data and extra_data.state not in [STATE_UNKNOWN, STATE_UNAVAILABLE]:
            self._state = extra_data.state
            attrs = extra_data.attributes
            self._source_type = attrs.get(ATTR_SOURCE_TYPE, SOURCE_TYPE_DEFAULT)
            self._source_id = attrs.get(ATTR_SOURCE_ID, SOURCE_ID_DEFAULT)
            self._source_name = attrs.get(ATTR_SOURCE_NAME, NAME_READY)
            self._context_id = attrs.get(ATTR_CONTEXT_ID, CONTEXT_ID_DEFAULT)
            self._user_id = attrs.get(ATTR_USER_ID, USER_ID_DEFAULT)
            self._event_time = attrs.get(ATTR_EVENT_TIME, EVENT_TIME_DEFAULT)

        # Monitor the bus for logic execution to build our whodunnit cache
        self.async_on_remove(self.hass.bus.async_listen("automation_triggered", self._record_logic_trigger))
        self.async_on_remove(self.hass.bus.async_listen("script_started", self._record_logic_trigger))
        self.async_on_remove(self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._record_service_context))
        
        # Track state changes of the target entity itself
        from homeassistant.helpers.event import async_track_state_change_event
        self.async_on_remove(async_track_state_change_event(self.hass, [self._target_entity], self._handle_change))

    def _cleanup_cache(self):
        """Housekeeping: Prune the global cache to prevent memory growth."""
        global CONTEXT_OWNER_CACHE
        now = time.time()
        expired_keys = [k for k, v in CONTEXT_OWNER_CACHE.items() if now - v.get("timestamp", 0) > CACHE_TTL]
        for k in expired_keys:
            CONTEXT_OWNER_CACHE.pop(k, None)

    async def _record_logic_trigger(self, event):
        """Add specific automation/script names to cache when they are triggered."""
        global CONTEXT_OWNER_CACHE
        self._cleanup_cache()
        ctx_id = event.context.id
        entity_id = event.data.get("entity_id")
        name = event.data.get("name")
        domain = entity_id.split(".")[0] if entity_id else "automation"

        if entity_id:
            CONTEXT_OWNER_CACHE[ctx_id] = {
                "id": entity_id,
                "name": name or self._get_friendly(entity_id),
                "type": domain,
                "timestamp": time.time()
            }

    async def _record_service_context(self, event):
        """Map service calls (scenes/scripts) to context IDs to identify source during state changes."""
        global CONTEXT_OWNER_CACHE
        self._cleanup_cache()
        domain = event.data.get("domain")
        service = event.data.get("service")
        ctx = event.context
        
        # Categorize known logic domains
        if domain in ["automation", "script", "scene"]:
            service_data = event.data.get("service_data", {})
            target_ids = service_data.get("entity_id", [])
            if isinstance(target_ids, str): target_ids = [target_ids]
            logic_id = target_ids[0] if target_ids else f"{domain}.{service}"
            
            if ctx.id not in CONTEXT_OWNER_CACHE:
                CONTEXT_OWNER_CACHE[ctx.id] = {
                    "id": logic_id,
                    "name": self._get_friendly(logic_id),
                    "type": domain,
                    "timestamp": time.time()
                }
        
        # Tag system-originated service calls (e.g., time-based or internal events)
        elif ctx.id not in CONTEXT_OWNER_CACHE and ctx.user_id is None:
            CONTEXT_OWNER_CACHE[ctx.id] = {
                "id": "automation.system",
                "name": NAME_SYSTEM_SOURCE,
                "type": STATE_SYSTEM,
                "timestamp": time.time()
            }

    async def _handle_change(self, event):
        """Main detective logic: Determines if a change was Automation, UI, or Physical."""
        try:
            new_s = event.data.get("new_state")
            old_s = event.data.get("old_state")
            
            # Prevent updates if the state didn't actually change (ignores attribute-only noise)
            if not new_s or not old_s or new_s.state == old_s.state:
                return

            ctx = event.context
            self._event_time = dt_util.now().isoformat()
            self._context_id = ctx.id if ctx else CONTEXT_ID_DEFAULT

            # STEP 1: Check Logic Cache (Highest confidence for automations/scripts)
            owner = None
            if ctx:
                owner = CONTEXT_OWNER_CACHE.get(ctx.id) or CONTEXT_OWNER_CACHE.get(ctx.parent_id)

            if owner:
                self._state = owner["type"]
                self._source_type = owner["type"]
                self._source_id = owner["id"]
                self._source_name = owner["name"]

            # STEP 2: Check User ID (Interactions via Dashboard or Mobile App)
            elif ctx and ctx.user_id:
                p_id, p_name = await self._get_person(ctx.user_id)
                self._state = STATE_UI
                self._source_type = "user"
                self._source_id = p_id or ctx.user_id
                self._source_name = p_name

            # STEP 3: Check Parent IDs (Automations that missed the cache)
            elif ctx and ctx.parent_id:
                self._state = STATE_AUTOMATION
                self._source_type = STATE_AUTOMATION
                self._source_id = ID_INDIRECT_AUTOMATION
                self._source_name = NAME_INDIRECT_AUTOMATION

            # STEP 4: Physical Fallback (LocalTuya/Zigbee/Z-Wave local toggles)
            else:
                self._state = STATE_MANUAL
                self._source_type = "physical"
                self._source_id = self._target_entity
                self._source_name = NAME_PHYSICAL_SWITCH

            self._user_id = ctx.user_id if ctx and self._state == STATE_UI else USER_ID_DEFAULT
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error("Whodunnit error in _handle_change: %s", err)

    def _get_friendly(self, entity_id):
        """Helper to get a readable name from the entity registry or state machine."""
        state = self.hass.states.get(entity_id)
        return state.attributes.get("friendly_name", entity_id.split('.')[-1].replace('_', ' ').title()) if state else entity_id

    async def _get_person(self, user_id):
        """Map a Home Assistant User ID to a Person entity for better UI labeling."""
        user = await self.hass.auth.async_get_user(user_id)
        name = user.name if user else NAME_UNKNOWN_USER
        for eid in self.hass.states.async_entity_ids("person"):
            s = self.hass.states.get(eid)
            if s and s.attributes.get("user_id") == user_id:
                return eid, s.attributes.get("friendly_name", name)
        return None, name