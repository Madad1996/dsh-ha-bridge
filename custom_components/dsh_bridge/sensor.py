"""Sensor platform for the DeepSeek Harness integration."""

from __future__ import annotations

from typing import Any

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import MANUFACTURER, MODEL, NAME
from .coordinator import DshCoordinator

STATUS_ICONS = {
    "bereit": "mdi:robot-happy-outline",
    "arbeitet": "mdi:robot",
    "wartet auf Freigabe": "mdi:hand-back-right-outline",
}

MAX_STATE_LENGTH = 250


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    return dt_util.parse_datetime(value)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the status sensors."""
    coordinator: DshCoordinator = entry.runtime_data
    async_add_entities(
        [
            DshStatusSensor(coordinator, entry),
            DshPendingApprovalsSensor(coordinator, entry),
            DshLastAnswerSensor(coordinator, entry),
            DshLastActivitySensor(coordinator, entry),
            DshResponseTimeSensor(coordinator, entry),
        ]
    )


class DshEntity(CoordinatorEntity[DshCoordinator]):
    """Shared device wiring."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry, key: str) -> None:
        """Attach the entity to the bridge device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
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
    def _status(self) -> dict[str, Any]:
        """Return the status block of the last snapshot."""
        data = self.coordinator.data or {}
        status = data.get("status")
        return status if isinstance(status, dict) else {}

    @property
    def _presence(self) -> dict[str, Any]:
        """Return the presence block of the last snapshot."""
        data = self.coordinator.data or {}
        presence = data.get("presence")
        return presence if isinstance(presence, dict) else {}


class DshStatusSensor(DshEntity, SensorEntity):
    """Current DeepSeek Harness activity."""

    _attr_translation_key = "status"
    _attr_icon = "mdi:robot-happy-outline"

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "status")

    @property
    def native_value(self) -> str | None:
        """Return the current status."""
        return self._status.get("state") or "unbekannt"

    @property
    def icon(self) -> str:
        """Pick an icon for the current status."""
        return STATUS_ICONS.get(self.native_value, "mdi:robot")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the last answer, session, presence, and approval settings."""
        data = self.coordinator.data or {}
        approvals = data.get("approvals")
        session = str(self._status.get("session") or "")
        if len(session) > 8:
            session = session[-8:]
        return {
            "last_answer": self._status.get("detail") or "",
            "session": session,
            "open_approvals": self._status.get("pending", 0),
            "updated_at": self._status.get("updated_at"),
            "home": self._presence.get("home"),
            "voice_approval": (approvals or {}).get("voice") if isinstance(approvals, dict) else None,
            "announce_entity": data.get("announce_entity"),
        }


class DshPendingApprovalsSensor(DshEntity, SensorEntity):
    """Number of permission requests waiting for an answer."""

    _attr_translation_key = "pending_approvals"
    _attr_icon = "mdi:shield-key-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "pending_approvals")

    @property
    def native_value(self) -> int:
        """Return the open approval count."""
        try:
            return int(self._status.get("pending", 0))
        except (TypeError, ValueError):
            return 0


class DshLastAnswerSensor(DshEntity, SensorEntity):
    """The most recent answer DeepSeek Harness produced."""

    _attr_translation_key = "last_answer"
    _attr_icon = "mdi:message-text-outline"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "last_answer")

    @property
    def native_value(self) -> str:
        """Return the answer, shortened to the state limit."""
        text = str(self._status.get("detail") or "")
        return text[:MAX_STATE_LENGTH]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the full text."""
        return {"text": self._status.get("detail") or ""}


class DshLastActivitySensor(DshEntity, SensorEntity):
    """When DSH last reported a change."""

    _attr_translation_key = "last_activity"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "last_activity")

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the last status change."""
        return _parse(self._status.get("updated_at"))


class DshResponseTimeSensor(DshEntity, SensorEntity):
    """Round-trip time of one status poll."""

    _attr_translation_key = "response_time"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "ms"
    _attr_icon = "mdi:speedometer"

    def __init__(self, coordinator: DshCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, "response_time")

    @property
    def native_value(self) -> int | None:
        """Return the measured response time in milliseconds."""
        return self.coordinator.response_ms
