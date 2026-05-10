from __future__ import annotations

import logging
from typing import Any, Dict

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from bridge.adapters.base import BaseAdapter, AdapterError
from bridge.registry import ServiceEntry

logger = logging.getLogger(__name__)


class RestAdapter(BaseAdapter):
    """
    Adapter for REST/JSON services.
    Resolves: Syntactic distance (caller speaks generic dict, service speaks HTTP/JSON)
    """

    def __init__(self, entry: ServiceEntry):
        self._entry = entry
        self._base_url = entry.base_url
        self._timeout = entry.config.timeout
        self._retry = entry.config.retry

    async def call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        attempt = 0
        last_error = None

        while attempt < self._retry:
            try:
                return await self._do_call(action, payload)
            except AdapterError as e:
                last_error = e
                attempt += 1
                logger.warning(
                    f"[REST:{self._entry.name}] attempt {attempt} failed: {e.message}"
                )

        raise last_error

    async def _do_call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convention: action maps to URL path.
        e.g. action="getOrder" + payload={"id": 42} → GET /getOrder?id=42
             action="createOrder" + payload={...}    → POST /createOrder
        """
        url = f"{self._base_url}/{action}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                if payload:
                    response = await client.post(url, json=payload)
                else:
                    response = await client.get(url)

                if response.status_code >= 400:
                    raise AdapterError(
                        code="REST_HTTP_ERROR",
                        message=f"HTTP {response.status_code}: {response.text}",
                        service=self._entry.name,
                    )

                logger.debug(f"[REST:{self._entry.name}] {action} → {response.status_code}")
                return response.json()

        except httpx.TimeoutException:
            raise AdapterError(
                code="REST_TIMEOUT",
                message=f"Request to '{action}' timed out after {self._timeout}s",
                service=self._entry.name,
            )
        except httpx.RequestError as e:
            raise AdapterError(
                code="REST_CONNECTION_ERROR",
                message=str(e),
                service=self._entry.name,
            )
