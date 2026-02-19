# Whodunnit 🕵️

**A Home Assistant Custom Integration - Know exactly what triggered your smart devices.**

Ever found a light on that shouldn't be, or a switch that tripped unexpectedly, and wondered: *was that an automation, someone on the dashboard, a physical button press, or something else?* Whodunnit answers that question with a dedicated diagnostic sensor for each entity you choose to monitor. Whodunnit itself can also be used to trigger automations which depend on the source context. 

---

## Table of Contents

- [What It Does](#what-it-does)
- [How It Works](#how-it-works)
  - [Detection Logic](#detection-logic)
  - [Sensor States](#sensor-states)
  - [Sensor Attributes](#sensor-attributes)
  - [Confidence Levels](#confidence-levels)
  - [History Log](#history-log)
- [Installation](#installation)
  - [HACS (Recommended)](#hacs-recommended)
  - [Manual Installation](#manual-installation)
- [Setup](#setup)
  - [Supported Entity Types](#supported-entity-types)
  - [Helper and Virtual Devices](#helper-and-virtual-devices)
- [Use Cases](#use-cases)
  - [Debugging](#debugging)
  - [Dashboard Cards](#dashboard-cards)
  - [Automations](#automations)
- [Caveats and Limitations](#caveats-and-limitations)
- [What's New](#whats-new-in-v11-19-feb-2026)

---

## What It Does

Whodunnit creates a **diagnostic sensor** for any supported entity in your Home Assistant setup. Each time that entity changes state - or a meaningful attribute changes (such as brightness or colour) - the Whodunnit sensor updates to record:

- **What** caused the change (automation, script, scene, dashboard, physical press, service account, or the system itself)
- **Who** did it (the person's name if triggered via the UI)
- **Which** specific automation, script, or scene was responsible (including its name and entity ID)
- **When** it happened (ISO timestamp)
- **How confident** Whodunnit is in its answer (High, Medium, or Low)
- **A rolling history** of the last 25 trigger events

This information is available as sensor attributes and persists across Home Assistant restarts.

---

## How It Works

### Detection Logic

Home Assistant attaches a **Context** object to every state change. This context carries:
- A unique **context ID** for the event
- A **parent ID** linking it to the action that caused it (e.g. the automation run that fired a service call)
- A **user ID** when a human directly triggered the action via the UI or app

Whodunnit listens to automation, script, and scene events *before* they fire their service calls, caches them by context ID, and then when the target entity's state changes, looks up that change's context in the cache to identify the source.

**The detection cascade works in this order:**

1. **Cache hit on the context ID** -> The state change was caused by an automation, script, or scene that Whodunnit pre-cached. This is a direct, reliable match. *Confidence: High.*

2. **No cache hit, but a `user_id` is on the context** -> A user acted directly via the dashboard, mobile app, or similar UI. Whodunnit resolves the user ID to a friendly name. If the user ID belongs to a service account (Node-RED, AppDaemon, a custom script, etc.) rather than a real person, it is classified as a **Service Account** trigger instead. *Confidence: High (or Low on hardware platforms susceptible to context bleed - see [Caveats](#caveats-and-limitations)).*

3. **No cache hit, but a `parent_id` exists** -> HA was involved (something upstream caused this), but the specific source wasn't in Whodunnit's cache - for example, a sub-automation called by another automation. It is classified as an **Indirect Automation**. *Confidence: Medium.*

4. **No user, no parent, no cache hit** -> The change originated entirely from the device with no Home Assistant involvement. Physical button presses, remote controls, hardware timers (inching), and device-internal firmware events all land here, classified as **Physical / Internal**. *Confidence: High.*

> **Note on attribute-only changes:** Whodunnit also fires when a state stays the same but a monitored attribute changes - for example, dimming a light without turning it on or off. The same detection cascade applies. To avoid flooding the log on continuously-changing sensors, attribute-only changes are rate-limited to one update per second per entity.

---

### Sensor States

The sensor's main state is a short, human-readable label describing the source type:

| State | Displayed As | Meaning |
| :--- | :--- | :--- |
| `monitoring` | Monitoring | Sensor is active but no change has been recorded yet |
| `automation` | Automation | An automation triggered the change |
| `script` | Script | A script triggered the change |
| `scene` | Scene | A scene activation triggered the change |
| `ui` | Dashboard/UI | A human user acted via the Lovelace dashboard or HA app |
| `service` | Service Account | A service account tool (Node-RED, AppDaemon, etc.) triggered the change |
| `system` | System | A time/event-based system action triggered the change |
| `manual` | Manual/Internal | A physical switch, button, or device-internal event triggered the change |

---

### Sensor Attributes

Each Whodunnit sensor exposes the following attributes:

| Attribute | Description | Example |
| :--- | :--- | :--- |
| `source_type` | The category of trigger | `automation`, `user`, `physical`, `service` |
| `source_id` | The entity ID or user ID of the trigger | `automation.morning_lights` |
| `source_name` | Human-readable name of the trigger | `Morning Lights` |
| `context_id` | Home Assistant's internal event ID for this change | `01HS3B...` |
| `user_id` | The HA user UUID (only populated for UI triggers) | `8f2b...` |
| `event_time` | ISO 8601 timestamp of when the change was detected | `2026-02-04T06:47:43` |
| `confidence` | How reliable the classification is | `high`, `medium`, `low` |
| `history_log` | A list of the last 25 trigger events (newest first) | *(see below)* |

---

### Confidence Levels

| Level | Meaning |
| :--- | :--- |
| **High** | Whodunnit is certain about the source. The context matched directly, or there was no HA context at all (physical press). |
| **Medium** | Whodunnit knows HA was involved (a parent context exists) but cannot identify the specific automation. Commonly seen with sub-automations or chained scripts. |
| **Low** | The classification may be unreliable. Most commonly seen on ESPHome devices within 5 seconds of a prior HA command, where the device may have inherited the previous context. See [Caveats](#caveats-and-limitations). |

---

### History Log

The `history_log` attribute stores a rolling list of the last **25 trigger events**, newest first. Each entry in the log contains:

```
event_time    - ISO timestamp of the event
source_type   - Category of trigger
source_id     - Entity or user ID of the trigger
source_name   - Human-readable name
confidence    - High / Medium / Low
```

The log is persisted across Home Assistant restarts. You can inspect it directly on the entity's Attributes tab, access it in templates and automations, or display it using the History Log dashboard card described in the [Use Cases](#use-cases) section below.

---

## Installation

### HACS (Recommended)

1. Open **HACS** in your Home Assistant sidebar.
2. Click the three-dot menu (top right) and choose **Custom repositories**.
3. Paste `https://github.com/sfox38/whodunnit` and select **Integration** as the category.
4. Click **Add**, then find **Whodunnit** in the HACS Integration list and click **Download**.
5. Restart Home Assistant.

### Manual Installation

1. Download the latest release zip from this repository and unpack it.
2. Copy the `whodunnit` folder into your `config/custom_components/` directory. The result should be `config/custom_components/whodunnit/`.
3. Restart Home Assistant.

---

## Setup

After installation and a restart, Whodunnit is available as an integration:

1. Go to **Settings -> Devices & Services**.
2. Click **+ Add Integration** and search for **Whodunnit**.
3. Select the entity you want to monitor from the dropdown picker and click **Submit**.
4. Whodunnit creates a sensor and attaches it to the entity's parent device page.

You can add Whodunnit to as many entities as you like - including multiple entities on the same physical device. Each tracked entity gets its own config entry and its own sensor. Already-tracked entities are automatically hidden from the picker to prevent duplicates.

### Supported Entity Types

The entity picker is filtered to domains that produce meaningful, actionable state changes:

**Physical device domains:** `switch`, `light`, `fan`, `media_player`, `cover`, `lock`, `vacuum`, `siren`, `humidifier`, `climate`, `remote`, `water_heater`, `valve`

**Device-side controls:** `number`, `select`, `button`

**Helper domains:** `input_boolean`, `input_button`, `input_number`, `input_select`, `input_text`

**Other trackable domains:** `alarm_control_panel`, `timer`

Read-only sensor entities are intentionally excluded because their state is driven entirely by the device and cannot be initiated by a user or automation.

**Monitored light attributes:** When tracking a `light` entity, Whodunnit also detects attribute-only changes (state stays `on` but something else changes): `brightness`, `rgb_color`, `rgbw_color`, `xy_color`, `color_temp`, `hs_color`, `effect`.

### Helper and Virtual Devices

Helper entities (`input_boolean`, `input_select`, etc.) do not belong to a physical device. For these, Whodunnit automatically creates a **virtual device** to host the sensor in the HA UI. This virtual device appears in the Devices list under the Whodunnit integration and is automatically removed when you delete the Whodunnit entry for that helper.

---

## Use Cases

### Debugging

A quick look at the Whodunnit sensor on any device's page instantly tells you how the device was last activated. Expand the attributes for the full picture - who, what, when, and how confident the answer is.

<table border="0"><tr><td width="50%" valign="top"><img src="https://github.com/sfox38/whodunnit/blob/main/images/sensor.png" width="100%"></td>
<td width="50%" valign="top"><img src="https://github.com/sfox38/whodunnit/blob/main/images/attributes.png" width="100%"></td></tr></table>

**Common debugging scenarios:**
- *"Why did my bedroom light turn on at 3 am?"* - Check `source_name` to see which automation was responsible.
- *"Did someone manually turn this off, or did an automation do it?"* - `source_type: physical` vs `source_type: automation` answers this immediately.
- *"Which Node-RED flow is affecting this switch?"* - Service account triggers display the HA username of the account, helping you trace the flow.

---

### Dashboard Cards

#### Basic Status Card
<table border="0"><tr><td width="50%" valign="top">This card displays the current trigger source and all its attributes at a glance. Paste the entire block into your dashboard as a new card, and change only the entity ID on the `&target` line.</td>
<td width="50%" valign="top"><img src="https://github.com/sfox38/whodunnit/blob/main/images/sensorcard.png" width="100%"></td></tr></table>


```yaml
##############################################################################
# Whodunnit - Basic Status Card
# Change ONLY the entity ID on the "&target" line below.
##############################################################################
type: entities
title: 🕵️ Whodunnit
show_header_toggle: false
entities:
  - entity: &target sensor.whodunnit_trigger_source
    name: Trigger Source
  - type: divider
  - type: attribute
    entity: *target
    attribute: source_type
    name: Source Type
    icon: mdi:shape-outline
  - type: attribute
    entity: *target
    attribute: source_id
    name: Source ID
    icon: mdi:identifier
  - type: attribute
    entity: *target
    attribute: source_name
    name: Source Name
    icon: mdi:label-outline
  - type: attribute
    entity: *target
    attribute: confidence
    name: Confidence
    icon: mdi:exclamation-thick
  - type: attribute
    entity: *target
    attribute: context_id
    name: Context ID
    icon: mdi:vector-point
  - type: attribute
    entity: *target
    attribute: user_id
    name: User ID
    icon: mdi:vector-point
  - type: attribute
    entity: *target
    attribute: event_time
    name: Event Time
    icon: mdi:clock-outline
```


#### History Log Card

<table border="0"><tr><td width="50%" valign="top">This card displays a rich, colour-coded history of the last 25 trigger events. It requires the **Lovelace HTML Jinja2 Template card** (`custom:html-template-card`), which is available on HACS.

Change only the `entity_id` variable on the first line of the `content` block.
</td>
<td width="50%" valign="top"><img src="https://github.com/sfox38/whodunnit/blob/main/images/historycard.png"></td>
</tr></table>

```yaml
##############################################################################
# Whodunnit - History Log Card
# Requires: custom:html-template-card (HACS)
# Change ONLY the entity_id variable on the first line of the content block.
##############################################################################

type: custom:html-template-card
ignore_line_breaks: true
content: |
  {%- set entity_id = 'sensor.whodunnit_trigger_source' -%}

  {%- set attr = state_attr(entity_id, 'history_log') or [] -%}
  {%- set name = state_attr(entity_id, 'friendly_name') or entity_id -%}
  {%- set cur_type  = state_attr(entity_id, 'source_type')  or '' -%}
  {%- set cur_name  = state_attr(entity_id, 'source_name')  or '' -%}
  {%- set cur_id    = state_attr(entity_id, 'source_id')    or '' -%}
  {%- set cur_conf  = state_attr(entity_id, 'confidence')   or 'high' -%}
  {%- set cur_time  = state_attr(entity_id, 'event_time')   or '' -%}

  {%- set type_colors = {
    'automation': '#6c8ebf',
    'script':     '#7b6bbf',
    'scene':      '#bf8e6c',
    'user':       '#6cbf8e',
    'service':    '#bf6c9a',
    'physical':   '#8e8e9a'
  } -%}
  {%- set type_labels = {
    'automation': 'Automation',
    'script':     'Script',
    'scene':      'Scene',
    'user':       'UI',
    'service':    'Service',
    'physical':   'Physical'
  } -%}
  {%- set conf_colors  = {'high': '#5ce0a0', 'medium': '#e0c85c', 'low': '#e05c5c'} -%}
  {%- set conf_symbols = {'high': '&#9679;', 'medium': '&#9680;', 'low': '&#9675;'} -%}

  {%- set cur_color  = type_colors.get(cur_type,  '#888') -%}
  {%- set cur_label  = type_labels.get(cur_type,  cur_type | title) -%}
  {%- set conf_color  = conf_colors.get(cur_conf,  '#5ce0a0') -%}
  {%- set conf_symbol = conf_symbols.get(cur_conf, '&#9679;') -%}

  <style>
    .wd { font-family: system-ui, sans-serif; text-align: left; margin: -16px; }
    .wd-hdr { padding: 14px 16px 12px; border-bottom: 1px solid rgba(255,255,255,0.08);
              display: flex; align-items: center; justify-content: space-between; }
    .wd-lbl { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.12em;
              color: rgba(255,255,255,0.28); margin-bottom: 3px; }
    .wd-title { font-size: 1rem; font-weight: 600; color: #e8e8f0; }
    .wd-badge { display: inline-flex; align-items: center; border-radius: 6px;
                padding: 5px 10px; border: 1px solid; font-size: 0.72rem;
                font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
    .wd-ts { font-family: monospace; font-size: 0.65rem;
             color: rgba(255,255,255,0.22); margin-top: 4px; text-align: right; }
    .wd-det { padding: 10px 16px; background: rgba(255,255,255,0.02);
              border-bottom: 1px solid rgba(255,255,255,0.06);
              display: flex; justify-content: space-between;
              align-items: center; gap: 12px; }
    .wd-det-name { color: #d8d8e8; font-size: 0.88rem; font-weight: 500; }
    .wd-det-id { font-family: monospace; font-size: 0.7rem;
                 color: rgba(255,255,255,0.27); margin-top: 2px; }
    .wd-conf { text-align: right; flex-shrink: 0; font-size: 0.72rem; font-weight: 500; }
    .wd-conf-lbl { font-size: 0.62rem; color: rgba(255,255,255,0.2); display: block; margin-top: 1px; }
    .wd-cols { display: grid; grid-template-columns: 1fr auto; gap: 0 10px;
               padding: 6px 16px; border-bottom: 1px solid rgba(255,255,255,0.06); }
    .wd-col { font-size: 0.6rem; text-transform: uppercase; letter-spacing: 0.1em;
              color: rgba(255,255,255,0.18); }
    .wd-list { max-height: 460px; overflow-y: auto; }
    .wd-row { display: grid; grid-template-columns: 1fr auto; gap: 0 10px;
              align-items: center; padding: 9px 16px;
              border-bottom: 1px solid rgba(255,255,255,0.04); }
    .wd-row.first { background: rgba(255,255,255,0.035); }
    .wd-badges { display: flex; align-items: center; gap: 6px; margin-bottom: 3px; }
    .wd-tbadge { font-size: 0.67rem; font-weight: 600; letter-spacing: 0.05em;
                 text-transform: uppercase; padding: 1px 6px;
                 border-radius: 4px; border: 1px solid; }
    .wd-cpill { font-size: 0.69rem; opacity: 0.85; }
    .wd-name { font-size: 0.87rem; color: #d8d8e8; font-weight: 500;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .wd-id { font-family: monospace; font-size: 0.7rem; color: rgba(255,255,255,0.27);
             margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .wd-right { text-align: right; flex-shrink: 0; }
    .wd-rts { font-family: monospace; font-size: 0.68rem;
              color: rgba(255,255,255,0.32); white-space: nowrap; }
    .wd-idx { font-size: 0.62rem; color: rgba(255,255,255,0.18); margin-top: 2px; }
    .wd-foot { padding: 8px 16px; border-top: 1px solid rgba(255,255,255,0.06);
               display: flex; justify-content: space-between; align-items: center; }
    .wd-cnt { font-size: 0.63rem; color: rgba(255,255,255,0.18); }
    .wd-leg { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
    .wd-li { font-size: 0.6rem; opacity: 0.6; }
  </style>

  <div class="wd">

    <div class="wd-hdr">
      <div>
        <div class="wd-lbl">Whodunnit</div>
        <div class="wd-title">{{ name | truncate(40, true, '…') }}</div>
      </div>
      <div style="text-align:right;">
        <div class="wd-badge"
             style="color:{{ cur_color }};background:{{ cur_color }}22;border-color:{{ cur_color }}55;">
          {{ cur_label }}
        </div>
        <div class="wd-ts">{{ cur_time[:19] | replace('T', ', ') if cur_time else '-' }}</div>
      </div>
    </div>

    <div class="wd-det">
      <div style="min-width:0;">
        <div class="wd-det-name">{{ cur_name | truncate(42, true, '…') }}</div>
        <div class="wd-det-id">{{ cur_id | truncate(46, true, '…') }}</div>
      </div>
      <div class="wd-conf" style="color:{{ conf_color }};">
        {{ conf_symbol }} {{ cur_conf }}
        <span class="wd-conf-lbl">confidence</span>
      </div>
    </div>

    <div class="wd-cols">
      <div class="wd-col">Source</div>
      <div class="wd-col" style="text-align:right;">Time</div>
    </div>

    <div class="wd-list">
      {%- if attr | length == 0 %}
        <div style="padding:32px 16px;text-align:center;color:rgba(255,255,255,0.2);font-size:0.85rem;">
          No history yet &mdash; waiting for first trigger
        </div>
      {%- else %}
        {%- for entry in attr %}
          {%- set ec     = type_colors.get(entry.source_type,   '#888') -%}
          {%- set el     = type_labels.get(entry.source_type,   entry.source_type | title) -%}
          {%- set ecc    = conf_colors.get(entry.confidence,    '#5ce0a0') -%}
          {%- set ecs    = conf_symbols.get(entry.confidence,   '&#9679;') -%}
          {%- set ets    = entry.event_time[:19] | replace('T', ', ') if entry.event_time else '-' -%}
          {%- set e_name = entry.source_name | truncate(32, true, '…') -%}
          {%- set e_id   = entry.source_id   | truncate(38, true, '…') -%}
          {%- set idx    = loop.index -%}
          <div class="wd-row{{ ' first' if loop.first else '' }}">
            <div style="min-width:0;">
              <div class="wd-badges">
                <span class="wd-tbadge"
                      style="color:{{ ec }};background:{{ ec }}22;border-color:{{ ec }}44;">
                  {{ el }}
                </span>
                <span class="wd-cpill" style="color:{{ ecc }};">
                  {{ ecs }} {{ entry.confidence }}
                </span>
              </div>
              <div class="wd-name">{{ e_name }}</div>
              <div class="wd-id">{{ e_id }}</div>
            </div>
            <div class="wd-right">
              <div class="wd-rts">{{ ets }}</div>
              <div class="wd-idx">{{ 'Latest' if loop.first else '#' ~ idx }}</div>
            </div>
          </div>
        {%- endfor %}
      {%- endif %}
    </div>

    <div class="wd-foot">
      <div class="wd-cnt">{{ attr | length }} of 25 entries</div>
      <div class="wd-leg">
        {%- for key, color in type_colors.items() %}
          <span class="wd-li" style="color:{{ color }};">
            {{ type_labels[key] }}
          </span>
        {%- endfor %}
      </div>
    </div>

  </div>
```

---

### Automations

#### Notify when a device changes state unexpectedly

Trigger the automation off `event_time` rather than the sensor's main state. This fires on every trigger event, including repeated triggers of the same source type.

```yaml
automation:
  - alias: "Notify of unexpected garage light change"
    trigger:
      - platform: state
        entity_id: sensor.garage_light_trigger_source
        attribute: event_time
    action:
      - service: notify.mobile_app
        data:
          title: "Garage Light Update"
          message: >
            The garage light was changed by
            {{ state_attr('sensor.garage_light_trigger_source', 'source_name') }}
            via {{ states('sensor.garage_light_trigger_source') }}.
```

#### Don't let a motion sensor turn off a light that was manually turned on

This prevents a common frustration: you turn a light on at the wall, then the motion sensor's "no motion" timer turns it straight back off.

```yaml
automation:
  - alias: "Smart motion off - respect manual control"
    trigger:
      - platform: state
        entity_id: binary_sensor.office_motion
        to: "off"
    condition:
      - condition: not
        conditions:
          - condition: state
            entity_id: sensor.office_light_trigger_source
            state: "manual"
    action:
      - service: light.turn_off
        target:
          entity_id: light.office_light
```

#### Alert only when a device is triggered by a specific person

```yaml
automation:
  - alias: "Alert when child's bedroom light is turned on"
    trigger:
      - platform: state
        entity_id: sensor.bedroom_light_trigger_source
        attribute: event_time
    condition:
      - condition: template
        value_template: >
          {{ state_attr('sensor.bedroom_light_trigger_source', 'source_name') == 'Alex' }}
    action:
      - service: notify.mobile_app
        data:
          message: "Alex just turned on the bedroom light."
```

#### Log who dimmed a light (attribute-only change)

When a light is already on and someone changes its brightness or colour without toggling the power, the state remains `on` but Whodunnit still detects the change and updates. Trigger your automation off `event_time` to catch these attribute-only events.

```yaml
automation:
  - alias: "Log who dimmed the living room light"
    trigger:
      - platform: state
        entity_id: sensor.living_room_light_trigger_source
        attribute: event_time
    condition:
      - condition: state
        entity_id: light.living_room
        state: "on"
    action:
      - service: logbook.log
        data:
          name: "Living Room Dimmed"
          message: >
            Brightness adjusted by
            {{ state_attr('sensor.living_room_light_trigger_source', 'source_name') }}
            ({{ states('sensor.living_room_light_trigger_source') }})
            - current brightness:
            {{ state_attr('light.living_room', 'brightness') | int | multiply(100) | divide(255) | round }}%.
```

> **Tip:** Because Whodunnit rate-limits attribute-only updates to one per second, rapidly sliding a brightness slider on the dashboard will produce a single log entry for the gesture rather than flooding the log with every intermediate value.

#### Alert when confidence is low (possible misclassification)

```yaml
automation:
  - alias: "Warn on low confidence Whodunnit reading"
    trigger:
      - platform: state
        entity_id: sensor.garage_switch_trigger_source
        attribute: event_time
    condition:
      - condition: template
        value_template: >
          {{ state_attr('sensor.garage_switch_trigger_source', 'confidence') == 'low' }}
    action:
      - service: notify.mobile_app
        data:
          message: >
            Whodunnit is uncertain about what triggered the garage switch.
            Check the attributes for details.
```

---

## Caveats and Limitations

Home Assistant has some quirks that may affect Whodunnit's accuracy in specific, rare circumstances. These are limitations of how HA works internally, not bugs in Whodunnit.

**System Restarts:** Whodunnit's sensor state and history log persist across restarts thanks to HA's RestoreEntity mechanism. However, any state change that occurs *while HA is offline* will not be captured.

**ESPHome Context Bleed:** ESPHome devices reuse the last context received from HA for approximately 5 seconds after receiving a command. If a physical button is pressed within that 5-second window after an HA-triggered command, the physical press may inherit the prior HA context and be misclassified as an automation or UI trigger. When Whodunnit detects this possibility, it reports `confidence: low`. After those 5 seconds, the ESPHome device generates its own fresh context, and accuracy returns to normal.

**Indirect Automations (Medium Confidence):** When a sub-automation is triggered by another automation, the inner automation's context may not be in Whodunnit's cache. Whodunnit will correctly identify that *something* in HA caused the trigger but will report it as `Automation (Indirect)` with `confidence: medium`, rather than naming the specific automation.

**Overloaded or Slow Networks:** Whodunnit caches contexts for 2 minutes to accommodate network latency and busy systems. On severely congested or slow local networks, events may occasionally arrive out of order or not at all.

**Local Polling Devices (e.g. LocalTuya):** Polling-based integrations take a short time to re-establish their state after HA restarts. Allow approximately 60 seconds after a restart before Whodunnit can reliably track these devices.

**Physical vs. Internal Events:** When `source_type` is `physical`, the trigger could be either a genuine physical button press or a device-internal firmware event (such as an inching/auto-off timer). Home Assistant does not distinguish between these at the context level, so Whodunnit cannot either.

---

## What's new in v1.1 (19 Feb 2026)

* Added support for more domains : climate, water_heater, valve, number, select, button, input_button, input_number, input_select, input_text, alarm_control_panel, timer
* Added attribute changes as a trigger source
* Added support for ESPHome devices
* Added support for multiple entities on a single device
* Added `service` status for API events such as Node-RED
* Added `Confidence` attribute High/Medium/Low
* Added a history log in attributes
* Further refinement to the Context cascade to ensure instantaneous and more accurate identification
* Refactored the code to improve memory usage, speed, and stabilty
* Improved error logging
* Improved comments in the source code
* Rewrite of this README.md
