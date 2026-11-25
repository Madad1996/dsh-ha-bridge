"""Data update coordinator for the DeepSeek Harness integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from aiohttp import ClientError, ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    STATUS_PATH,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10


class DshCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the DeepSeek Harness status endpoint."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator from one config entry."""
        interval = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
            update_interval=timedelta(seconds=interval),
        )
        self.entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.port: int = entry.data[CONF_PORT]
        self.token: str = entry.data[CONF_TOKEN]

    @property
    def base_url(self) -> str:
        """Return the base URL of the bridge."""
        return f"http://{self.host}:{self.port}"

    @property
    def session(self) -> ClientSession:
        """Return the shared aiohttp session."""
        return async_get_clientsession(self.hass)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the status snapshot."""
        url = f"{self.base_url}{STATUS_PATH}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self.session.get(url, headers=headers)
                if response.status == 401:
                    raise ConfigEntryAuthFailed("Der Brücken-Token wurde abgelehnt (HTTP 401)")
                if response.status != 200:
                    raise UpdateFailed(f"Unerwartete Antwort von DSH: HTTP {response.status}")
                payload = await response.json(content_type=None)
        except asyncio.TimeoutError as err:
            raise UpdateFailed("Zeitüberschreitung beim Abruf des DSH-Status") from err
        except ClientError as err:
            raise UpdateFailed(f"DSH nicht erreichbar: {err}") from err
        except ValueError as err:
            raise UpdateFailed(f"Ungültige Antwort von DSH: {err}") from err
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise UpdateFailed("DSH meldet keinen gültigen Status")
        return payload
