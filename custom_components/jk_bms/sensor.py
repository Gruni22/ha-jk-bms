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
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
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

    value_fn: Callable[[BmsState], float | int | str | None]


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
    # --- Leistung aufgeteilt ---
    JkSensorDescription(
        key="charging_power",
        name="Charging power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.charging_power,
    ),
    JkSensorDescription(
        key="discharging_power",
        name="Discharging power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.discharging_power,
    ),
    # --- Abgeleitete Kapazität / Energie (kein eigener BMS-Record) ---
    JkSensorDescription(
        key="capacity_remaining_ah",
        name="Capacity remaining",
        native_unit_of_measurement="Ah",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: s.capacity_remaining_ah,
    ),
    JkSensorDescription(
        key="energy_remaining_wh",
        name="Energy remaining",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: s.energy_remaining_wh,
    ),
    JkSensorDescription(
        key="nominal_capacity_ah",
        name="Nominal capacity",
        native_unit_of_measurement="Ah",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.nominal_capacity_ah,
    ),
    JkSensorDescription(
        key="actual_capacity_ah",
        name="Actual capacity",
        native_unit_of_measurement="Ah",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.actual_capacity_ah,
    ),
    JkSensorDescription(
        key="temperature_sensor_count",
        name="Temperature sensors",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.temperature_sensor_count,
    ),
    # --- Info / Strings (diagnostisch) ---
    JkSensorDescription(
        key="operation_mode",
        name="Operation mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.operation_mode_text,
    ),
    JkSensorDescription(
        key="errors",
        name="Errors",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.errors_text,
    ),
    JkSensorDescription(
        key="battery_type",
        name="Battery type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.battery_type,
    ),
    JkSensorDescription(
        key="device_id",
        name="Device",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.device_id,
    ),
    JkSensorDescription(
        key="software_version",
        name="Software version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.software_version,
    ),
    JkSensorDescription(
        key="manufacturer",
        name="Manufacturer",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.manufacturer,
    ),
    JkSensorDescription(
        key="protocol_version",
        name="Protocol version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.protocol_version,
    ),
    JkSensorDescription(
        key="total_runtime",
        name="Total runtime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        suggested_display_precision=1,
        value_fn=lambda s: s.total_runtime_seconds,
    ),
    JkSensorDescription(
        key="total_runtime_formatted",
        name="Total runtime formatted",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.total_runtime_formatted,
    ),
    # --- Schutz-/Settings-Parameter (diagnostisch) ---
    JkSensorDescription(
        key="current_calibration",
        name="Current calibration",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.current_calibration_a,
    ),
    JkSensorDescription(
        key="sleep_wait_time",
        name="Sleep wait time",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.sleep_wait_time_s,
    ),
    JkSensorDescription(
        key="low_capacity_alarm",
        name="Low capacity alarm",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.low_capacity_alarm,
    ),
    JkSensorDescription(
        key="total_overvoltage_protection",
        name="Total overvoltage protection",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda s: s.total_overvoltage_protection_v,
    ),
    JkSensorDescription(
        key="total_undervoltage_protection",
        name="Total undervoltage protection",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda s: s.total_undervoltage_protection_v,
    ),
    JkSensorDescription(
        key="cell_overvoltage_protection",
        name="Cell overvoltage protection",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_overvoltage_protection_v,
    ),
    JkSensorDescription(
        key="cell_overvoltage_recovery",
        name="Cell overvoltage recovery",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_overvoltage_recovery_v,
    ),
    JkSensorDescription(
        key="cell_overvoltage_delay",
        name="Cell overvoltage delay",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.cell_overvoltage_delay_s,
    ),
    JkSensorDescription(
        key="cell_undervoltage_protection",
        name="Cell undervoltage protection",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_undervoltage_protection_v,
    ),
    JkSensorDescription(
        key="cell_undervoltage_recovery",
        name="Cell undervoltage recovery",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_undervoltage_recovery_v,
    ),
    JkSensorDescription(
        key="cell_undervoltage_delay",
        name="Cell undervoltage delay",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.cell_undervoltage_delay_s,
    ),
    JkSensorDescription(
        key="cell_pressure_difference_protection",
        name="Cell pressure difference protection",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.cell_pressure_difference_protection_v,
    ),
    JkSensorDescription(
        key="discharge_overcurrent_protection",
        name="Discharge overcurrent protection",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.discharge_overcurrent_protection_a,
    ),
    JkSensorDescription(
        key="discharge_overcurrent_delay",
        name="Discharge overcurrent delay",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.discharge_overcurrent_delay_s,
    ),
    JkSensorDescription(
        key="charge_overcurrent_protection",
        name="Charge overcurrent protection",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.charge_overcurrent_protection_a,
    ),
    JkSensorDescription(
        key="charge_overcurrent_delay",
        name="Charge overcurrent delay",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.charge_overcurrent_delay_s,
    ),
    JkSensorDescription(
        key="balance_starting_voltage",
        name="Balance starting voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.balance_starting_voltage_v,
    ),
    JkSensorDescription(
        key="balance_opening_pressure_difference",
        name="Balance opening pressure difference",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=3,
        value_fn=lambda s: s.balance_opening_pressure_difference_v,
    ),
    JkSensorDescription(
        key="power_tube_temp_protection",
        name="Power tube temperature protection",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.power_tube_temp_protection_c,
    ),
    JkSensorDescription(
        key="power_tube_temp_recovery",
        name="Power tube temperature recovery",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.power_tube_temp_recovery_c,
    ),
    JkSensorDescription(
        key="temp_sensor_protection",
        name="Temperature sensor protection",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.temp_sensor_protection_c,
    ),
    JkSensorDescription(
        key="temp_sensor_recovery",
        name="Temperature sensor recovery",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.temp_sensor_recovery_c,
    ),
    JkSensorDescription(
        key="temp_sensor_difference_protection",
        name="Temperature sensor difference protection",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.temp_sensor_difference_protection_c,
    ),
    JkSensorDescription(
        key="charge_high_temp_protection",
        name="Charge high temperature protection",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.charge_high_temp_protection_c,
    ),
    JkSensorDescription(
        key="discharge_high_temp_protection",
        name="Discharge high temperature protection",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.discharge_high_temp_protection_c,
    ),
    JkSensorDescription(
        key="charge_low_temp_protection",
        name="Charge low temperature protection",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.charge_low_temp_protection_c,
    ),
    JkSensorDescription(
        key="charge_low_temp_recovery",
        name="Charge low temperature recovery",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.charge_low_temp_recovery_c,
    ),
    JkSensorDescription(
        key="discharge_low_temp_protection",
        name="Discharge low temperature protection",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.discharge_low_temp_protection_c,
    ),
    JkSensorDescription(
        key="discharge_low_temp_recovery",
        name="Discharge low temperature recovery",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.discharge_low_temp_recovery_c,
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
        super().__init__(coordinator, description.key, entity_id_domain="sensor")
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class JkBmsCellSensor(JkBmsBaseEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: JkBmsCoordinator, idx: int) -> None:
        # Karten-Suffix ist cell_voltage_<n> (nicht cell_<n>_voltage).
        super().__init__(
            coordinator,
            f"cell_{idx}_voltage",
            entity_id_domain="sensor",
            object_id_key=f"cell_voltage_{idx}",
        )
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
