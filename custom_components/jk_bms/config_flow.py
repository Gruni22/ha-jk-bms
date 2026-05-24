"""Config flow for JK BMS."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import serial.tools.list_ports

from .const import (
    CONF_BAUDRATE,
    CONF_DEVICE_ADDRESS,
    CONF_PROTOCOL,
    CONF_SCAN_INTERVAL,
    CONF_SERIAL_PORT,
    DEFAULT_BAUDRATE,
    DEFAULT_DEVICE_ADDRESS,
    DEFAULT_PROTOCOL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PROTOCOLS,
)
from .serial_client import JkSerialClient

_LOGGER = logging.getLogger(__name__)

CONF_MANUAL_PATH = "manual_path"


def _list_serial_ports() -> list[str]:
    """Liefert verfügbare /dev/tty* Ports + /dev/serial/by-id."""
    ports: list[str] = []
    try:
        for p in serial.tools.list_ports.comports():
            ports.append(p.device)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("comports() failed", exc_info=True)
    # Auf Raspberry Pi sind die /dev/serial/by-id-Pfade stabiler:
    import os
    by_id = "/dev/serial/by-id"
    if os.path.isdir(by_id):
        for entry in os.listdir(by_id):
            ports.append(os.path.join(by_id, entry))
    # Dedup, sort
    return sorted(set(ports))


class JkBmsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """UI flow for JK BMS."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_ports: list[str] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            port = user_input.get(CONF_SERIAL_PORT)
            if port == CONF_MANUAL_PATH:
                return await self.async_step_manual()

            await self.async_set_unique_id(f"jk_bms_{port}")
            self._abort_if_unique_id_configured()

            ok = await self._test_connection(
                port, user_input.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
            )
            if not ok:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or port,
                    data=user_input,
                )

        # Erste Anzeige: Ports einsammeln
        self._discovered_ports = await self.hass.async_add_executor_job(
            _list_serial_ports
        )
        port_options = self._discovered_ports + [CONF_MANUAL_PATH]

        schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): vol.In(port_options),
                vol.Optional(CONF_NAME, default="JK BMS"): str,
                vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.All(
                    int, vol.In([9600, 19200, 38400, 57600, 115200])
                ),
                vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(PROTOCOLS),
                vol.Optional(CONF_DEVICE_ADDRESS, default=DEFAULT_DEVICE_ADDRESS): int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    int, vol.Range(min=2, max=600)
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_SERIAL_PORT]
            await self.async_set_unique_id(f"jk_bms_{port}")
            self._abort_if_unique_id_configured()
            ok = await self._test_connection(
                port, user_input.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
            )
            if not ok:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or port, data=user_input
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): str,
                vol.Optional(CONF_NAME, default="JK BMS"): str,
                vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): int,
                vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(PROTOCOLS),
                vol.Optional(CONF_DEVICE_ADDRESS, default=DEFAULT_DEVICE_ADDRESS): int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }
        )
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)

    async def async_step_import(self, import_data: dict[str, Any]) -> FlowResult:
        """YAML import — direkt anlegen, ohne Connection-Test (Boot-Race)."""
        port = import_data[CONF_SERIAL_PORT]
        await self.async_set_unique_id(f"jk_bms_{port}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"JK BMS {port}", data=import_data)

    # --------------------------------------------------------------------- #
    # Connection probe
    # --------------------------------------------------------------------- #
    async def _test_connection(self, port: str, baudrate: int) -> bool:
        client = JkSerialClient(port=port, baudrate=baudrate, timeout=4.0)
        try:
            await client.read_all()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Connection test failed for %s: %s", port, err)
            return False
        finally:
            await client.disconnect()
        return True

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> JkBmsOptionsFlow:
        return JkBmsOptionsFlow(config_entry)


class JkBmsOptionsFlow(config_entries.OptionsFlow):
    """Spätere Anpassungen (Scan-Intervall etc.)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        schema = vol.Schema(
            {
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    int, vol.Range(min=2, max=600)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
