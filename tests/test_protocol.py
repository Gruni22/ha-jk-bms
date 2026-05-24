"""Tests für protocol.py (laufen ohne HA und ohne Hardware)."""
from __future__ import annotations

import sys
from pathlib import Path

# protocol.py direkt laden, ohne dass __init__.py (HA-Abhängigkeiten) ausgeführt wird
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
_PKG_DIR = ROOT / "custom_components" / "jk_bms"

sys.modules["jk_bms"] = type(sys)("jk_bms")  # leeres Paket

spec_const = importlib.util.spec_from_file_location("jk_bms.const", _PKG_DIR / "const.py")
mod_const = importlib.util.module_from_spec(spec_const)
sys.modules["jk_bms.const"] = mod_const
spec_const.loader.exec_module(mod_const)

spec_proto = importlib.util.spec_from_file_location("jk_bms.protocol", _PKG_DIR / "protocol.py")
mod_proto = importlib.util.module_from_spec(spec_proto)
sys.modules["jk_bms.protocol"] = mod_proto
spec_proto.loader.exec_module(mod_proto)

FrameParser = mod_proto.FrameParser
build_authenticate_frame = mod_proto.build_authenticate_frame
build_read_all_frame = mod_proto.build_read_all_frame
build_set_register_frame = mod_proto.build_set_register_frame
build_switch_frame = mod_proto.build_switch_frame
jk_checksum = mod_proto.jk_checksum
parse_status_payload = mod_proto.parse_status_payload


def test_read_all_frame_layout() -> None:
    """Das read-all-Frame muss exakt 21 Byte sein und mit 4E 57 starten."""
    f = build_read_all_frame()
    assert len(f) == 21
    assert f[0] == 0x4E and f[1] == 0x57
    # data_len high byte
    assert f[2] == 0x00 and f[3] == 0x13
    # function = 0x06
    assert f[8] == 0x06
    # end marker
    assert f[16] == 0x68
    # CRC check
    expected = jk_checksum(f[:17])
    actual = (f[19] << 8) | f[20]
    assert expected == actual


def test_authenticate_frame_function() -> None:
    f = build_authenticate_frame()
    assert f[0:2] == bytes([0x4E, 0x57])
    assert f[8] == 0x05  # FUNCTION_PASSWORD


def test_switch_frame_balancer_on() -> None:
    f = build_switch_frame("balancer", True)
    assert f[0:2] == bytes([0x4E, 0x57])
    assert f[8] == 0x02            # FUNCTION_WRITE_REGISTER
    assert f[11] == 0xAD           # balancer register
    assert f[12] == 0x01           # value = on


def test_set_register_u32() -> None:
    f = build_set_register_frame(0xA8, 3400, width=4)  # 3.400 V Balance Trigger
    assert f[8] == 0x02
    assert f[11] == 0xA8
    # u32 BE = 00 00 0D 48
    assert f[12:16] == bytes([0x00, 0x00, 0x0D, 0x48])


def test_parser_round_trip() -> None:
    """Wir bauen ein Status-Frame mit bekanntem Inhalt und parsen es zurück."""
    # Payload: ein 0x83 (total voltage) record = 53.21 V → uint16 5321
    # plus ein 0x85 (SOC) = 78 %, plus ein 0x84 (current) = +12.34 A
    inner = bytearray()
    inner += bytes([0x83, 0x14, 0xC9])           # 5321
    inner += bytes([0x85, 0x4E])                  # 78 %
    inner += bytes([0x84, 0x84, 0xD2])            # current: bit15=1 → charging, value=0x04D2=1234 → 12.34 A
    inner += bytes([0x79, 0x06,                   # cell info, len=6 → 2 cells
                    0x01, 0x0F, 0xFA,             # cell 1 = 4090 mV
                    0x02, 0x0F, 0xFE])            # cell 2 = 4094 mV
    inner += bytes([0xAB, 0x01])                  # charging switch on
    inner += bytes([0xAC, 0x00])                  # discharging switch off
    inner += bytes([0xAD, 0x01])                  # balancer on

    # Frame zusammenbauen (Layout siehe protocol.FrameParser):
    # 11 Bytes Header: 4E 57 | data_len(2) | terminal(4) | func | source | type
    header = bytearray()
    header += bytes([0x4E, 0x57])                 # magic
    header += bytes([0x00, 0x00])                 # placeholder data_len
    header += bytes([0, 0, 0, 0])                 # terminal
    header += bytes([0x06])                       # function
    header += bytes([0x00])                       # source
    header += bytes([0x00])                       # type
    header += inner                               # payload
    header += bytes([0, 0, 0, 0])                 # record (wird vom Decoder als unbekannt geskippt)
    header += bytes([0x68])                       # end
    header += bytes([0x00, 0x00])                 # crc unused

    # data_len ist die Position des CRC-LOW-Bytes (also = Länge bis hierhin)
    data_len = len(header)
    header[2] = (data_len >> 8) & 0xFF
    header[3] = data_len & 0xFF

    crc = jk_checksum(bytes(header[:data_len]))
    header += bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    parser = FrameParser()
    parser.feed(bytes(header))
    frame = parser.pop()
    assert frame is not None, "Parser sollte ein Frame liefern"
    assert frame.function == 0x06

    state = parse_status_payload(frame.payload)
    assert state.total_voltage == 53.21
    assert state.state_of_charge == 78.0
    assert state.current == 12.34   # bit15 gesetzt → charging
    assert state.cell_count == 2
    assert state.cell_voltages == [4.090, 4.094]
    assert state.charging_switch is True
    assert state.discharging_switch is False
    assert state.balancer_switch is True
    # Power = U * I
    assert state.power is not None
    assert abs(state.power - 53.21 * 12.34) < 0.1


def test_parser_resync_on_garbage() -> None:
    """Müll vor dem Frame darf den Parser nicht killen."""
    garbage = bytes([0xFF, 0x00, 0x42, 0x4E, 0x12])  # Fake-Start, dann echtes 4E kommt
    valid = build_read_all_frame()                    # nur als Header-Beispiel
    # Wir senden den `valid` nicht — wir wollen nur sehen, dass Parser nicht abstürzt.
    parser = FrameParser()
    parser.feed(garbage)
    assert parser.pop() is None
