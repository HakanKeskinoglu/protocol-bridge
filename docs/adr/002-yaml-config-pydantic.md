# ADR-002: YAML Configuration with Pydantic Validation

**Date:** 2025  
**Status:** Accepted

## Context

The bridge needs to know about each downstream service: host, port, protocol,
timeout, retry policy, and (for Modbus) register mappings with scale, offset, and unit.

This configuration must be readable by non-developers (ops teams, field engineers)
and must fail loudly if it is incorrect.

## Decision

Store all service configuration in a single `config/services.yaml` file.
Load and validate it at startup using Pydantic v2 models.

If the config is invalid (wrong type, missing required field, port out of range),
the application raises a `ValidationError` immediately — it does not start.

## Consequences

**Positive:**
- Fail-fast: misconfiguration is caught before any service call is attempted.
- YAML is human-readable and familiar to ops teams.
- Pydantic provides free type coercion (YAML int keys → Python int) and
  clear error messages with field paths.
- The same models are reused across config loading, registry, and adapters —
  no parallel data structures.

**Negative:**
- Config changes require a restart (no hot-reload).
- YAML indentation errors are silent until parse time.

## Alternatives Considered

- **Environment variables:** rejected because Modbus register mappings are
  too structured for flat env vars.
- **Database-backed config:** rejected as over-engineering for this scope;
  noted as a future extension point.
- **JSON config:** YAML chosen for readability and comment support.
