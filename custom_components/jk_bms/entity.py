"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import JkBmsCoordinator


class JkBmsBaseEntity(CoordinatorEntity[JkBmsCoordinator]):
    """Gemeinsame Basisklasse: Device-Info, unique_id-Präfix."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JkBmsCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}" \
            if coordinator.config_entry else f"jk_{coordinator.device_name}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_name)},
            name=self.coordinator.device_name,
            manufacturer="Jikong",
            model="JK BMS",
        )
