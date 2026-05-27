# ha-jk-bms

Home Assistant Custom Integration for **Jikong (JK) Battery Management Systems** over a direct **USB-TTL** connection to the Raspberry Pi (no ESP needed).

> Inspired by and protocol-compatible with [`syssi/esphome-jk-bms`](https://github.com/syssi/esphome-jk-bms). This is a clean-room Python port targeting Home Assistant directly.

## Features

- **Direct serial** — connect the BMS GPS/UART-TTL port to the Pi via any cheap CP2102/CH340 USB-TTL adapter. No ESP, no MQTT, no extra service.
- **Read** — total voltage, current, power, SOC, per-cell voltages (up to 24), cell delta/min/max, MOSFET + sensor temperatures, cycle count, capacity.
- **Control** — toggle charging / discharging / balancer; set balance trigger voltage.
- **Config Flow + YAML** — set up via UI (with port auto-discovery) or via `configuration.yaml`.
- **Protocol agnostic** — both old JK (JK02 / GPS-style) and new JK-PB (Modbus-style) share enough framing that one parser handles both reading the status frame.

## Hardware wiring

```
JK-BMS GPS / UART-TTL port      USB-TTL adapter        Raspberry Pi
┌──────────────────────────┐   ┌────────────────┐
│  GND  RX  TX  VBAT       │   │  GND TX RX VCC │  ──USB──►  /dev/ttyUSB0
│   │    │   │   x         │   │   │  │  │  3V3 │
│   └────┼───┼───────────────│  GND │  │   x    │
│        └───┼───────────────│      RX │        │
│            └───────────────│         TX       │
└──────────────────────────┘   └────────────────┘
```

- **Do not connect VBAT** — it's full battery voltage and will fry the adapter.
- Use a 3.3 V capable USB-TTL adapter (CP2102, CH340 with 3V3 jumper, FT232 set to 3V3).
- For JK-PB with RS485: use an RS485-USB adapter and connect A/B.

## Installation

### Via HACS

1. HACS → ⋮ → Custom repositories → add `https://github.com/Gruni22/ha-jk-bms`, category *Integration*.
2. Install **JK BMS**, restart HA.
3. Settings → Devices & Services → **Add Integration** → *JK BMS*.

### Manual

Copy `custom_components/jk_bms/` into your `/config/custom_components/` directory and restart Home Assistant.

## Configuration

### UI

Settings → Devices & Services → **Add Integration** → *JK BMS*. The integration scans `/dev/serial/by-id` and any `/dev/ttyUSB*` / `/dev/ttyAMA*` ports. Pick yours, choose baudrate (default 115200), confirm.

### YAML

```yaml
jk_bms:
  - serial_port: /dev/serial/by-id/usb-1a86_USB_Single_Serial_xxxxxxx-if00-port0
    baudrate: 115200
    scan_interval: 10
    protocol: auto       # auto | jk02 | jkpb
```

YAML entries are imported on startup and become regular config entries you can later manage in the UI.

## Provided entities

**Sensors:** total voltage, current, power, SOC, cell 1..N voltage, cell avg/min/max/delta, cell min/max index, temp sensor 1/2, MOSFET temp, cycle count, total cycle capacity, cell count.

**Binary sensors:** charging, discharging, error.

**Switches:** charging enabled, discharging enabled, balancer enabled.

**Numbers:** balance trigger voltage.

> Switches write to BMS holding registers `0xAB`/`0xAC`/`0xAD` after authenticating. The BMS does not always echo new values immediately — give it one poll cycle to confirm.

## jk-bms-card (Lovelace) compatibility

This integration is built to work out-of-the-box with the
[**jk-bms-card**](https://github.com/Pho3niX90/jk-bms-card) — **without any manual
entity mapping**.

The card resolves entities as `<domain>.<prefix>_<key>` (default `prefix: jk_bms`).
To match this regardless of your Home Assistant language, the integration pins a
**fixed, English `entity_id`** for every entity (the *display* names stay
translated). With a device named *JK BMS* you get e.g.:

| Card key | entity_id |
|---|---|
| `total_voltage` | `sensor.jk_bms_total_voltage` |
| `delta_cell_voltage` | `sensor.jk_bms_delta_cell_voltage` |
| `average_cell_voltage` | `sensor.jk_bms_average_cell_voltage` |
| `power_tube_temperature` | `sensor.jk_bms_power_tube_temperature` |
| `min/max_voltage_cell` | `sensor.jk_bms_min/max_voltage_cell` |
| `cell_voltage_1…N` | `sensor.jk_bms_cell_voltage_1…N` |
| `charging` / `discharging` / `balancer` | `switch.jk_bms_…` |
| `balancing` | `binary_sensor.jk_bms_balancing` |

So a minimal card config is simply:

```yaml
type: custom:jk-bms-card
prefix: jk_bms
cellCount: 4        # match your pack
```

> **Existing installation:** entity_ids are only assigned when an entity is *first*
> created. If your BMS was already set up before this version, its entities keep
> their old IDs. To switch to the English/card-compatible IDs, **remove and
> re-add the integration** (Settings → Devices & Services → JK BMS → delete, then
> *Add Integration* again). Long-term statistics for the old IDs are lost.

**Not available on this protocol** (the card hides or zeroes them automatically):
`balancing_current`, `hardware_version`, and per-cell `cell_resistance_*` are only
reported by the newer JK02_32S/BLE protocol, not the serial JK02/JK-PB frames this
integration reads. `heater` requires heater hardware (`hasHeater: 1` in the card).

## Compatibility

| BMS family       | Protocol      | Status   |
|------------------|---------------|----------|
| JK-Bx, JK-Cx     | JK02 (GPS)    | tested   |
| JK-PB series     | JK-Modbus     | tested   |
| Heltec balancer  | —             | not yet  |

Tested with firmware ≥ 6.0 (the same minimum syssi documents).

## Troubleshooting

Enable debug logging:

```yaml
logger:
  default: info
  logs:
    custom_components.jk_bms: debug
```

Common issues:

- **`cannot_connect` in setup** — wrong RX/TX wiring (90% of the time). Swap them.
- **CRC errors in log** — bad cable or wrong baudrate. The JK uses 115200 8N1.
- **No data after first poll** — BMS may need a few seconds after power-up.

## Credits

- Frame format, register map and field semantics: [syssi/esphome-jk-bms](https://github.com/syssi/esphome-jk-bms) (Apache-2.0).
- Modbus-style protocol docs: JK BMS RS485 Modbus V1.1 (vendor PDF, mirrored in the syssi repo).

## License

Apache-2.0 — same as the upstream ESPHome project this is based on.
