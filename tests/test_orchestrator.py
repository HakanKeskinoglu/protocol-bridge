import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bridge.orchestrator import Orchestrator, OrchestratorError, Step
from bridge.adapters.base import AdapterError
from bridge.registry import Registry, ServiceEntry, ServiceNotFoundError, ServiceUnavailableError
from bridge.config import ServiceConfig, Protocol


def make_registry(services: dict) -> Registry:
    registry = Registry()
    for name, protocol in services.items():
        config = ServiceConfig(host="localhost", port=8000, protocol=protocol)
        entry = ServiceEntry(name=name, config=config)
        registry._services[name] = entry
    return registry


class TestOrchestratorExecute:
    @pytest.mark.asyncio
    async def test_single_step_success(self):
        registry = make_registry({"order-service": Protocol.REST})
        orchestrator = Orchestrator(registry)

        expected = {"order_id": 42}

        with patch("bridge.orchestrator.AdapterFactory.get") as mock_factory:
            mock_adapter = AsyncMock()
            mock_adapter.call.return_value = expected
            mock_factory.return_value = mock_adapter

            results = await orchestrator.execute([
                Step("order-service", "getOrder", {"id": 42})
            ])

        assert results == [expected]
        mock_adapter.call.assert_called_once_with("getOrder", {"id": 42})

    @pytest.mark.asyncio
    async def test_multiple_steps_all_succeed(self):
        registry = make_registry({
            "order-service": Protocol.REST,
            "erp-service": Protocol.SOAP,
        })
        orchestrator = Orchestrator(registry)

        results_map = {
            ("order-service", "getOrder"): {"order_id": 1},
            ("erp-service", "checkStock"): {"available": True},
        }

        async def fake_call(action, payload):
            service = [s for s in results_map if s[1] == action][0]
            return results_map[service]

        with patch("bridge.orchestrator.AdapterFactory.get") as mock_factory:
            mock_adapter = AsyncMock()
            mock_adapter.call.side_effect = fake_call
            mock_factory.return_value = mock_adapter

            results = await orchestrator.execute([
                Step("order-service", "getOrder", {"id": 1}),
                Step("erp-service", "checkStock", {"item": "bolt"}),
            ])

        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_stops_on_first_failure(self):
        registry = make_registry({
            "order-service": Protocol.REST,
            "erp-service": Protocol.SOAP,
            "plc-service": Protocol.MODBUS,
        })
        orchestrator = Orchestrator(registry)

        call_count = 0

        async def fail_on_second(action, payload):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise AdapterError("SOAP_TIMEOUT", "timed out", "erp-service")
            return {"ok": True}

        with patch("bridge.orchestrator.AdapterFactory.get") as mock_factory:
            mock_adapter = AsyncMock()
            mock_adapter.call.side_effect = fail_on_second
            mock_factory.return_value = mock_adapter

            with pytest.raises(OrchestratorError) as exc_info:
                await orchestrator.execute([
                    Step("order-service", "getOrder", {"id": 1}),
                    Step("erp-service", "checkStock", {"item": "bolt"}),
                    Step("plc-service", "readRegister", {"register": 100}),
                ])

        # Third step should never be called
        assert call_count == 2
        assert exc_info.value.step_index == 1
        assert exc_info.value.adapter_error.code == "SOAP_TIMEOUT"

    @pytest.mark.asyncio
    async def test_service_not_found_raises_orchestrator_error(self):
        registry = make_registry({})  # empty registry
        orchestrator = Orchestrator(registry)

        with pytest.raises(OrchestratorError) as exc_info:
            await orchestrator.execute([
                Step("nonexistent-service", "doSomething", {})
            ])

        assert exc_info.value.step_index == 0

    def test_orchestrator_error_to_dict(self):
        adapter_err = AdapterError("MODBUS_TIMEOUT", "timed out", "plc-service")
        err = OrchestratorError(step_index=2, service="plc-service", adapter_error=adapter_err)
        d = err.to_dict()

        assert d["error"] is True
        assert d["failed_step"] == 2
        assert d["code"] == "MODBUS_TIMEOUT"
        assert d["service"] == "plc-service"
