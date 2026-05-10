import pytest
from bridge.registry import Registry, ServiceEntry, ServiceNotFoundError, ServiceUnavailableError
from bridge.config import ServiceConfig, Protocol, BridgeConfig


def make_config():
    return BridgeConfig(services={
        "order-service": ServiceConfig(host="localhost", port=8001, protocol=Protocol.REST),
        "plc-service": ServiceConfig(host="localhost", port=5020, protocol=Protocol.MODBUS),
    })


class TestRegistry:
    def test_register_all_adds_services(self):
        registry = Registry()
        registry.register_all(make_config())

        assert "order-service" in registry._services
        assert "plc-service" in registry._services

    def test_discover_returns_entry(self):
        registry = Registry()
        registry.register_all(make_config())

        entry = registry.discover("order-service")
        assert entry.name == "order-service"
        assert entry.config.protocol == Protocol.REST

    def test_discover_unknown_service_raises_error(self):
        registry = Registry()
        registry.register_all(make_config())

        with pytest.raises(ServiceNotFoundError):
            registry.discover("unknown-service")

    def test_discover_unhealthy_service_raises_error(self):
        registry = Registry()
        registry.register_all(make_config())
        registry._services["order-service"].healthy = False

        with pytest.raises(ServiceUnavailableError):
            registry.discover("order-service")

    def test_status_returns_all_services(self):
        registry = Registry()
        registry.register_all(make_config())

        status = registry.status()
        assert status["order-service"] == "healthy"
        assert status["plc-service"] == "healthy"

    def test_status_reflects_unhealthy(self):
        registry = Registry()
        registry.register_all(make_config())
        registry._services["order-service"].healthy = False

        status = registry.status()
        assert status["order-service"] == "unhealthy"
        assert status["plc-service"] == "healthy"

    def test_service_entry_base_url(self):
        config = ServiceConfig(host="service_a", port=8001, protocol=Protocol.REST)
        entry = ServiceEntry(name="svc", config=config)
        assert entry.base_url == "http://service_a:8001"
