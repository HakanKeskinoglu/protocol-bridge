from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

import httpx

from bridge.config import BridgeConfig, Protocol, ServiceConfig

logger = logging.getLogger(__name__)


class ServiceEntry:
    def __init__(self, name: str, config: ServiceConfig):
        self.name = name
        self.config = config
        self.healthy: bool = True

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"


class Registry:
    def __init__(self):
        self._services: Dict[str, ServiceEntry] = {}

    def register_all(self, bridge_config: BridgeConfig) -> None:
        for name, svc_config in bridge_config.services.items():
            entry = ServiceEntry(name=name, config=svc_config)
            self._services[name] = entry
            logger.info(f"Registered: {name} ({svc_config.protocol.value}) at {entry.base_url}")

    def discover(self, name: str) -> ServiceEntry:
        entry = self._services.get(name)
        if not entry:
            raise ServiceNotFoundError(f"Service '{name}' not found in registry")
        if not entry.healthy:
            raise ServiceUnavailableError(f"Service '{name}' is currently unhealthy")
        return entry

    async def health_check_all(self) -> None:
        tasks = [self._check(name, entry) for name, entry in self._services.items()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check(self, name: str, entry: ServiceEntry) -> None:
        # Modbus health check is skipped (no HTTP endpoint)
        if entry.config.protocol == Protocol.MODBUS:
            return

        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{entry.base_url}/health")
                entry.healthy = resp.status_code == 200
        except Exception:
            entry.healthy = False

        status = "healthy" if entry.healthy else "UNHEALTHY"
        logger.info(f"Health check [{name}]: {status}")

    def status(self) -> Dict[str, str]:
        return {
            name: "healthy" if entry.healthy else "unhealthy"
            for name, entry in self._services.items()
        }


# Errors
class ServiceNotFoundError(Exception):
    pass


class ServiceUnavailableError(Exception):
    pass


# Singleton
_registry = Registry()


def get_registry() -> Registry:
    return _registry
