"""Diagnostics support for the DeepSeek Harness integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN
from .coordinator import DshCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with the bridge token redacted."""
    coordinator: DshCoordinator = entry.runtime_data
    entry_data = dict(entry.data)
    if CONF_TOKEN in entry_data:
        entry_data[CONF_TOKEN] = "**REDACTED**"
    return {
        "entry": entry_data,
        "options": dict(entry.options),
        "base_url": coordinator.base_url,
        "last_update_success": coordinator.last_update_success,
        "last_update": coordinator.last_update_success_time.isoformat()
        if getattr(coordinator, "last_update_success_time", None) is not None
        else None,
        "data": coordinator.data,
    }
