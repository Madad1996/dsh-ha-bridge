"""Binary sensor platform for the DeepSeek Harness integration."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import MANUFACTURER, MODEL, NAME, STALE_AFTER_MINUTES
from .coordinator import DshCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the connectivity sensor."""
    coordinator: DshCoordinator = entry.runtime_data
    async_add_entities([
        DshOnlineBinarySensor(coordinator, entry),
        DshWaitingBinarySensor(coordinator, entry),
        DshStaleBinarySensor(coordinator, entry),
    ])


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


class DshWaitingBinarySensor(CoordinatorEntity[DshCoordinator], BinarySensorEntity):
    """True while DSH waits for an approval decision."""

    _attr_has_entity_name = True
    _attr_translation_key = "waiting"
    _attr_icon = "mdi:hand-back-right-outline"

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Attach the sensor to the bridge device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_waiting"
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
        """Return True while an approval is pending."""
        status = (self.coordinator.data or {}).get("status") or {}
        return str(status.get("state")) == "wartet auf Freigabe"


class DshStaleBinarySensor(CoordinatorEntity[DshCoordinator], BinarySensorEntity):
    """True when the bridge answers but DSH stopped updating its own status."""

    _attr_has_entity_name = True
    _attr_translation_key = "stale"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Attach the sensor to the bridge device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_stale"
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
        """Return True when the last status update is older than the threshold."""
        status = (self.coordinator.data or {}).get("status") or {}
        # Only a working DSH can be stuck: an idle one legitimately has no new status.
        if str(status.get("state")) != "arbeitet":
            return False
        stamp = status.get("updated_at")
        if not stamp:
            return False
        parsed: datetime | None = dt_util.parse_datetime(str(stamp))
        if parsed is None:
            return False
        return dt_util.utcnow() - parsed > timedelta(minutes=STALE_AFTER_MINUTES)
