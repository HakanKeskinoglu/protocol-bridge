# ADR-001: Protocol Adapter Abstraction

**Date:** 2025  
**Status:** Accepted

## Context

The bridge must communicate with services that speak fundamentally different protocols:
REST/JSON, SOAP/XML, and Modbus TCP. Each protocol has distinct serialization formats,
transport mechanisms, and error semantics.

A naive approach would embed protocol-specific logic directly in the orchestrator,
causing a single class to handle HTTP, XML parsing, and raw TCP framing simultaneously.

## Decision

Introduce a `BaseAdapter` abstract class with a single method: `call(action, payload) → dict`.

Each protocol gets its own concrete adapter class. The orchestrator never imports
a concrete adapter directly — it receives one from `AdapterFactory` based on the
protocol declared in the service registry.

## Consequences

**Positive:**
- Open/Closed Principle: adding a new protocol (e.g. gRPC, MQTT) requires writing
  one new adapter class and one entry in `AdapterFactory._map`. Nothing else changes.
- Each adapter can be tested in complete isolation without running the orchestrator.
- Protocol-specific retry, timeout, and error-mapping logic stays inside the adapter.

**Negative:**
- Slight indirection: the orchestrator cannot see what protocol it is calling.
- All adapters must return a normalized `dict`; adapters are responsible for any
  data transformation this requires.

## Alternatives Considered

- **Strategy pattern via dependency injection:** rejected because service-to-protocol
  mapping is config-driven, not caller-driven.
- **Single generic HTTP adapter with format plugins:** rejected because Modbus TCP
  is not HTTP-based; the abstraction would have been leaky.
