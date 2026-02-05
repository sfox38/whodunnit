import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN

class WhodunnitConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """
    Handle the configuration flow for Whodunnit.
    This UI allows users to select which entities they want to monitor for trigger sources.
    """

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """
        Handle the initial setup step.
        Users select a single entity from supported domains to begin tracking.
        """
        if user_input is not None:
            # Get the selected entity ID from the form
            target = user_input["targets"]
            
            # Create a unique ID per target to prevent multiple trackers for the same entity
            await self.async_set_unique_id(f"{DOMAIN}_{target}")
            self._abort_if_unique_id_configured()

            # Format the target as a list to maintain compatibility with the data model
            user_input["targets"] = [target]
            
            # Generate the integration entry (the 'Card' in the Integrations UI)
            return self.async_create_entry(title="Whodunnit", data=user_input)

        # Build a list of entities already being tracked to hide them from the picker
        existing_entities = []
        for entry in self._async_current_entries():
            existing_entities.extend(entry.data.get("targets", []))

        # Define which device types are compatible with the detective logic
        supported_domains = [
            "switch", "light", "fan", "media_player", "input_boolean", 
            "cover", "lock", "vacuum", "siren", "humidifier", "remote"
        ]

        # Display the selection form to the user
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("targets"): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=supported_domains,
                        multiple=False,  # Enforce one-to-one relationship for easier management
                        exclude_entities=existing_entities,
                    ),
                ),
            }),
        )