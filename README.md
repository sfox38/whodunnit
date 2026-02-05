# Whodunnit 🕵️
**A handy device Sensor for Home Assistant**

`Whodunnit` helps you figure out what actually triggered your smart home devices. It creates a sensor that will tell you whether the device was changed by an automation, a script, a scene, the dashboard, or a physical switch, as well as the user who did it.

---

## How It Works

`Whodunnit` listens to various events in Home Assistant and pieces together what happened.

* **Automations and Scripts**: When these run, `Whodunnit` grabs their name and ID.
* **Service Calls**: Things like `scene.turn_on` get tracked so they can be linked to the actual state change.
* **State Changes**: When something you're tracking changes state, `Whodunnit` checks a few things:
  * It looks in its internal cache to see if an automation or scene or script just fired (it keeps this info handy for 2 minutes in case of network traffic jams).
  * If that's empty, it checks if a user triggered it from the dashboard.
  * Still nothing? It looks for a parent context that might indicate an indirect automation.
  * If all else fails, it determines this was a human interaction (like a physical wall switch) and marks it as `manual`.

---

## Sensor Attributes

Each sensor also gives you these attributes:

| Attribute | What It Tells You | Example |
| :--- | :--- | :--- |
| `source_type` | The type of trigger | `automation`, `script`, `scene`, `user`, `system`, `physical` |
| `source_id` | The actual entity or user ID | `automation.morning_lights` |
| `source_name` | Human-readable name | `Morning Routine` |
| `context_id` | Home Assistant's event ID | `01HS...` |
| `user_id` | User UUID if triggered from UI | `8f2b...` |
| `event_time` | When it happened | `2026-02-04T16:47:43` |

---
## Installation

### Manual
1. Download the `whodunnit` zip archive from this repository and unpack it.
2. Copy the folder into your `custom_components/` directory.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration** and search for `Whodunnit`.

### HACS (Recommended)
1. Open HACS.
2. Click the three dots (top right) > "Custom repositories".
3. Paste the URL of this repository (`https://github.com/sfox38/whodunnit`) and select **Integration** as the category.
4. Click **Download**.

---
## Adding Whodunnit to your Devices
Once installed, `Whodunnit` will appear in your Integrations panel. If you don't see it, click the **"+ Add integration"** button and search for `Whodunnit`.

1. Click on **"Add Service"** (or the + icon) to add a new device to `Whodunnit`.
2. Select your device from the dropdown list and click **Submit**.
3. You will be redirected to that device's Controls page.

**Virtual Devices:**
You can also add `Whodunnit` to Template, Group, and Helper devices. Since these usually lack a dedicated Device page, `Whodunnit` will automatically create one containing just the `Whodunnit` Sensor.

---

## Sample Use Cases

### Debugging

Extremely useful for debugging or just knowing what's going on. A quick look at the Sensor on the Device panel will tell you how the device was last activated. Call up the Attributes for who, why and when:

<table border="0"><tr><td width="50%" valign="top"><img src="https://github.com/sfox38/whodunnit/blob/main/images/sensor.png" width="100%"></td>
<td width="50%" valign="top"><img src="https://github.com/sfox38/whodunnit/blob/main/images/attributes.png" width="100%"></td></tr></table>

### Dashboard

You can also create a dashboard card to provide all the details you need at a glance:
<table border="0"><tr><td width="50%" valign="top"><img src="https://github.com/sfox38/whodunnit/blob/main/images/card.png" width="100%"></td><td width="50%" valign="top">

```yaml
type: entities
title: 🕵️ Whodunnit
show_header_toggle: false
entities:
  - entity: &target sensor.bathroom_light_trigger_source
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
</td></tr></table>

### Automations

Create an automation to inform you when a device changes state:

```yaml
automation:
  - alias: "Notify of unexpected light change"
    trigger:
      - platform: state
        entity_id: sensor.garage_light_trigger_source
        attribute: event_time
    action:
      - service: notify.mobile_app
        data:
          title: "Garage Light Update"
          message: >
            The light was turned on by {{ state_attr('sensor.garage_light_trigger_source', 'source_name') }} 
            via {{ states('sensor.garage_light_trigger_source') }}.
```

### Advanced Automations

Don't let your motion sensor turn off a light that you just turned on at the wall.

```yaml
automation:
  - alias: "Smart Off"
    trigger:
      - platform: state
        entity_id: binary_sensor.motion
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

---

## Caveats

* **System Restarts**: While your Sensor info sticks around after reboots, if a device changes state while HA is down that event will not be recognized by `Whodunnit`.
* **Not 100% accurate**: While `Whodunnit` is normally instantaneous, laggy or busy networks can slow down the `Whodunnit` response time or, rarely, not trigger it at all.
* **Memory-Friendly**: A small cache is used to improve accuracy with slow networks and devices. All cache entries get cleared out after 2 minutes by default.
* **Startup Lag**: If you're using local polling devices (such as LocalTuya), wait about a minute after HA starts up before `Whodunnit` can accurately track these devices.
