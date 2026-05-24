"""Binary sensors (status bits)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JkBmsCoordinator
from .entity import JkBmsBaseEntity
from .protocol import BmsState


@dataclass(frozen=True, kw_only=True)
class JkBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[BmsState], bool | None]


BINARY_SENSORS: tuple[JkBinaryDescription, ...] = (
    JkBinaryDescription(
        key="charging_state",
        name="Charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda s: (s.current is not None and s.current > 0.05),
    ),
    JkBinaryDescription(
        key="discharging_state",
        name="Discharging",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda s: (s.current is not None and s.current < -0.05),
    ),
    JkBinaryDescription(
        key="error_present",
        name="Error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: bool(s.errors_bitmask) if s.errors_bitmask is not None else None,
    ),
    JkBinaryDescription(
        key="balancing",
        name="Balancing",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.balancing,
    ),
    JkBinaryDescription(
        key="dedicated_charger",
        name="Dedicated charger",
        value_fn=lambda s: s.dedicated_charger_switch,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: JkBmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        JkBmsBinarySensor(coordinator, desc) for desc in BINARY_SENSORS
    )


class JkBmsBinarySensor(JkBmsBaseEntity, BinarySensorEntity):
    entity_description: JkBinaryDescription

    def __init__(
        self, coordinator: JkBmsCoordinator, description: JkBinaryDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
