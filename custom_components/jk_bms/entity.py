"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CARD_ENTITY_ID_KEYS, DOMAIN
from .coordinator import JkBmsCoordinator


class JkBmsBaseEntity(CoordinatorEntity[JkBmsCoordinator]):
    """Gemeinsame Basisklasse: Device-Info, unique_id-Präfix, stabile entity_id."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: JkBmsCoordinator,
        key: str,
        *,
        entity_id_domain: str | None = None,
        object_id_key: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        # Entitätsname kommt aus den Übersetzungen (entity.<platform>.<key>.name);
        # fehlt eine Übersetzung, greift der englische `name=` der Description.
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}" \
            if coordinator.config_entry else f"jk_{coordinator.device_name}_{key}"

        # Stabile, sprachunabhängige entity_id, die exakt den Schlüsseln der
        # jk-bms-card entspricht (z. B. sensor.jk_bms_total_voltage). Anzeigename
        # bleibt übersetzt. `entity_id` wirkt nur als Vorschlag für NEU angelegte
        # Entities; bereits registrierte behalten ihre vorhandene entity_id
        # (siehe README – Bestand neu anlegen, um englische IDs zu erhalten).
        if entity_id_domain is not None:
            suffix = object_id_key or CARD_ENTITY_ID_KEYS.get(key, key)
            self.entity_id = (
                f"{entity_id_domain}.{slugify(coordinator.device_name)}_{suffix}"
            )

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data
        sw_version = data.software_version if data else None
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.device_name)},
            name=self.coordinator.device_name,
            manufacturer="Jikong",
            model="JK BMS",
            sw_version=sw_version or None,
        )
