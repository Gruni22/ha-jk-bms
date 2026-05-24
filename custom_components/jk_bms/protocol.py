"""Low-level JK BMS frame protocol.

Implementiert den UART-Frame, wie ihn syssi/esphome-jk-bms verwendet
(components/jk_modbus/jk_modbus.cpp). Frame-Aufbau (vereinfacht):

    [0x4E 0x57] [len_hi len_lo] [terminal x4] [function] [source]
    [type] [address] [payload...] [record x4] [0x68] [crc16_unused x2] [crc_hi crc_lo]

CRC = simple sum of all bytes up to crc field.

Die Payload-Dekodierung (Zellen, SOC, Strom etc.) folgt der jk02-Layout-
Definition aus components/jk_bms/jk_bms.cpp. Sie ist hier bewusst defensiv
implementiert: fehlende Felder ergeben None, kein Crash.
"""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass, field
from typing import Any

from .const import (
    ADDRESS_READ_ALL,
    FRAME_END,
    FRAME_HEADER,
    FRAME_SOURCE_GPS,
    FRAME_TYPE_READ,
    FUNCTION_PASSWORD,
    FUNCTION_READ_ALL_REGISTERS,
    FUNCTION_WRITE_REGISTER,
)

_LOGGER = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# CRC
# --------------------------------------------------------------------------- #
def jk_checksum(data: bytes) -> int:
    """Summen-CRC wie in jk_modbus.cpp::chksum()."""
    return sum(data) & 0xFFFF


# --------------------------------------------------------------------------- #
# Frame Builder
# --------------------------------------------------------------------------- #
def build_read_all_frame() -> bytes:
    """Anfrage 'alle Register lesen' (Function 0x06)."""
    # 21 Bytes wie in jk_modbus.cpp::read_registers()
    frame = bytearray(21)
    frame[0:2] = FRAME_HEADER
    frame[2] = 0x00            # len lb
    frame[3] = 0x13            # len hb (= 19)
    # Bytes 4..7 = terminal (0)
    frame[8] = FUNCTION_READ_ALL_REGISTERS
    frame[9] = FRAME_SOURCE_GPS
    frame[10] = FRAME_TYPE_READ
    frame[11] = ADDRESS_READ_ALL
    # Bytes 12..15 = record (0)
    frame[16] = FRAME_END
    crc = jk_checksum(frame[:17])
    # Bytes 17,18 = crc unused
    frame[19] = (crc >> 8) & 0xFF
    frame[20] = crc & 0xFF
    return bytes(frame)


def build_write_frame(
    function: int, address: int, value: int | bytes
) -> bytes:
    """Schreib-/Steuerframe (Function 0x02 / 0x05).

    `value` kann int (1 Byte) oder bytes (mehrere Bytes für u16/u32) sein.
    Frame-Layout aus jk_modbus.cpp::send().
    """
    if isinstance(value, int):
        payload = bytes([value & 0xFF])
    else:
        payload = bytes(value)

    # Original syssi send() schreibt nur 1 Datenbyte (frame[12]).
    # Für u16/u32 erweitern wir die Datenlänge entsprechend; der Header
    # data_len-Wert deckt das ab.
    data_bytes = len(payload)
    frame = bytearray(21 + data_bytes)
    frame[0:2] = FRAME_HEADER
    data_len = 0x13 + data_bytes  # entspricht dem alten 0x13 + extra bytes
    frame[2] = (data_len >> 8) & 0xFF
    frame[3] = data_len & 0xFF
    # 4..7 terminal
    frame[8] = function
    frame[9] = FRAME_SOURCE_GPS
    frame[10] = FRAME_TYPE_READ
    frame[11] = address & 0xFF
    frame[12:12 + data_bytes] = payload
    # record (4 Bytes, 0)
    frame[12 + data_bytes + 4] = FRAME_END
    crc_end = 12 + data_bytes + 5   # bis inkl. 0x68
    crc = jk_checksum(frame[:crc_end])
    frame[-2] = (crc >> 8) & 0xFF
    frame[-1] = crc & 0xFF
    return bytes(frame)


def build_authenticate_frame() -> bytes:
    """Passwort-Frame (FUNCTION 0x05). Muss vor Schreib-Frames gesendet werden."""
    return build_write_frame(FUNCTION_PASSWORD, 0x00, 0x00)


def build_set_register_frame(address: int, value: int, width: int = 1) -> bytes:
    """Holding-Register schreiben.

    width: 1, 2 oder 4 Byte (big-endian).
    """
    if width == 1:
        data: bytes = bytes([value & 0xFF])
    elif width == 2:
        data = struct.pack(">H", value & 0xFFFF)
    elif width == 4:
        data = struct.pack(">I", value & 0xFFFFFFFF)
    else:
        raise ValueError(f"Unsupported register width: {width}")
    return build_write_frame(FUNCTION_WRITE_REGISTER, address, data)


# --------------------------------------------------------------------------- #
# Frame Parser (Stream)
# --------------------------------------------------------------------------- #
@dataclass
class JkFrame:
    """Ein vollständig empfangenes JK-Frame."""

    address: int
    function: int
    payload: bytes
    raw: bytes


class FrameParser:
    """Streaming-Parser. Bytes per `feed()` einwerfen, Frames per `pop()` rausholen.

    Sehr nahe an jk_modbus.cpp::parse_jk_modbus_byte_().
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._frames: list[JkFrame] = []

    def feed(self, data: bytes) -> None:
        for b in data:
            self._step(b)

    def pop(self) -> JkFrame | None:
        if not self._frames:
            return None
        return self._frames.pop(0)

    # -- intern --
    def _step(self, byte: int) -> None:
        self._buf.append(byte)
        at = len(self._buf) - 1
        raw = self._buf

        # Header sync
        if at == 0:
            if raw[0] != 0x4E:
                self._buf.clear()
            return
        if at == 1:
            if raw[1] != 0x57:
                _LOGGER.debug("Invalid header: %02X %02X", raw[0], raw[1])
                self._buf.clear()
            return
        if at in (2, 3):
            return

        # data_len = uint16 BE aus Bytes 2..3
        data_len = (raw[2] << 8) | raw[3]

        # bis data_len-1 reine Payload sammeln, bei data_len und data_len+1 kommen CRC bytes
        if at < data_len + 1:
            # Schutz gegen wild gewordene Pakete
            if len(raw) > 4096:
                _LOGGER.debug("Buffer overflow protection, clearing")
                self._buf.clear()
            return

        # Vollständig: at == data_len + 1
        computed = jk_checksum(bytes(raw[:data_len]))
        remote = (raw[data_len] << 8) | raw[data_len + 1]
        if computed != remote:
            _LOGGER.warning("CRC mismatch: 0x%04X != 0x%04X", computed, remote)
            self._buf.clear()
            return

        # terminal/address (4 byte) liegt bei 4..7
        address = raw[4]
        function = raw[8]
        # Layout (Offsets vom Frame-Start), wie syssi/esphome-jk-bms es nutzt:
        #   0..1      Header 4E 57
        #   2..3      data_len (uint16 BE) — gibt die Länge bis vor dem letzten
        #             CRC-Byte an. Frame-Gesamtlänge = data_len + 2.
        #   4..7      Terminal/Adresse (4 Byte)
        #   8         Function
        #   9         Source
        #   10        Type
        #   11..      Payload  (Ende = data_len - 3, weil die letzten 3 Bytes
        #             0x68 + 2 Byte CRC sind. Record + crc_unused liegen vor 0x68
        #             und sind hier Teil des "payload"-Bereichs — Decoder muss
        #             sie als unbekannte Records überspringen, oder wir trimmen
        #             unten zusätzlich.)
        payload = bytes(raw[11:data_len - 3])

        self._frames.append(
            JkFrame(address=address, function=function, payload=payload, raw=bytes(raw[: data_len + 2]))
        )
        self._buf.clear()


# --------------------------------------------------------------------------- #
# Payload-Decoder (status frame, function 0x06)
# --------------------------------------------------------------------------- #
@dataclass
class BmsState:
    """Dekodierter BMS-Status. Felder sind alle Optional, damit Teildaten ok sind."""

    cell_voltages: list[float] = field(default_factory=list)  # in V
    cell_count: int | None = None
    cell_avg_voltage: float | None = None
    cell_delta_voltage: float | None = None
    cell_min_voltage: float | None = None
    cell_max_voltage: float | None = None
    cell_min_index: int | None = None
    cell_max_index: int | None = None

    temperature_sensor_1: float | None = None  # °C
    temperature_sensor_2: float | None = None
    temperature_mos: float | None = None
    temperature_sensor_count: int | None = None

    total_voltage: float | None = None      # V
    current: float | None = None            # A (positive = charge)
    power: float | None = None              # W
    charging_power: float | None = None     # W (>=0)
    discharging_power: float | None = None  # W (>=0)
    state_of_charge: float | None = None    # %
    capacity_remaining_ah: float | None = None   # abgeleitet: nominal * SOC/100
    energy_remaining_wh: float | None = None      # abgeleitet: capacity_remaining * U
    nominal_capacity_ah: float | None = None
    actual_capacity_ah: float | None = None
    cycle_count: int | None = None
    cycle_capacity_ah: float | None = None

    charging_switch: bool | None = None
    discharging_switch: bool | None = None
    balancer_switch: bool | None = None
    dedicated_charger_switch: bool | None = None
    balancing: bool | None = None
    charging: bool | None = None
    discharging: bool | None = None

    errors_bitmask: int | None = None
    errors_text: str | None = None
    operation_mode_bitmask: int | None = None
    operation_mode_text: str | None = None

    # Geräte-Info / Strings
    battery_type: str | None = None
    software_version: str | None = None
    manufacturer: str | None = None
    device_id: str | None = None
    protocol_version: int | None = None
    total_runtime_seconds: int | None = None
    total_runtime_formatted: str | None = None

    # Settings / Schutzparameter
    current_calibration_a: float | None = None
    sleep_wait_time_s: int | None = None
    low_capacity_alarm: int | None = None
    total_overvoltage_protection_v: float | None = None
    total_undervoltage_protection_v: float | None = None
    cell_overvoltage_protection_v: float | None = None
    cell_overvoltage_recovery_v: float | None = None
    cell_overvoltage_delay_s: int | None = None
    cell_undervoltage_protection_v: float | None = None
    cell_undervoltage_recovery_v: float | None = None
    cell_undervoltage_delay_s: int | None = None
    cell_pressure_difference_protection_v: float | None = None
    discharge_overcurrent_protection_a: float | None = None
    discharge_overcurrent_delay_s: int | None = None
    charge_overcurrent_protection_a: float | None = None
    charge_overcurrent_delay_s: int | None = None
    balance_starting_voltage_v: float | None = None
    balance_opening_pressure_difference_v: float | None = None
    power_tube_temp_protection_c: float | None = None
    power_tube_temp_recovery_c: float | None = None
    temp_sensor_protection_c: float | None = None
    temp_sensor_recovery_c: float | None = None
    temp_sensor_difference_protection_c: float | None = None
    charge_high_temp_protection_c: float | None = None
    discharge_high_temp_protection_c: float | None = None
    charge_low_temp_protection_c: float | None = None
    charge_low_temp_recovery_c: float | None = None
    discharge_low_temp_protection_c: float | None = None
    discharge_low_temp_recovery_c: float | None = None

    raw_length: int = 0


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _i16(data: bytes, off: int) -> int:
    return struct.unpack_from(">h", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def _i32(data: bytes, off: int) -> int:
    return struct.unpack_from(">i", data, off)[0]


def _cstr(data: bytes, off: int, width: int) -> str:
    """Liest ein nullterminiertes ASCII-Feld fester Breite und trimmt es."""
    raw = data[off:off + width]
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


# Warn-/Fehler-Bits aus Record 0x8B (uint16), Reihenfolge wie syssi/esphome-jk-bms.
_ERROR_BITS: tuple[str, ...] = (
    "Low capacity",                       # bit0
    "Power tube overtemperature",         # bit1
    "Charging overvoltage",               # bit2
    "Discharging undervoltage",           # bit3
    "Battery over temperature",           # bit4
    "Charging overcurrent",               # bit5
    "Discharging overcurrent",            # bit6
    "Cell pressure difference",           # bit7
    "Overtemperature in battery box",     # bit8
    "Battery low temperature",            # bit9
    "Cell overvoltage",                   # bit10
    "Cell undervoltage",                  # bit11
    "309_A protection",                   # bit12
    "309_B protection",                   # bit13
)

# Betriebsmodus-Bits aus Record 0x8C (uint16).
_OPERATION_MODE_BITS: tuple[str, ...] = (
    "Charging",      # bit0
    "Discharging",   # bit1
    "Balancing",     # bit2
    "Battery full",  # bit3
)

_BATTERY_TYPES: dict[int, str] = {
    0: "Lithium iron phosphate",
    1: "Ternary lithium",
    2: "Lithium titanate",
}

# Record-ID -> (Feldname, Skalierung, signed, Nachkommastellen).
# Alle Einträge sind 2-Byte-Records; round_digits == 0 ergibt einen int.
# Breiten/Bedeutungen verifiziert gegen syssi/esphome-jk-bms (on_status_data_).
_U16_RECORDS: dict[int, tuple[str, float, bool, int]] = {
    0x8E: ("total_overvoltage_protection_v", 0.01, False, 2),
    0x8F: ("total_undervoltage_protection_v", 0.01, False, 2),
    0x90: ("cell_overvoltage_protection_v", 0.001, False, 3),
    0x91: ("cell_overvoltage_recovery_v", 0.001, False, 3),
    0x92: ("cell_overvoltage_delay_s", 1.0, False, 0),
    0x93: ("cell_undervoltage_protection_v", 0.001, False, 3),
    0x94: ("cell_undervoltage_recovery_v", 0.001, False, 3),
    0x95: ("cell_undervoltage_delay_s", 1.0, False, 0),
    0x96: ("cell_pressure_difference_protection_v", 0.001, False, 3),
    0x97: ("discharge_overcurrent_protection_a", 1.0, False, 0),
    0x98: ("discharge_overcurrent_delay_s", 1.0, False, 0),
    0x99: ("charge_overcurrent_protection_a", 1.0, False, 0),
    0x9A: ("charge_overcurrent_delay_s", 1.0, False, 0),
    0x9B: ("balance_starting_voltage_v", 0.001, False, 3),
    0x9C: ("balance_opening_pressure_difference_v", 0.001, False, 3),
    0x9E: ("power_tube_temp_protection_c", 1.0, False, 0),
    0x9F: ("power_tube_temp_recovery_c", 1.0, False, 0),
    0xA0: ("temp_sensor_protection_c", 1.0, False, 0),
    0xA1: ("temp_sensor_recovery_c", 1.0, False, 0),
    0xA2: ("temp_sensor_difference_protection_c", 1.0, False, 0),
    0xA3: ("charge_high_temp_protection_c", 1.0, False, 0),
    0xA4: ("discharge_high_temp_protection_c", 1.0, False, 0),
    0xA5: ("charge_low_temp_protection_c", 1.0, True, 0),
    0xA6: ("charge_low_temp_recovery_c", 1.0, True, 0),
    0xA7: ("discharge_low_temp_protection_c", 1.0, True, 0),
    0xA8: ("discharge_low_temp_recovery_c", 1.0, True, 0),
    0xAD: ("current_calibration_a", 0.001, False, 3),
    0xB0: ("sleep_wait_time_s", 1.0, False, 0),
}

# Bekannte Records, die wir nur konsumieren (zur Sync-Erhaltung), aber nicht
# als Entität anbieten. Breite = Datenbytes nach der Record-ID.
_SKIP_RECORDS: dict[int, int] = {
    0xAE: 1,   # protection board address
    0xB2: 10,  # parameter password (nicht als Sensor exponiert)
    0xB5: 4,   # manufacturing date (unparsed)
    0xB8: 1,   # start current calibration flag
}


def _fmt_runtime(seconds: int) -> str:
    """Sekunden -> 'Xd Yh Zm'."""
    minutes, _ = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h {minutes}m"


def parse_status_payload(payload: bytes) -> BmsState:
    """Dekodiert einen 0x06 status frame.

    Layout-Quelle: syssi/esphome-jk-bms components/jk_bms/jk_bms.cpp::
    on_status_data_(). Felder werden über typisierte Records eingelesen.
    Wichtig: Jeder Record hat eine feste Breite; sie MUSS korrekt konsumiert
    werden, sonst desynchronisiert der record-by-record Strom (z. B. ist
    0xAD = current calibration mit 2 Byte, nicht der Balancer-Switch).

        0x79  cell info (variable length, 3 bytes per cell)
        0x80  power tube temperature (i16, °C)
        0x81  sensor 1 temperature (i16, °C)
        0x82  sensor 2 temperature (i16, °C)
        0x83  total voltage (u16 *0.01 V)
        0x84  current (u16, bit15 = Vorzeichen-Flag, *0.01 A)
        0x85  SOC (u8 %)
        0x86  num temp sensors (u8)
        0x87  cycle count (u16)
        0x89  total cycle capacity (u32 Ah)
        0x8A  cell count / battery strings (u16)
        0x8B  warning/error bitmask (u16)
        0x8C  operation mode bitmask (u16)
        0x8E..0xB0  Schutz-/Settings-Records (siehe _U16_RECORDS)
        0x9D  active balance switch (u8)  -> balancer_switch
        0xAA  total battery capacity setting (u32 Ah)  -> nominal_capacity_ah
        0xAB  charging switch (u8)
        0xAC  discharging switch (u8)
        0xAF  battery type (u8 enum)
        0xB1  low capacity alarm (u8 %)
        0xB3  dedicated charger switch (u8)
        0xB4  device id (8-byte string)
        0xB6  total runtime (u32 s)
        0xB7  software version (15-byte string)
        0xB9  actual battery capacity (u32 Ah)
        0xBA  manufacturer (24-byte string)
        0xC0  protocol version (u8)

    Restkapazität ist KEIN eigener Record, sondern wird abgeleitet
    (nominal_capacity_ah * SOC / 100). Unbekannte Records werden mit 2 Byte
    übersprungen (Fallback); bei vollständiger Breitentabelle tritt das nicht auf.
    """
    state = BmsState(raw_length=len(payload))
    i = 0
    n = len(payload)

    while i < n:
        record = payload[i]
        i += 1

        if record == 0x79:
            # Cell info: 1 Byte length, dann Tripel (idx, voltage_hi, voltage_lo) je Zelle
            if i >= n:
                break
            cell_data_len = payload[i]
            i += 1
            end = i + cell_data_len
            if end > n:
                break
            cells: list[float] = []
            j = i
            while j + 3 <= end:
                # idx = payload[j]
                mv = (payload[j + 1] << 8) | payload[j + 2]
                cells.append(round(mv / 1000.0, 3))
                j += 3
            if cells:
                state.cell_voltages = cells
                state.cell_count = len(cells)
                state.cell_min_voltage = min(cells)
                state.cell_max_voltage = max(cells)
                state.cell_min_index = cells.index(state.cell_min_voltage) + 1
                state.cell_max_index = cells.index(state.cell_max_voltage) + 1
                state.cell_avg_voltage = round(sum(cells) / len(cells), 3)
                state.cell_delta_voltage = round(state.cell_max_voltage - state.cell_min_voltage, 3)
            i = end

        elif record == 0x80:
            if i + 2 > n:
                break
            state.temperature_mos = float(_i16(payload, i))
            i += 2
        elif record == 0x81:
            if i + 2 > n:
                break
            state.temperature_sensor_1 = float(_i16(payload, i))
            i += 2
        elif record == 0x82:
            if i + 2 > n:
                break
            state.temperature_sensor_2 = float(_i16(payload, i))
            i += 2
        elif record == 0x83:
            if i + 2 > n:
                break
            state.total_voltage = round(_u16(payload, i) * 0.01, 2)
            i += 2
        elif record == 0x84:
            if i + 2 > n:
                break
            # Manche Firmwares: int16 *0.01; andere: bit15=sign-flag
            raw = _u16(payload, i)
            if raw & 0x8000:
                amps = (raw & 0x7FFF) * 0.01
            else:
                amps = -(raw & 0x7FFF) * 0.01
            state.current = round(amps, 2)
            i += 2
        elif record == 0x85:
            if i + 1 > n:
                break
            state.state_of_charge = float(payload[i])
            i += 1
        elif record == 0x86:
            if i + 1 > n:
                break
            state.temperature_sensor_count = payload[i]
            i += 1
        elif record == 0x87:
            if i + 2 > n:
                break
            state.cycle_count = _u16(payload, i)
            i += 2
        elif record == 0x89:
            if i + 4 > n:
                break
            state.cycle_capacity_ah = float(_u32(payload, i))
            i += 4
        elif record == 0x8A:
            if i + 2 > n:
                break
            state.cell_count = _u16(payload, i)
            i += 2
        elif record == 0x8B:
            if i + 2 > n:
                break
            state.errors_bitmask = _u16(payload, i)
            i += 2
        elif record == 0x8C:
            if i + 2 > n:
                break
            state.operation_mode_bitmask = _u16(payload, i)
            i += 2
        elif record == 0x9D:
            # Active balance switch (Balancer-Freigabe), 1 Byte.
            if i + 1 > n:
                break
            state.balancer_switch = bool(payload[i])
            i += 1
        elif record == 0xAA:
            if i + 4 > n:
                break
            state.nominal_capacity_ah = float(_u32(payload, i))
            i += 4
        elif record == 0xAB:
            if i + 1 > n:
                break
            state.charging_switch = bool(payload[i])
            i += 1
        elif record == 0xAC:
            if i + 1 > n:
                break
            state.discharging_switch = bool(payload[i])
            i += 1
        elif record == 0xAF:
            if i + 1 > n:
                break
            state.battery_type = _BATTERY_TYPES.get(payload[i], f"Unknown ({payload[i]})")
            i += 1
        elif record == 0xB1:
            if i + 1 > n:
                break
            state.low_capacity_alarm = payload[i]
            i += 1
        elif record == 0xB3:
            if i + 1 > n:
                break
            state.dedicated_charger_switch = bool(payload[i])
            i += 1
        elif record == 0xB4:
            if i + 8 > n:
                break
            state.device_id = _cstr(payload, i, 8)
            i += 8
        elif record == 0xB6:
            if i + 4 > n:
                break
            secs = _u32(payload, i)
            state.total_runtime_seconds = secs
            state.total_runtime_formatted = _fmt_runtime(secs)
            i += 4
        elif record == 0xB7:
            if i + 15 > n:
                break
            state.software_version = _cstr(payload, i, 15)
            i += 15
        elif record == 0xB9:
            if i + 4 > n:
                break
            state.actual_capacity_ah = float(_u32(payload, i))
            i += 4
        elif record == 0xBA:
            if i + 24 > n:
                break
            # Manche Firmwares stellen "Input Userdata" voran; nur ASCII behalten.
            state.manufacturer = _cstr(payload, i, 24)
            i += 24
        elif record == 0xC0:
            if i + 1 > n:
                break
            state.protocol_version = payload[i]
            i += 1
        elif record in _U16_RECORDS:
            if i + 2 > n:
                break
            attr, scale, signed, digits = _U16_RECORDS[record]
            raw_val = _i16(payload, i) if signed else _u16(payload, i)
            value: float | int = raw_val * scale
            value = int(round(value)) if digits == 0 else round(value, digits)
            setattr(state, attr, value)
            i += 2
        elif record in _SKIP_RECORDS:
            i += _SKIP_RECORDS[record]
        else:
            # Unbekannter Record – plausibler Skip (2 Byte). Bei vollständiger
            # Breitentabelle oben sollte dieser Zweig nicht erreicht werden.
            i += 2

    # --- Abgeleitete Werte ---
    if state.total_voltage is not None and state.current is not None:
        state.power = round(state.total_voltage * state.current, 2)

    if state.power is not None:
        state.charging_power = round(state.power, 2) if state.power > 0 else 0.0
        state.discharging_power = round(-state.power, 2) if state.power < 0 else 0.0

    # Lade-/Entlade-Status aus Stromrichtung (Hysterese 0.05 A).
    if state.current is not None:
        state.charging = state.current > 0.05
        state.discharging = state.current < -0.05

    # Restkapazität: kein eigener Record, abgeleitet aus Nennkapazität und SOC.
    if state.nominal_capacity_ah is not None and state.state_of_charge is not None:
        state.capacity_remaining_ah = round(
            state.nominal_capacity_ah * state.state_of_charge / 100.0, 3
        )
        if state.total_voltage is not None:
            state.energy_remaining_wh = round(
                state.capacity_remaining_ah * state.total_voltage, 1
            )

    # Fehler- und Betriebsmodus-Klartext aus den Bitmasken.
    if state.errors_bitmask is not None:
        active = [
            name
            for bit, name in enumerate(_ERROR_BITS)
            if state.errors_bitmask & (1 << bit)
        ]
        state.errors_text = ", ".join(active) if active else "OK"

    if state.operation_mode_bitmask is not None:
        modes = [
            name
            for bit, name in enumerate(_OPERATION_MODE_BITS)
            if state.operation_mode_bitmask & (1 << bit)
        ]
        state.operation_mode_text = ", ".join(modes) if modes else "Idle"
        # Aktives Balancing (Bit 2) ergänzend zum Freigabe-Schalter (0x9D).
        state.balancing = bool(state.operation_mode_bitmask & (1 << 2))

    return state


# --------------------------------------------------------------------------- #
# Hilfsfunktionen für Schalter/Numbers
# --------------------------------------------------------------------------- #
def build_switch_frame(name: str, on: bool) -> bytes:
    """Baut Schaltbefehl für `charging` / `discharging` / `balancer`."""
    from .const import (
        REG_BALANCER_SWITCH,
        REG_CHARGING_SWITCH,
        REG_DISCHARGING_SWITCH,
    )

    addrs = {
        "charging": REG_CHARGING_SWITCH,
        "discharging": REG_DISCHARGING_SWITCH,
        "balancer": REG_BALANCER_SWITCH,
    }
    if name not in addrs:
        raise ValueError(f"Unknown switch: {name}")
    return build_set_register_frame(addrs[name], 1 if on else 0, width=1)
