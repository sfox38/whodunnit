"""
Whodunnit — Home Assistant Custom Integration
sensor.py: The WhodunnitSensor entity

This file contains the core detective logic. For each tracked entity, one
WhodunnitSensor is created. Its job is to watch for state changes on the target
entity and figure out *what* caused that change — a user tapping the dashboard,
a physical switch, an automation, a scene, a script, or the device itself.

How HA context chaining works (essential background):
  Every state change in HA carries a Context object with three fields:
    - id:        A unique ID for this specific event.
    - parent_id: The ID of the context that triggered this one (e.g. the
                 automation run that caused this service call).
    - user_id:   Set when a human user directly triggered the action via the UI.

  Whodunnit listens to automation/script/scene events *before* they fire their
  service calls, caches those events by context ID, and then when the target
  entity's state changes, looks up the change's context in that cache to
  identify the source.

Detection cascade (in _handle_change):
  1. Context ID found in cache        → Automation / Script / Scene
  2. Context has a user_id            → Dashboard / UI action by a named user
  3. Context has a parent_id (no cache hit) → Indirect automation (context chain
                                              exists but the trigger wasn't cached,
                                              e.g. a sub-automation)
  4. Context has no user_id or parent_id   → Device internal (timer, hardware event)
  5. Fallback                              → Physical switch / manual hardware press
"""

import logging
import time
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE, EVENT_CALL_SERVICE
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_state_change_event

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
    NAME_SYSTEM_SOURCE,
    STATE_INTERNAL,
    NAME_INTERNAL_SOURCE
)

_LOGGER = logging.getLogger(__name__)

# Light attribute names that Whodunnit monitors for attribute-only changes
# (e.g. a brightness or colour change without an on/off state transition).
# Defined as a module-level frozenset so it is created once, not on every event.
_WATCHED_ATTRS = frozenset({
    "brightness", "rgb_color", "rgbw_color",
    "xy_color", "color_temp", "hs_color", "effect"
})

# How long (seconds) a cached context entry remains valid. Contexts are short-
# lived — if no matching state change arrives within this window, the entry is
# stale and should be discarded.
CACHE_TTL = 120

# Maximum number of entries allowed in the context cache at any one time.
# Eviction is oldest-first once this limit is reached. 200 is generous for
# typical home automation use; reduce if memory is a concern.
CACHE_MAX_SIZE = 200


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Create a WhodunnitSensor for each entity listed in the config entry.

    Called by HA after __init__.py has finished setting up the entry. Reads the
    pre-built device_info and target list from hass.data and creates the sensor.
    """
    data = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([
        WhodunnitSensor(ent, data["device_info"], config_entry.entry_id, hass)
        for ent in data["targets"]
    ])


class WhodunnitSensor(SensorEntity, RestoreEntity):
    """A sensor that reports what last triggered a state change on a target entity.

    Inherits from both SensorEntity (standard HA sensor behaviour) and
    RestoreEntity (persists state across HA restarts via the recorder).

    The sensor's native_value is a short slug string (e.g. "automation", "ui",
    "manual") that maps to a human-readable label and icon. Full context — who,
    what, and when — is exposed via extra_state_attributes.
    """

    # Tell HA that this entity's name comes from its translation key + placeholders
    # rather than being set directly. See strings.json → entity.sensor.trigger_source.
    _attr_has_entity_name = True

    # This sensor is event-driven; it updates itself by calling async_write_ha_state().
    # Setting should_poll = False tells HA not to call async_update() on a schedule.
    _attr_should_poll = False

    # Maps to the "trigger_source" entry in strings.json for translated state labels.
    _attr_translation_key = "trigger_source"

    def __init__(self, target_entity, device_info, entry_id, hass):
        """Initialise the sensor.

        Sets up internal state, resolves the entity display name for the sensor
        title, and gets references to the shared context and user caches.

        Args:
            target_entity: The entity_id being monitored (e.g. "switch.garage").
            device_info:   The device_info dict built by __init__.py. Used to
                           attach this sensor to the correct device card in the UI.
            entry_id:      The config entry ID, used to access shared hass.data.
            hass:          The HomeAssistant instance.
        """
        self.hass = hass
        self._target_entity = target_entity
        self._device_info = device_info

        # Both caches live in hass.data so they are shared across all sensors
        # belonging to the same config entry. This avoids duplicate lookups if
        # a future version supports tracking multiple entities per entry.
        entry_data = hass.data[DOMAIN][entry_id]
        self._cache = entry_data["context_cache"]       # context_id → {id, name, type, timestamp}
        self._user_cache = entry_data["user_cache"]     # user_id → (person_entity_id, display_name)

        # --- Sensor display name (translation placeholder) ---
        # The sensor name shown in the UI is "{target} Trigger Source" where
        # {target} is derived by _get_clean_target_name() below. Set the
        # initial value here; it will be refreshed automatically if the target
        # entity is renamed (see async_added_to_hass).
        self._attr_translation_placeholders = {"target": self._get_clean_target_name()}

        # --- Initial sensor state ---
        # The sensor starts in "monitoring" state (shown as "Monitoring" in the UI)
        # until the first state change on the target entity is detected.
        self._state = STATE_MONITORING
        self._source_type = SOURCE_TYPE_DEFAULT
        self._source_id = SOURCE_ID_DEFAULT
        self._source_name = NAME_READY
        self._context_id = CONTEXT_ID_DEFAULT
        self._user_id = USER_ID_DEFAULT
        self._event_time = EVENT_TIME_DEFAULT

        # unique_id ties this sensor to a specific config entry in the registry.
        self._attr_unique_id = f"{target_entity}_whodunnit"

        # Timestamp of the last attribute-only change. Used to debounce rapid
        # attribute updates (e.g. a brightness slider being dragged).
        self._last_attr_time = 0

    def _get_clean_target_name(self) -> str:
        """Derive the display name for the sensor title from the target entity.

        Checks three sources in priority order:
          1. The user-assigned name in the entity registry (set via HA UI rename)
          2. The friendly_name state attribute (set by the integration/device)
          3. A title-cased slug derived from the entity_id

        If the target entity belongs to a device, the device name prefix is
        stripped to avoid redundancy in the UI. For example, a sensor on the
        "Garage Switch" device tracking "Garage Switch Relay 1" will return
        "Relay 1" rather than "Garage Switch Relay 1".

        This method is called at init time and again whenever the target entity
        is renamed, so the sensor title always stays in sync.
        """
        device_name = self._device_info.get("name", "")

        # Priority 1: user-assigned name from the entity registry.
        ent_reg = er.async_get(self.hass)
        entry = ent_reg.async_get(self._target_entity)
        if entry and entry.name:
            target_name = entry.name
        else:
            # Priority 2: friendly_name from state attributes.
            state = self.hass.states.get(self._target_entity)
            if state and state.attributes.get("friendly_name"):
                target_name = state.attributes["friendly_name"]
            else:
                # Priority 3: slug fallback.
                target_name = self._target_entity.split(".")[-1].replace("_", " ").title()

        if device_name and target_name.startswith(device_name):
            # Strip the device name prefix and any leading separator characters.
            clean_target = target_name[len(device_name):].strip()
            if not clean_target or clean_target.startswith(("_", ".")):
                # Stripping left nothing meaningful; use the full name instead.
                clean_target = target_name
        else:
            clean_target = target_name

        return clean_target

    @property
    def device_info(self):
        """Return device info to attach this sensor to the correct device card."""
        return self._device_info

    @property
    def native_value(self):
        """Return the current trigger source slug (e.g. "automation", "ui")."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return detailed metadata about the last detected trigger.

        These attributes are visible on the entity's detail page and can be
        used in automations and templates for fine-grained control.
        """
        return {
            ATTR_SOURCE_TYPE: self._source_type,    # e.g. "automation", "user", "physical"
            ATTR_SOURCE_ID: self._source_id,         # e.g. "automation.turn_off_lights"
            ATTR_SOURCE_NAME: self._source_name,     # e.g. "Turn Off Lights"
            ATTR_CONTEXT_ID: self._context_id,       # Raw HA context ID for debugging
            ATTR_USER_ID: self._user_id,             # HA user ID if triggered via UI
            ATTR_EVENT_TIME: self._event_time        # ISO 8601 timestamp of the change
        }

    @property
    def icon(self):
        """Return an icon that reflects the current trigger source type."""
        icon_map = {
            STATE_MANUAL: "mdi:gesture-tap",
            STATE_UI: "mdi:monitor-dashboard",
            STATE_AUTOMATION: "mdi:robot",
            STATE_SYSTEM: "mdi:cog",
            STATE_MONITORING: "mdi:eye-outline",
            STATE_SCENE: "mdi:palette",
            STATE_SCRIPT: "mdi:script-text-outline",
            STATE_INTERNAL: "mdi:chip",
        }
        return icon_map.get(self._state, "mdi:help-circle-outline")

    async def async_added_to_hass(self):
        """Finalise setup after the entity has been added to HA.

        This is the correct place to restore persisted state and register event
        listeners, because self.hass is fully available and the entity is
        registered in the entity registry by the time this is called.
        """
        # Restore the last known state from the recorder so the sensor shows
        # meaningful data immediately after a restart rather than "Monitoring".
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

        # Listen for automations and scripts firing. These events are emitted
        # *before* the automation/script executes its actions, so by the time
        # the target entity changes state, the context is already in our cache.
        self.async_on_remove(self.hass.bus.async_listen("automation_triggered", self._record_logic_trigger))
        self.async_on_remove(self.hass.bus.async_listen("script_started", self._record_logic_trigger))

        # Listen for service calls. This catches scene activations and any
        # automation/script that calls a service directly, providing a second
        # opportunity to cache the context if the above events were missed.
        self.async_on_remove(self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._record_service_context))

        # Listen for state changes on the target entity. This serves two purposes:
        #   1. Triggers the main detective logic in _handle_change.
        #   2. Detects friendly_name changes so the sensor title can be updated.
        self.async_on_remove(async_track_state_change_event(self.hass, [self._target_entity], self._handle_change))

        # Listen for entity registry updates so the sensor title stays in sync
        # when the user renames the target entity via the HA UI. User-assigned
        # names are stored in the entity registry (entry.name), not in state
        # attributes, so a state change listener won't catch renames.
        @callback
        def _handle_registry_update(event) -> None:
            """Update the sensor title if the target entity's registry name changed."""
            # The event fires for all entity registry changes; filter to ours.
            if event.data.get("entity_id") != self._target_entity:
                return
            # "changes" contains only the fields that actually changed.
            if "name" not in event.data.get("changes", {}):
                return
            self._attr_translation_placeholders = {"target": self._get_clean_target_name()}
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _handle_registry_update)
        )

    def _cleanup_cache(self):
        """Prune the context cache to prevent unbounded memory growth.

        Step 1: Remove entries older than CACHE_TTL seconds.
        Step 2: If the cache is still over CACHE_MAX_SIZE, evict the oldest
                entries first until it fits within the limit.

        Called at the start of every cache write operation.
        """
        now = time.time()

        # Remove expired entries.
        expired_keys = [k for k, v in self._cache.items() if now - v.get("timestamp", 0) > CACHE_TTL]
        for k in expired_keys:
            self._cache.pop(k, None)

        # If still over the size limit, evict oldest entries first.
        if len(self._cache) > CACHE_MAX_SIZE:
            sorted_keys = sorted(self._cache, key=lambda k: self._cache[k].get("timestamp", 0))
            for k in sorted_keys[:len(self._cache) - CACHE_MAX_SIZE]:
                del self._cache[k]

    @callback
    def _record_logic_trigger(self, event):
        """Cache an automation or script trigger event by its context ID.

        Called when "automation_triggered" or "script_started" fires. Stores
        the source entity and name so that when the target entity later changes
        state with a matching context, we can identify the trigger.

        The @callback decorator marks this as a synchronous HA scheduler
        callback. It must not await or perform blocking I/O.
        """
        self._cleanup_cache()

        ctx_id = event.context.id
        entity_id = event.data.get("entity_id")
        name = event.data.get("name")
        domain = entity_id.split(".")[0] if entity_id else "automation"

        if entity_id:
            self._cache[ctx_id] = {
                "id": entity_id,
                "name": name or self._get_friendly(entity_id),
                "type": domain,
                "timestamp": time.time()
            }

    @callback
    def _record_service_context(self, event):
        """Cache a service call event for automation, script, or scene domains.

        Called for every EVENT_CALL_SERVICE event. Only caches entries for the
        domains we care about (automation, script, scene) and only if that
        context ID isn't already in the cache (to avoid overwriting a more
        specific entry from _record_logic_trigger).

        The @callback decorator marks this as a synchronous HA scheduler
        callback. It must not await or perform blocking I/O.
        """
        self._cleanup_cache()

        domain = event.data.get("domain")
        service = event.data.get("service")
        ctx = event.context

        if domain in ["automation", "script", "scene"]:
            service_data = event.data.get("service_data", {})
            target_ids = service_data.get("entity_id", [])

            # entity_id in service_data can be a string or a list.
            if isinstance(target_ids, str):
                target_ids = [target_ids]

            # Use the first target entity as the source ID, or fall back to
            # "domain.service" if no specific entity was targeted.
            logic_id = target_ids[0] if target_ids else f"{domain}.{service}"

            # Only write to cache if this context isn't already recorded — the
            # automation_triggered / script_started events above are more specific.
            if ctx.id not in self._cache:
                self._cache[ctx.id] = {
                    "id": logic_id,
                    "name": self._get_friendly(logic_id),
                    "type": domain,
                    "timestamp": time.time()
                }

    async def _handle_change(self, event):
        """Identify what triggered a state change on the target entity.

        This is the heart of Whodunnit. It runs every time the target entity's
        state or a watched attribute changes, and works through a cascade of
        checks to classify the trigger source.

        Detection cascade:
          1. Context ID (or parent_id) found in cache → Automation/Script/Scene
          2. Context has user_id                      → Dashboard/UI user action
          3. Context has parent_id but no cache hit   → Indirect automation
          4. Context with no user_id or parent_id     → Device internal event
          5. Fallback                                 → Physical switch press
        """
        try:
            new_s = event.data.get("new_state")
            old_s = event.data.get("old_state")

            # Ignore events where state objects are missing (e.g. entity just
            # added or removed from HA).
            if not new_s or not old_s:
                return

            # Check whether any of the watched light attributes changed.
            attr_changed = any(
                new_s.attributes.get(a) != old_s.attributes.get(a)
                for a in _WATCHED_ATTRS
            )

            # Ignore events where neither the state value nor watched attributes changed.
            if new_s.state == old_s.state and not attr_changed:
                return

            # Debounce rapid attribute-only changes (e.g. a brightness slider
            # being dragged continuously). Allow at most one update per 2 seconds
            # for attribute-only changes; state changes (on/off) always pass through.
            now = time.time()
            if new_s.state == old_s.state and (now - self._last_attr_time) < 2.0:
                return

            # Only reset the throttle clock for attribute-only changes.
            # If the state itself changed, we never throttle regardless of
            # what attributes also changed alongside it.
            if attr_changed and new_s.state == old_s.state:
                self._last_attr_time = now

            ctx = event.context

            # Skip if this event shares the same context as the last one we
            # processed — prevents double-counting a single logical action.
            if ctx and ctx.id == self._context_id:
                return

            # Record when this change was detected.
            self._event_time = dt_util.now().isoformat()
            self._context_id = ctx.id if ctx else CONTEXT_ID_DEFAULT

            # --- Detection cascade ---

            # Step 1: Look up the context ID in the cache.
            # The cache is populated by _record_logic_trigger and _record_service_context.
            # Note: we deliberately do NOT fall back to ctx.parent_id here — doing so
            # causes ESPHome physical button presses to be misclassified as UI actions
            # because ESPHome can inherit the parent context of a previous HA action.
            owner = None
            if ctx:
                owner = self._cache.get(ctx.id)

            if owner:
                # A cached automation, script, or scene triggered this change.
                self._state = owner["type"]
                self._source_type = owner["type"]
                self._source_id = owner["id"]
                self._source_name = owner["name"]

            elif ctx and ctx.user_id:
                # Note: during testing, HA was observed to propagate the user context from
                # a dashboard action to subsequent device state confirmations (e.g. ESPHome)
                # for approximately 5 seconds. Within that window, physical button presses
                # may be misclassified as UI actions. The root cause is unclear — it may be
                # intentional HA context propagation or an ESPHome-specific behaviour.

                # Look up the user's person entity for a display name.
                p_id, p_name = await self._get_person_cached(ctx.user_id)
                self._state = STATE_UI
                self._source_type = "user"
                self._source_id = p_id or ctx.user_id
                self._source_name = p_name

            elif ctx and ctx.parent_id:
                # Step 3: There is a parent context but no cache entry for it.
                # This typically means a sub-automation or a chained script that
                # wasn't caught by the pre-fire events (e.g. a notify action that
                # itself triggered another change).
                self._state = STATE_AUTOMATION
                self._source_type = STATE_AUTOMATION
                self._source_id = ID_INDIRECT_AUTOMATION
                self._source_name = NAME_INDIRECT_AUTOMATION

            else:
                # Steps 4 & 5: No user, no parent context.
                if ctx and not ctx.user_id and not ctx.parent_id:
                    # Step 4: The context exists but has no user or parent — this is
                    # a device-internal event such as a hardware timer, a firmware
                    # schedule, or a Zigbee binding that bypasses HA automations.
                    self._state = STATE_INTERNAL
                    self._source_type = STATE_INTERNAL
                    self._source_name = NAME_INTERNAL_SOURCE
                else:
                    # Step 5: Fallback — most likely a physical button or switch
                    # press that triggered the state change directly at the hardware
                    # level without any HA context.
                    self._state = STATE_MANUAL
                    self._source_type = "physical"
                    self._source_name = NAME_PHYSICAL_SWITCH

                self._source_id = self._target_entity

            # Only record user_id when the trigger was a UI action; clear it otherwise.
            self._user_id = ctx.user_id if ctx and self._state == STATE_UI else USER_ID_DEFAULT

            # Push the updated state and attributes to HA.
            self.async_write_ha_state()

        except Exception as err:
            _LOGGER.error("Whodunnit error in _handle_change: %s", err)

    def _get_friendly(self, entity_id):
        """Return the friendly name for an entity, or a title-cased slug fallback.

        Used when populating the cache with human-readable source names for
        automations, scripts, and scenes.
        """
        state = self.hass.states.get(entity_id)
        return (
            state.attributes.get("friendly_name", entity_id.split(".")[-1].replace("_", " ").title())
            if state else entity_id
        )

    async def _get_person_cached(self, user_id):
        """Resolve a HA user ID to a person entity ID and display name.

        Auth lookups (hass.auth.async_get_user) are relatively expensive. Results
        are cached in self._user_cache (shared across sensors in this entry) so
        that repeated actions by the same user only incur the lookup cost once.

        Returns a tuple of (person_entity_id, display_name). person_entity_id
        may be None if the user has no associated person entity.
        """
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        # Look up the HA auth user record for the display name.
        user = await self.hass.auth.async_get_user(user_id)
        name = user.name if user else NAME_UNKNOWN_USER
        p_id = None

        # Try to find a person entity linked to this user ID. Person entities
        # carry a user_id attribute that matches the HA auth user. Finding one
        # lets us return the person entity_id as the source_id, which is more
        # useful in automations than a raw auth UUID.
        for eid in self.hass.states.async_entity_ids("person"):
            s = self.hass.states.get(eid)
            if s and s.attributes.get("user_id") == user_id:
                p_id = eid
                # Prefer the person entity's friendly_name over the auth user name.
                name = s.attributes.get("friendly_name", name)
                break

        self._user_cache[user_id] = (p_id, name)
        return p_id, name