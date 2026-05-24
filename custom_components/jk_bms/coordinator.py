"""DataUpdateCoordinator for JK BMS."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN
from .protocol import BmsState, parse_status_payload
from .serial_client import JkSerialClient

_LOGGER = logging.getLogger(__name__)


class JkBmsCoordinator(DataUpdateCoordinator[BmsState]):
    """Poll-Coordinator. Hält State + Client."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: JkSerialClient,
        scan_interval: int,
        device_name: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({device_name})",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.device_name = device_name

    async def _async_update_data(self) -> BmsState:
        try:
            frame = await self.client.read_all()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"JK BMS read failed: {err}") from err

        try:
            return parse_status_payload(frame.payload)
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"JK BMS decode failed: {err}") from err
