"""Sensor platform for JK BMS."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import JkBmsCoordinator
from .entity import JkBmsBaseEntity
from .protocol import BmsState


@dataclass(frozen=True, kw_only=True)
class JkSensorDescription(SensorEntityDescription):
    """Beschreibung eines BMS-Sensors."""

    value_fn: Callable[[BmsState], float | int | None]


SENSORS: tuple[JkSensorDescription, ...] = (
    JkSensorDescription(
        key="total_voltage",
        translation_key="total_voltage",
        name="Total voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: s.total_voltage,
    ),
    JkSensorDescription(
        key="current",
        name="Current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: s.current,
    ),
    JkSensorDescription(
        key="power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.power,
    ),
    JkSensorDescription(
        key="state_of_charge",
        name="State of charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.state_of_charge,
    ),
    JkSensorDescription(
        key="cell_avg_voltage",
        name="Cell avg voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_avg_voltage,
    ),
    JkSensorDescription(
        key="cell_delta_voltage",
        name="Cell delta voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_delta_voltage,
    ),
    JkSensorDescription(
        key="cell_min_voltage",
        name="Cell min voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_min_voltage,
    ),
    JkSensorDescription(
        key="cell_max_voltage",
        name="Cell max voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_max_voltage,
    ),
    JkSensorDescription(
        key="cell_min_index",
        name="Cell min index",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.cell_min_index,
    ),
    JkSensorDescription(
        key="cell_max_index",
        name="Cell max index",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.cell_max_index,
    ),
    JkSensorDescription(
        key="temperature_sensor_1",
        name="Temperature sensor 1",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.temperature_sensor_1,
    ),
    JkSensorDescription(
        key="temperature_sensor_2",
        name="Temperature sensor 2",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.temperature_sensor_2,
    ),
    JkSensorDescription(
        key="temperature_mos",
        name="MOSFET temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda s: s.temperature_mos,
    ),
    JkSensorDescription(
        key="cycle_count",
        name="Cycle count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: s.cycle_count,
    ),
    JkSensorDescription(
        key="cycle_capacity_ah",
        name="Total cycle capacity",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda s: s.cycle_capacity_ah,
    ),
    JkSensorDescription(
        key="cell_count",
        name="Cell count",
        value_fn=lambda s: s.cell_count,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: JkBmsCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(JkBmsSensor(coordinator, desc) for desc in SENSORS)

    # Per-Cell-Sensoren: Anzahl wird aus den BMS-Daten autodetektiert. Es werden
    # nur so viele Sensoren angelegt, wie das BMS tatsächlich Zellen meldet.
    # Wächst die erkannte Zellenzahl bei einem späteren Poll (oder lieferte der
    # erste Poll noch keine Zelldaten), werden fehlende Sensoren nachgelegt.
    known_cells = 0

    @callback
    def _sync_cell_sensors() -> None:
        nonlocal known_cells
        data = coordinator.data
        if data is None:
            return
        detected = len(data.cell_voltages) if data.cell_voltages else (data.cell_count or 0)
        if detected <= known_cells:
            return
        async_add_entities(
            JkBmsCellSensor(coordinator, i) for i in range(known_cells + 1, detected + 1)
        )
        known_cells = detected

    _sync_cell_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_sync_cell_sensors))


class JkBmsSensor(JkBmsBaseEntity, SensorEntity):
    entity_description: JkSensorDescription

    def __init__(
        self, coordinator: JkBmsCoordinator, description: JkSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class JkBmsCellSensor(JkBmsBaseEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: JkBmsCoordinator, idx: int) -> None:
        super().__init__(coordinator, f"cell_{idx}_voltage")
        self._idx = idx
        self._attr_name = f"Cell {idx} voltage"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if not data or not data.cell_voltages:
            return None
        if self._idx > len(data.cell_voltages):
            return None
        return data.cell_voltages[self._idx - 1]

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return bool(super().available and data and self._idx <= len(data.cell_voltages))
