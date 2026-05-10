import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from bridge.adapters.rest_adapter import RestAdapter
from bridge.adapters.base import AdapterError
from bridge.config import ServiceConfig, Protocol
from bridge.registry import ServiceEntry


def make_entry(host="localhost", port=8001, timeout=5.0, retry=2):
    config = ServiceConfig(host=host, port=port, protocol=Protocol.REST, timeout=timeout, retry=retry)
    entry = ServiceEntry(name="order-service", config=config)
    return entry


def make_response(status_code=200, json_data=None, text=""):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_data or {}
    mock.text = text
    return mock


class TestRestAdapterCall:
    @pytest.mark.asyncio
    async def test_successful_post_call(self):
        entry = make_entry()
        adapter = RestAdapter(entry)
        expected = {"order_id": 42, "item": "bolt"}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = make_response(200, expected)

            result = await adapter.call("getOrder", {"id": 42})

        assert result == expected
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_payload_uses_get(self):
        entry = make_entry()
        adapter = RestAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.get.return_value = make_response(200, {"status": "ok"})

            result = await adapter.call("ping", {})

        mock_client.get.assert_called_once()
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_http_error_raises_adapter_error(self):
        entry = make_entry(retry=1)
        adapter = RestAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = make_response(500, text="Internal Server Error")

            with pytest.raises(AdapterError) as exc_info:
                await adapter.call("getOrder", {"id": 1})

        assert exc_info.value.code == "REST_HTTP_ERROR"
        assert exc_info.value.service == "order-service"

    @pytest.mark.asyncio
    async def test_timeout_raises_adapter_error(self):
        entry = make_entry(retry=1)
        adapter = RestAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.TimeoutException("timed out")

            with pytest.raises(AdapterError) as exc_info:
                await adapter.call("getOrder", {"id": 1})

        assert exc_info.value.code == "REST_TIMEOUT"

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_last_error(self):
        entry = make_entry(retry=3)
        adapter = RestAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.side_effect = httpx.TimeoutException("timed out")

            with pytest.raises(AdapterError) as exc_info:
                await adapter.call("getOrder", {"id": 1})

        assert mock_client.post.call_count == 3
        assert exc_info.value.code == "REST_TIMEOUT"

    @pytest.mark.asyncio
    async def test_url_construction(self):
        entry = make_entry(host="service_a", port=8001)
        adapter = RestAdapter(entry)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client
            mock_client.post.return_value = make_response(200, {})

            await adapter.call("getOrder", {"id": 1})

        call_args = mock_client.post.call_args
        assert "http://service_a:8001/getOrder" in call_args[0][0]
