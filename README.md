# protocol-bridge

An integration gateway that bridges services speaking different protocols —
REST/JSON, SOAP/XML, and Modbus TCP — behind a single unified HTTP interface.

Built as a practical demonstration of Software Architecture integrability tactics
(SE322 — Software Architecture, Atılım University).

---

## The Problem

Real-world systems rarely speak the same language. A REST API, a legacy ERP system
exposing SOAP, and an industrial PLC communicating over Modbus TCP cannot call each
other directly. Integrating them naively produces tight coupling, scattered translation
logic, and systems that break whenever any one component changes.

`protocol-bridge` sits between them.

---

## Architecture

```
Client
  │
  │ POST /execute
  ▼
┌────────────────────────────────────────┐
│             FastAPI Gateway             │
│                                        │
│  Discovery Registry ← services.yaml   │
│         │                              │
│    Orchestrator                        │
│         │                              │
│  ┌──────┼──────┐                       │
│  ▼      ▼      ▼                       │
│ REST  SOAP  Modbus  ← Adapter Layer   │
└──┬──────┬──────┬───────────────────────┘
   │      │      │
   ▼      ▼      ▼
Service  Service  Service
A (JSON) B (XML)  C (Modbus TCP)
```

---

## Integrability Tactics Applied

This project directly implements the five distance types from Bass et al.,
*Software Architecture in Practice* (4th ed., Part 7):

| Distance Type | Problem | Solution in this project |
|---|---|---|
| **Syntactic** | Service A speaks JSON, Service B speaks XML | `SoapAdapter` translates JSON ↔ XML transparently |
| **Data Semantic** | Modbus register 100 = raw integer 256; actual meaning = 25.6 °C | `ModbusAdapter` normalizes via `scale`, `offset`, `unit` from config |
| **Behavioral Semantic** | SOAP requires specific envelope structure; caller should not care | Envelope construction encapsulated inside `SoapAdapter` |
| **Temporal** | Slow legacy systems, unreliable Modbus links | Per-service `timeout` and `retry` in `services.yaml` |
| **Resource** | Concurrent requests to limited Modbus devices | Sequential orchestration; each step completes before the next begins |

Tactics used: **Encapsulate**, **Use an Intermediary**, **Tailor Interface**,
**Configure Behavior**, **Orchestrate**, **Restrict Communication Paths**.

---

## Quickstart

```bash
git clone https://github.com/HakanKeskinoglu/protocol-bridge
cd protocol-bridge
docker-compose up
```

All three mock services start first. The bridge starts only after they are healthy
(`depends_on` with `service_healthy`).

### Demo: one curl, three protocols

```bash
curl -s -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "steps": [
      { "service": "order-service",  "action": "getOrder",     "payload": { "id": 42 } },
      { "service": "erp-service",    "action": "checkStock",   "payload": { "item": "bolt" } },
      { "service": "plc-service",    "action": "readRegister", "payload": { "register": 100 } }
    ]
  }' | python3 -m json.tool
```

Expected response:

```json
{
  "results": [
    { "order_id": 42, "item": "bolt", "quantity": 100, "status": "confirmed" },
    { "available": "true", "quantity": "500", "warehouse": "Istanbul" },
    { "temperature": 25.6, "unit": "celsius", "register": 100 }
  ]
}
```

### Other endpoints

```bash
# Bridge and service health
curl http://localhost:8000/health

# List registered services
curl http://localhost:8000/services
```

---

## Project Structure

```
protocol-bridge/
├── bridge/
│   ├── main.py              # FastAPI app, lifespan, endpoints
│   ├── config.py            # Pydantic models, YAML loader (fail-fast)
│   ├── registry.py          # Discovery registry + health checks
│   ├── orchestrator.py      # Sequential execution + AdapterFactory
│   └── adapters/
│       ├── base.py          # BaseAdapter + unified AdapterError
│       ├── rest_adapter.py  # HTTP/JSON with retry
│       ├── soap_adapter.py  # JSON ↔ XML translation
│       └── modbus_adapter.py# Register R/W + semantic normalization
├── mock_services/
│   ├── service_a/           # REST/JSON (FastAPI)
│   ├── service_b/           # SOAP/XML (FastAPI)
│   └── service_c/           # Modbus TCP server (pymodbus)
├── config/
│   └── services.yaml        # All service config including register mappings
├── tests/
│   ├── adapters/
│   │   ├── test_rest_adapter.py
│   │   ├── test_soap_adapter.py
│   │   └── test_modbus_adapter.py
│   ├── test_orchestrator.py
│   └── test_registry.py
└── docs/
    └── adr/
        ├── 001-adapter-pattern.md
        ├── 002-yaml-config-pydantic.md
        └── 003-sync-orchestration.md
```

---

## Adding a New Protocol

1. Create `bridge/adapters/mqtt_adapter.py` extending `BaseAdapter`
2. Add `Protocol.MQTT = "mqtt"` to `bridge/config.py`
3. Register in `AdapterFactory._map`
4. Add the service to `config/services.yaml`

Nothing else changes. This is the Open/Closed Principle in practice.

---

## Running Tests

```bash
pip install -r requirements.txt pytest pytest-asyncio
pytest tests/ -v
```

33 tests, 0 external dependencies required (all network calls are mocked).

---

## Modbus Register Configuration

```yaml
plc-service:
  protocol: modbus
  registers:
    100:
      name: temperature
      type: uint16      # or int16, float32
      scale: 0.1
      offset: 0
      unit: celsius
    102:
      name: fuel_level
      type: float32     # reads registers 102 + 103, decodes IEEE 754
      scale: 1.0
      unit: liters
```

`float32` reads two consecutive registers and decodes them as a big-endian
IEEE 754 float — the standard encoding used by most industrial PLCs.

---

## Future

- **Saga / Compensation:** each step declares an optional `compensate` action;
  on failure the orchestrator calls `compensate` on previously successful steps.
- **Parallel steps:** `asyncio.gather` for independent steps declared with `parallel: true`.
- **MQTT adapter:** publish/subscribe integration for IoT sensor streams.
- **WebSocket stream:** real-time Modbus polling pushed to clients.

---

## References

- Bass, Clements, Kazman — *Software Architecture in Practice*, 4th edition, Part 7 (Integrability)
- [Modbus Application Protocol Specification V1.1b3](https://modbus.org/docs/Modbus_Application_Protocol_V1_1b3.pdf)
- [pymodbus documentation](https://pymodbus.readthedocs.io)
