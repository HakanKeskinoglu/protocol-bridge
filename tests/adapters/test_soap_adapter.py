import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bridge.adapters.soap_adapter import SoapAdapter
from bridge.adapters.base import AdapterError
from bridge.config import ServiceConfig, Protocol
from bridge.registry import ServiceEntry


def make_entry(retry=1):
    config = ServiceConfig(host="service_b", port=8002, protocol=Protocol.SOAP, timeout=5.0, retry=retry)
    entry = ServiceEntry(name="erp-service", config=config)
    return entry


def make_response(status_code=200, content=""):
    mock = MagicMock()
    mock.status_code = status_code
    mock.text = content
    return mock


SOAP_RESPONSE_OK = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <checkStockResponse>
      <available>true</available>
      <quantity>500</quantity>
    </checkStockResponse>
  </soap:Body>
</soap:Envelope>"""

SOAP_RESPONSE_MALFORMED = "not xml at all"


class TestSoapAdapterTranslation:
    def test_to_soap_envelope_contains_action(self):
        entry = make_entry()
        adapter = SoapAdapter(entry)
        xml_bytes = adapter._to_soap_envelope("checkStock", {"item": "bolt"})
        xml_str = xml_bytes.decode("utf-8")

        assert "<checkStock>" in xml_str
        assert "<item>bolt</item>" in xml_str
        assert "soap:Envelope" in xml_str

    def test_from_soap_response_unwraps_body(self):
        entry = make_entry()
        adapter = SoapAdapter(entry)
        result = adapter._from_soap_response(SOAP_RESPONSE_OK)

        assert result.get("available") == "true"
        assert result.get("quantity") == "500"

    def test_from_soap_response_malformed_raises_error(self):
        entry = make_entry()
        adapter = SoapAdapter(entry)

        with pytest.raises(AdapterError) as exc_info:
            adapter._from_soap_response(SOAP_RESPONSE_MALFORMED)

        assert exc_info.value.code == "SOAP_PARSE_ERROR"


class TestSoapAdapterCall:
    @pytest.mark.asyncio
    async def test_successful_call_returns_parsed_json(self):
        entry = make_entry()
        adapter = SoapAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = make_response(200, SOAP_RESPONSE_OK)

            result = await adapter.call("checkStock", {"item": "bolt"})

        assert result["available"] == "true"

    @pytest.mark.asyncio
    async def test_sends_correct_headers(self):
        entry = make_entry()
        adapter = SoapAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = make_response(200, SOAP_RESPONSE_OK)

            await adapter.call("checkStock", {"item": "bolt"})

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["headers"]["SOAPAction"] == "checkStock"
        assert "text/xml" in call_kwargs["headers"]["Content-Type"]

    @pytest.mark.asyncio
    async def test_http_error_raises_adapter_error(self):
        entry = make_entry(retry=1)
        adapter = SoapAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = make_response(500)

            with pytest.raises(AdapterError) as exc_info:
                await adapter.call("checkStock", {"item": "bolt"})

        assert exc_info.value.code == "SOAP_HTTP_ERROR"
