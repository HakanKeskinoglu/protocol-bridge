import struct
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from bridge.adapters.modbus_adapter import ModbusAdapter
from bridge.adapters.base import AdapterError
from bridge.config import ServiceConfig, Protocol, RegisterConfig, RegisterType
from bridge.registry import ServiceEntry


def make_entry():
    config = ServiceConfig(
        host="service_c",
        port=5020,
        protocol=Protocol.MODBUS,
        timeout=3.0,
        retry=2,
        unit_id=1,
        registers={
            100: RegisterConfig(name="temperature", type=RegisterType.UINT16, scale=0.1, unit="celsius"),
            101: RegisterConfig(name="pressure", type=RegisterType.UINT16, scale=0.01, unit="bar"),
            102: RegisterConfig(name="fuel_level", type=RegisterType.FLOAT32, scale=1.0, unit="liters"),
        },
    )
    entry = ServiceEntry(name="plc-service", config=config)
    return entry


def make_modbus_result(registers: list):
    result = MagicMock()
    result.isError.return_value = False
    result.registers = registers
    return result


class TestModbusNormalization:
    def test_uint16_normalization(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)
        reg_config = entry.config.registers[100]  # temperature, scale=0.1

        result = adapter._normalize(100, [256], reg_config)

        assert result["temperature"] == 25.6
        assert result["unit"] == "celsius"
        assert result["register"] == 100

    def test_uint16_pressure_normalization(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)
        reg_config = entry.config.registers[101]  # pressure, scale=0.01

        result = adapter._normalize(101, [215], reg_config)

        assert result["pressure"] == 2.15
        assert result["unit"] == "bar"

    def test_float32_normalization(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)
        reg_config = entry.config.registers[102]  # fuel_level, float32

        # Encode 87.5 as IEEE 754 float32 into two uint16 registers
        packed = struct.pack(">f", 87.5)
        hi, lo = struct.unpack(">HH", packed)

        result = adapter._normalize(102, [hi, lo], reg_config)

        assert abs(result["fuel_level"] - 87.5) < 0.001
        assert result["unit"] == "liters"

    def test_unknown_register_returns_raw(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)

        result = adapter._normalize(999, [1234], None)

        assert result["register"] == 999
        assert result["raw_value"] == 1234


class TestModbusAdapterCall:
    @pytest.mark.asyncio
    async def test_read_register_success(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)

        with patch("bridge.adapters.modbus_adapter.AsyncModbusTcpClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.read_holding_registers.return_value = make_modbus_result([256])

            result = await adapter.call("readRegister", {"register": 100})

        assert result["temperature"] == 25.6

    @pytest.mark.asyncio
    async def test_read_register_missing_param_raises_error(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)

        with pytest.raises(AdapterError) as exc_info:
            await adapter.call("readRegister", {})

        assert exc_info.value.code == "MODBUS_MISSING_PARAM"

    @pytest.mark.asyncio
    async def test_unknown_action_raises_error(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)

        with pytest.raises(AdapterError) as exc_info:
            await adapter.call("unknownAction", {})

        assert exc_info.value.code == "MODBUS_UNKNOWN_ACTION"

    @pytest.mark.asyncio
    async def test_modbus_error_response_raises_adapter_error(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)

        error_result = MagicMock()
        error_result.isError.return_value = True

        with patch("bridge.adapters.modbus_adapter.AsyncModbusTcpClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.read_holding_registers.return_value = error_result

            with pytest.raises(AdapterError) as exc_info:
                await adapter.call("readRegister", {"register": 100})

        assert exc_info.value.code == "MODBUS_READ_ERROR"

    @pytest.mark.asyncio
    async def test_float32_register_reads_two_registers(self):
        entry = make_entry()
        adapter = ModbusAdapter(entry)

        packed = struct.pack(">f", 87.5)
        hi, lo = struct.unpack(">HH", packed)

        with patch("bridge.adapters.modbus_adapter.AsyncModbusTcpClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client
            mock_client.read_holding_registers.return_value = make_modbus_result([hi, lo])

            result = await adapter.call("readRegister", {"register": 102})

        # count=2 because register 102 is float32
        call_kwargs = mock_client.read_holding_registers.call_args[1]
        assert call_kwargs["count"] == 2
        assert abs(result["fuel_level"] - 87.5) < 0.001
