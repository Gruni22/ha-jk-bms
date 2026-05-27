"""Number platform: editable BMS thresholds (subset)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, REG_BALANCE_TRIGGER_VOLTAGE
from .coordinator import JkBmsCoordinator
from .entity import JkBmsBaseEntity


@dataclass(frozen=True, kw_only=True)
class JkNumberDescription(NumberEntityDescription):
    register: int
    width: int                # 1, 2 oder 4 Byte
    scale: float = 1.0        # Wert vor dem Schreiben mit scale multiplizieren
    state_attr: str | None = None  # Feld in BmsState (read-back), optional


NUMBERS: tuple[JkNumberDescription, ...] = (
    JkNumberDescription(
        key="balance_trigger_voltage",
        name="Balance trigger voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        native_min_value=0.0,
        native_max_value=1.0,
        native_step=0.001,
        mode=NumberMode.BOX,
        register=REG_BALANCE_TRIGGER_VOLTAGE,
        width=4,
        scale=1000.0,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: JkBmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(JkBmsNumber(coordinator, desc) for desc in NUMBERS)


class JkBmsNumber(JkBmsBaseEntity, NumberEntity):
    entity_description: JkNumberDescription

    def __init__(
        self, coordinator: JkBmsCoordinator, description: JkNumberDescription
    ) -> None:
        super().__init__(coordinator, description.key, entity_id_domain="number")
        self.entity_description = description
        self._cached_value: float | None = None

    @property
    def native_value(self) -> float | None:
        # BMS liefert diese Schreib-Register nicht zwingend im Status-Frame zurück.
        # Wir zeigen den zuletzt gesetzten Wert, sonst None.
        return self._cached_value

    async def async_set_native_value(self, value: float) -> None:
        raw = int(round(value * self.entity_description.scale))
        await self.coordinator.client.write_register(
            self.entity_description.register, raw, width=self.entity_description.width
        )
        self._cached_value = value
        self.async_write_ha_state()
