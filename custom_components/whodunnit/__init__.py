import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er, device_registry as dr
from homeassistant.helpers.event import async_track_device_registry_updated_event
from .const import (
    DOMAIN, 
    PLATFORMS, 
    NAME_TRACKER_PREFIX
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Whodunnit from a config entry with dynamic title syncing."""
    hass.data.setdefault(DOMAIN, {})
    targets = entry.data.get("targets", [])
    if not targets:
        return False

    target_entity = targets[0]
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)

    target_entry = ent_reg.async_get(target_entity)
    device_id = target_entry.device_id if target_entry else None

    @callback
    def update_entry_title(event=None):
        """Syncs the Config Entry title with the actual Device Name or User Name."""
        if device_id:
            device = dev_reg.async_get(device_id)
            device_name = device.name_by_user or device.name
        else:
            device_name = target_entity.split('.')[-1].replace('_', ' ').title()

        final_title = f"{NAME_TRACKER_PREFIX}: {device_name}"
        if entry.title != final_title:
            hass.config_entries.async_update_entry(entry, title=final_title)

    update_entry_title()

    if device_id:
        entry.async_on_unload(
            async_track_device_registry_updated_event(hass, device_id, update_entry_title)
        )

    # Prepare Device Info for the sensor to inherit
    if device_id:
        device = dev_reg.async_get(device_id)
        device_info = {
            "identifiers": device.identifiers,
            "name": device.name_by_user or device.name
        }
    else:
        device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": entry.title,
            "manufacturer": "Whodunnit",
            "model": "Whodunnit Virtual Device",
            "entry_type": dr.DeviceEntryType.SERVICE,
        }
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            **device_info
        )

    hass.data[DOMAIN][entry.entry_id] = {
        "targets": targets,
        "device_info": device_info
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload and remove entities cleanly."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Standard cleanup for entries
        ent_reg = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            ent_reg.async_remove(entity.entity_id)
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok