# ADR-003: Synchronous Sequential Orchestration (No Message Queue)

**Date:** 2025  
**Status:** Accepted

## Context

The orchestrator must invoke multiple services in a defined sequence and return
a combined result to the caller. Two architectural approaches were considered:
synchronous sequential calls vs. an async message queue (e.g. Celery, RabbitMQ).

## Decision

The orchestrator executes steps sequentially using Python `asyncio` (async/await).
Each step must complete before the next begins. No external message broker is introduced.

## Consequences

**Positive:**
- Simple mental model: the caller gets a result when all steps complete.
- No additional infrastructure (broker, worker processes, result backend).
- Failure isolation is straightforward: a failed step halts execution immediately,
  preventing partial state in downstream systems.
- Latency is predictable and directly observable in a single HTTP response.

**Negative:**
- Total latency = sum of all step latencies. If steps were independent, parallelism
  would help, but the current use cases require ordered execution.
- Long-running Modbus operations block the response. Mitigated by per-service
  `timeout` config.

## Future

If steps become truly independent, the orchestrator can be extended to run them
with `asyncio.gather`. If durability across restarts is required, a Saga pattern
with an external broker is the natural next step (documented as `Future` in README).
