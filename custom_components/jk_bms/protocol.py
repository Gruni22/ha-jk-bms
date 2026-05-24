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

    total_voltage: float | None = None      # V
    current: float | None = None            # A (positive = charge)
    power: float | None = None              # W
    state_of_charge: float | None = None    # %
    capacity_remaining_ah: float | None = None
    nominal_capacity_ah: float | None = None
    cycle_count: int | None = None
    cycle_capacity_ah: float | None = None

    charging_switch: bool | None = None
    discharging_switch: bool | None = None
    balancer_switch: bool | None = None
    balancing: bool | None = None

    errors_bitmask: int | None = None
    raw_length: int = 0


def _u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def _i16(data: bytes, off: int) -> int:
    return struct.unpack_from(">h", data, off)[0]


def _u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


def _i32(data: bytes, off: int) -> int:
    return struct.unpack_from(">i", data, off)[0]


def parse_status_payload(payload: bytes) -> BmsState:
    """Dekodiert einen 0x06 status frame.

    Layout-Quelle: syssi/esphome-jk-bms components/jk_bms/jk_bms.cpp::
    on_status_data_(). Felder werden über typisierte Records eingelesen:

        0x79  cell info (variable length, 3 bytes per cell)
        0x80  power tube temperature (°C, /10? – Skalierung in i16)
        0x81  sensor 1 temperature
        0x82  sensor 2 temperature
        0x83  total voltage (uint16 *0.01 V)
        0x84  current (int16 *0.01 A)  -- bei manchen Firmwares offset/sign anders
        0x85  SOC (uint8 %)
        0x86  num temp sensors
        0x87  cycle count uint16
        0x89  total cycle capacity uint32 (Ah)
        0x8A  cell count uint16
        0x8B  battery warning bitmask uint16
        0x8C  battery status bitmask uint16
        0xAB  charging switch
        0xAC  discharging switch
        0xAD  balancer switch

    Wir verarbeiten record-by-record. Unbekannte Records werden übersprungen,
    fehlende Felder bleiben None.
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
            state.temperature_mos = _i16(payload, i)
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
            state.total_voltage = _u16(payload, i) * 0.01
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
            # Anzahl Temperatursensoren – meist 1 Byte, ignorieren
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
        elif record == 0xAA:
            if i + 4 > n:
                break
            state.nominal_capacity_ah = float(_u32(payload, i))
            i += 4
        elif record in (0xAB, 0xAC, 0xAD):
            if i + 1 > n:
                break
            val = bool(payload[i])
            if record == 0xAB:
                state.charging_switch = val
            elif record == 0xAC:
                state.discharging_switch = val
            elif record == 0xAD:
                state.balancer_switch = val
            i += 1
        else:
            # Unbekannter Record – versuche, einen plausiblen Skip zu finden.
            # Heuristik: 2 Byte. Wenn das zu Frame-Ende führt, ok.
            i += 2

    # Power = U * I, wenn beides bekannt
    if state.total_voltage is not None and state.current is not None:
        state.power = round(state.total_voltage * state.current, 2)

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
