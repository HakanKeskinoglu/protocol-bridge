from __future__ import annotations

import logging
from typing import Any, Dict
from xml.etree import ElementTree as ET

import httpx
import xmltodict

from bridge.adapters.base import BaseAdapter, AdapterError
from bridge.registry import ServiceEntry

logger = logging.getLogger(__name__)


class SoapAdapter(BaseAdapter):
    """
    Adapter for SOAP/XML services.
    Resolves: Syntactic distance (JSON ↔ XML translation)
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
                    f"[SOAP:{self._entry.name}] attempt {attempt} failed: {e.message}"
                )

        raise last_error

    async def _do_call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        xml_body = self._to_soap_envelope(action, payload)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/soap",
                    content=xml_body,
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": action,
                    },
                )

                if response.status_code >= 400:
                    raise AdapterError(
                        code="SOAP_HTTP_ERROR",
                        message=f"HTTP {response.status_code}",
                        service=self._entry.name,
                    )

                logger.debug(f"[SOAP:{self._entry.name}] {action} → {response.status_code}")
                return self._from_soap_response(response.text)

        except httpx.TimeoutException:
            raise AdapterError(
                code="SOAP_TIMEOUT",
                message=f"SOAP call '{action}' timed out after {self._timeout}s",
                service=self._entry.name,
            )
        except httpx.RequestError as e:
            raise AdapterError(
                code="SOAP_CONNECTION_ERROR",
                message=str(e),
                service=self._entry.name,
            )

    def _to_soap_envelope(self, action: str, payload: Dict[str, Any]) -> bytes:
        """JSON dict → SOAP XML envelope"""
        body_fields = "\n".join(
            f"  <{k}>{v}</{k}>" for k, v in payload.items()
        )
        envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <{action}>
{body_fields}
    </{action}>
  </soap:Body>
</soap:Envelope>"""
        return envelope.encode("utf-8")

    def _from_soap_response(self, xml_text: str) -> Dict[str, Any]:
        """SOAP XML response → JSON dict"""
        try:
            parsed = xmltodict.parse(xml_text)
            # Unwrap Envelope > Body > *Response
            body = parsed.get("soap:Envelope", {}).get("soap:Body", {})
            # Return first child of body (the actual response element)
            for key, value in body.items():
                if isinstance(value, dict):
                    return value
            return body
        except Exception as e:
            raise AdapterError(
                code="SOAP_PARSE_ERROR",
                message=f"Failed to parse SOAP response: {e}",
                service=self._entry.name,
            )
