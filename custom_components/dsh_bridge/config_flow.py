"""Config flow, reauthentication, and reconfiguration for DeepSeek Harness."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientError
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    STATUS_PATH,
    TITLE,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Required(CONF_TOKEN): str,
    }
)

TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): str})

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
    }
)


async def _validate(hass, host: str, port: int, token: str) -> str | None:
    """Return an error key when the bridge cannot be reached, otherwise None."""
    session = async_get_clientsession(hass)
    url = f"http://{host}:{port}{STATUS_PATH}"
    try:
        async with asyncio.timeout(10):
            response = await session.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status == 401:
                return "invalid_auth"
            if response.status != 200:
                return "cannot_connect"
            payload = await response.json(content_type=None)
    except (asyncio.TimeoutError, ClientError, ValueError):
        return "cannot_connect"
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return "cannot_connect"
    return None


class DshConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the DeepSeek Harness config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the bridge address and token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            token = user_input[CONF_TOKEN].strip()
            error = await _validate(self.hass, host, int(user_input[CONF_PORT]), token)
            if error is not None:
                errors["base"] = error
            else:
                await self.async_set_unique_id(f"{host}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=TITLE,
                    data={
                        CONF_HOST: host,
                        CONF_PORT: int(user_input[CONF_PORT]),
                        CONF_TOKEN: token,
                    },
                )
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Start reauthentication after the bridge rejected the token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh bridge token."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reauth_entry_missing")

        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            host = entry.data[CONF_HOST]
            port = int(entry.data[CONF_PORT])
            error = await _validate(self.hass, host, port, token)
            if error is not None:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_TOKEN: token}
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=TOKEN_SCHEMA,
            description_placeholders={"host": entry.data[CONF_HOST], "port": str(entry.data[CONF_PORT])},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change host, port, or token of an existing entry."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reconfigure_entry_missing")

        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            token = user_input[CONF_TOKEN].strip()
            port = int(user_input[CONF_PORT])
            error = await _validate(self.hass, host, port, token)
            if error is not None:
                errors["base"] = error
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={CONF_HOST: host, CONF_PORT: port, CONF_TOKEN: token},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        suggested = {
            CONF_HOST: entry.data[CONF_HOST],
            CONF_PORT: int(entry.data[CONF_PORT]),
            CONF_TOKEN: entry.data[CONF_TOKEN],
        }
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(STEP_USER_DATA_SCHEMA, suggested),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return DshOptionsFlow()


class DshOptionsFlow(OptionsFlow):
    """Adjust the polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and store the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, {CONF_SCAN_INTERVAL: current}
            ),
        )
