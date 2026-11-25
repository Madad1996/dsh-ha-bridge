"""Binary sensor platform for the DeepSeek Harness integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import MANUFACTURER, MODEL, NAME
from .coordinator import DshCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the connectivity sensor."""
    coordinator: DshCoordinator = entry.runtime_data
    async_add_entities([DshOnlineBinarySensor(coordinator, entry)])


class DshOnlineBinarySensor(CoordinatorEntity[DshCoordinator], BinarySensorEntity):
    """Whether the bridge currently answers."""

    _attr_has_entity_name = True
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Attach the sensor to the bridge device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_online"
        version = (coordinator.data or {}).get("version")
        self._attr_device_info = {
            "identifiers": {(entry.domain, entry.entry_id)},
            "name": NAME,
            "manufacturer": MANUFACTURER,
            "model": MODEL,
            "sw_version": version,
            "configuration_url": coordinator.base_url,
        }

    @property
    def is_on(self) -> bool:
        """Return True while the last poll succeeded."""
        return self.coordinator.last_update_success
