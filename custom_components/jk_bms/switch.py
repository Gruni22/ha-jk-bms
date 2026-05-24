"""Switch platform: charge / discharge / balancer."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JkBmsCoordinator
from .entity import JkBmsBaseEntity
from .protocol import BmsState


@dataclass(frozen=True, kw_only=True)
class JkSwitchDescription(SwitchEntityDescription):
    state_fn: Callable[[BmsState], bool | None]
    bms_name: str  # "charging" / "discharging" / "balancer"


SWITCHES: tuple[JkSwitchDescription, ...] = (
    JkSwitchDescription(
        key="charging_switch",
        name="Charging enabled",
        state_fn=lambda s: s.charging_switch,
        bms_name="charging",
    ),
    JkSwitchDescription(
        key="discharging_switch",
        name="Discharging enabled",
        state_fn=lambda s: s.discharging_switch,
        bms_name="discharging",
    ),
    JkSwitchDescription(
        key="balancer_switch",
        name="Balancer enabled",
        state_fn=lambda s: s.balancer_switch,
        bms_name="balancer",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: JkBmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(JkBmsSwitch(coordinator, desc) for desc in SWITCHES)


class JkBmsSwitch(JkBmsBaseEntity, SwitchEntity):
    entity_description: JkSwitchDescription

    def __init__(
        self, coordinator: JkBmsCoordinator, description: JkSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.state_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_switch(self.entity_description.bms_name, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_switch(self.entity_description.bms_name, False)
        await self.coordinator.async_request_refresh()
