"""Constants for the JK BMS integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "jk_bms"

# --- Config keys ---
CONF_SERIAL_PORT: Final = "serial_port"
CONF_BAUDRATE: Final = "baudrate"
CONF_PROTOCOL: Final = "protocol"
CONF_DEVICE_ADDRESS: Final = "device_address"
CONF_SCAN_INTERVAL: Final = "scan_interval"

# --- Protocol selection ---
PROTOCOL_AUTO: Final = "auto"
PROTOCOL_JK02: Final = "jk02"     # alte JK-Bx/Cx-Serie (GPS-/JST-Protokoll)
PROTOCOL_JKPB: Final = "jkpb"     # neue JK-PB-Serie (RS485 Modbus-ähnlich)
PROTOCOLS = [PROTOCOL_AUTO, PROTOCOL_JK02, PROTOCOL_JKPB]

# --- Defaults ---
DEFAULT_BAUDRATE: Final = 115200
DEFAULT_PROTOCOL: Final = PROTOCOL_AUTO
DEFAULT_DEVICE_ADDRESS: Final = 0x00
DEFAULT_SCAN_INTERVAL: Final = 10  # seconds

# --- Frame constants (gemeinsam für beide Varianten) ---
FRAME_HEADER: Final = bytes([0x4E, 0x57])
FRAME_END: Final = 0x68

# Function codes (siehe syssi/esphome-jk-bms/components/jk_modbus/jk_modbus.cpp)
FUNCTION_ACTIVATE: Final = 0x01
FUNCTION_WRITE_REGISTER: Final = 0x02
FUNCTION_READ_REGISTER: Final = 0x03
FUNCTION_PASSWORD: Final = 0x05
FUNCTION_READ_ALL_REGISTERS: Final = 0x06

ADDRESS_READ_ALL: Final = 0x00

# Frame sources
FRAME_SOURCE_BMS: Final = 0x00
FRAME_SOURCE_BLUETOOTH: Final = 0x01
FRAME_SOURCE_GPS: Final = 0x02
FRAME_SOURCE_COMPUTER: Final = 0x03

# Frame types
FRAME_TYPE_READ: Final = 0x00
FRAME_TYPE_REPLY: Final = 0x01
FRAME_TYPE_ACTIVE: Final = 0x02

# --- Holding register addresses (Auswahl, Steuerungs-Switches/Numbers) ---
# Quelle: components/jk_bms/*.cpp in syssi/esphome-jk-bms
REG_CHARGING_SWITCH: Final = 0xAB
REG_DISCHARGING_SWITCH: Final = 0xAC
# Balancer-Freigabe ist Record/Register 0x9D ("active balance switch"), verifiziert
# gegen syssi/esphome-jk-bms. 0xAD ist hingegen "current calibration" (2 Byte) —
# der frühere Wert 0xAD hätte den Balancer-Befehl auf die Strom-Kalibrierung geschrieben.
REG_BALANCER_SWITCH: Final = 0x9D

REG_TOTAL_BATTERY_CAPACITY: Final = 0xAA   # Ah, uint32
REG_CELL_COUNT: Final = 0xA9
REG_BALANCE_TRIGGER_VOLTAGE: Final = 0xA8  # V, *1000

# --- Kompatibilität mit der jk-bms-card (Pho3niX90/jk-bms-card) ---------------
# Die Karte löst Entities als `<domain>.<prefix>_<key>` auf (Default-Prefix
# "jk_bms"). Damit die Karte ohne manuelles Mapping funktioniert, müssen die
# entity_id-Suffixe exakt diesen englischen Schlüsseln entsprechen. Wir setzen
# die entity_id deshalb sprachunabhängig fest (Anzeigenamen bleiben übersetzt).
#
# Dieses Mapping enthält nur Entities, deren internes Schlüsselwort vom
# Karten-Suffix abweicht. Alle übrigen Entities behalten ihren Key als Suffix
# (er stimmt bereits mit der Karte überein, z. B. total_voltage, current, power,
# state_of_charge, charging_power, discharging_power, temperature_sensor_1/2,
# software_version, total_runtime_formatted, errors, balancing).
CARD_ENTITY_ID_KEYS: dict[str, str] = {
    # Sensoren
    "cell_avg_voltage": "average_cell_voltage",
    "cell_delta_voltage": "delta_cell_voltage",
    "cell_min_voltage": "min_cell_voltage",
    "cell_max_voltage": "max_cell_voltage",
    "cell_min_index": "min_voltage_cell",
    "cell_max_index": "max_voltage_cell",
    "temperature_mos": "power_tube_temperature",
    "cycle_count": "charging_cycles",
    "cycle_capacity_ah": "total_charging_cycle_capacity",
    "capacity_remaining_ah": "capacity_remaining",
    "nominal_capacity_ah": "total_battery_capacity_setting",
    # Schalter
    "charging_switch": "charging",
    "discharging_switch": "discharging",
    "balancer_switch": "balancer",
}

# Bekannte Schreib-Register als Mapping name->(addr, type)
# type: "bool" | "u8" | "u16" | "u32_v"  (u32_v = uint32, value*1000 in V)
WRITE_REGISTERS: dict[str, tuple[int, str]] = {
    "charging": (REG_CHARGING_SWITCH, "bool"),
    "discharging": (REG_DISCHARGING_SWITCH, "bool"),
    "balancer": (REG_BALANCER_SWITCH, "bool"),
    "balance_trigger_voltage": (REG_BALANCE_TRIGGER_VOLTAGE, "u32_v"),
    "total_battery_capacity_ah": (REG_TOTAL_BATTERY_CAPACITY, "u32"),
}
