from __future__ import annotations

import logging
from typing import Any, Dict, List

from bridge.adapters.base import AdapterError, BaseAdapter
from bridge.adapters.modbus_adapter import ModbusAdapter
from bridge.adapters.rest_adapter import RestAdapter
from bridge.adapters.soap_adapter import SoapAdapter
from bridge.config import Protocol
from bridge.registry import Registry, ServiceEntry

logger = logging.getLogger(__name__)


# ─── Adapter Factory ──────────────────────────────────────────────────────────

class AdapterFactory:
    """
    Open/Closed: adding a new protocol = adding one entry here + one adapter class.
    Nothing else changes.
    """
    _map = {
        Protocol.REST: RestAdapter,
        Protocol.SOAP: SoapAdapter,
        Protocol.MODBUS: ModbusAdapter,
    }

    @classmethod
    def get(cls, entry: ServiceEntry) -> BaseAdapter:
        adapter_cls = cls._map.get(entry.config.protocol)
        if not adapter_cls:
            raise ValueError(f"No adapter for protocol: {entry.config.protocol}")
        return adapter_cls(entry)


# ─── Step Model ───────────────────────────────────────────────────────────────

class Step:
    def __init__(self, service: str, action: str, payload: Dict[str, Any]):
        self.service = service
        self.action = action
        self.payload = payload


# ─── Orchestrator ─────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Executes a list of steps sequentially.
    Each step: discover → adapt → call → collect result.
    Stops immediately on any failure.
    """

    def __init__(self, registry: Registry):
        self._registry = registry

    async def execute(self, steps: List[Step]) -> List[Dict[str, Any]]:
        results = []

        for i, step in enumerate(steps):
            logger.info(
                f"Orchestrator: step {i + 1}/{len(steps)} "
                f"→ {step.service}::{step.action}"
            )
            try:
                entry = self._registry.discover(step.service)
                adapter = AdapterFactory.get(entry)
                result = await adapter.call(step.action, step.payload)
                results.append(result)

            except AdapterError as e:
                logger.error(
                    f"Orchestrator: step {i + 1} failed [{e.code}] {e.message}"
                )
                raise OrchestratorError(
                    step_index=i,
                    service=step.service,
                    adapter_error=e,
                )

            except Exception as e:
                logger.error(f"Orchestrator: unexpected error at step {i + 1}: {e}")
                raise OrchestratorError(
                    step_index=i,
                    service=step.service,
                    adapter_error=AdapterError(
                        code="INTERNAL_ERROR",
                        message=str(e),
                        service=step.service,
                    ),
                )

        return results


class OrchestratorError(Exception):
    def __init__(self, step_index: int, service: str, adapter_error: AdapterError):
        super().__init__(adapter_error.message)
        self.step_index = step_index
        self.service = service
        self.adapter_error = adapter_error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": True,
            "failed_step": self.step_index,
            **self.adapter_error.to_dict(),
        }
