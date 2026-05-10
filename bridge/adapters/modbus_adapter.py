from __future__ import annotations

import logging
import struct
from typing import Any, Dict

import asyncio
from pymodbus.client import ModbusTcpClient

from bridge.adapters.base import BaseAdapter, AdapterError
from bridge.config import RegisterConfig, RegisterType
from bridge.registry import ServiceEntry

logger = logging.getLogger(__name__)


class ModbusAdapter(BaseAdapter):
    """
    Adapter for Modbus TCP devices.
    Resolves:
      - Syntactic distance  : raw Modbus frames ↔ JSON dict
      - Data Semantic distance: raw register value → named, scaled, unit-tagged value
      - Temporal distance   : configurable timeout per device
    """

    def __init__(self, entry: ServiceEntry):
        self._entry = entry
        self._host = entry.config.host
        self._port = entry.config.port
        self._timeout = entry.config.timeout
        self._retry = entry.config.retry
        self._unit_id = entry.config.unit_id or 1
        self._registers = entry.config.registers or {}

    async def call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        attempt = 0
        last_error = None

        while attempt < self._retry:
            try:
                return await self._dispatch(action, payload)
            except AdapterError as e:
                last_error = e
                attempt += 1
                logger.warning(
                    f"[Modbus:{self._entry.name}] attempt {attempt} failed: {e.message}"
                )

        raise last_error

    async def _dispatch(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if action == "readRegister":
            return await self._read_register(payload)
        elif action == "writeRegister":
            return await self._write_register(payload)
        else:
            raise AdapterError(
                code="MODBUS_UNKNOWN_ACTION",
                message=f"Unknown action '{action}'",
                service=self._entry.name,
            )

    async def _read_register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        address = payload.get("register")
        if address is None:
            raise AdapterError("MODBUS_MISSING_PARAM", "'register' field is required", self._entry.name)

        reg_config = self._registers.get(int(address))
        count = 2 if reg_config and reg_config.type == RegisterType.FLOAT32 else 1

        try:
            loop = asyncio.get_running_loop()
            raw = await loop.run_in_executor(None, self._sync_read, address, count)
            return self._normalize(address, raw, reg_config)
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError(
                code="MODBUS_CONNECTION_ERROR",
                message=str(e),
                service=self._entry.name,
            )
        

    async def _write_register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        address = payload.get("register")
        value = payload.get("value")
        if address is None or value is None:
            raise AdapterError("MODBUS_MISSING_PARAM", "'register' and 'value' are required", self._entry.name)

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._sync_write, address, int(value))
            return {"written": True, "register": address, "value": value}
        except AdapterError:
            raise
        except Exception as e:
            raise AdapterError("MODBUS_CONNECTION_ERROR", str(e), self._entry.name)

    def _sync_read(self, address: int, count: int) -> list:
        with ModbusTcpClient(host=self._host, port=self._port, timeout=self._timeout) as client:
            result = client.read_holding_registers(address=address, count=count, slave=self._unit_id)
            if result.isError():
                raise AdapterError("MODBUS_READ_ERROR", f"Error reading register {address}", self._entry.name)
            return result.registers

    def _sync_write(self, address: int, value: int) -> None:
        with ModbusTcpClient(host=self._host, port=self._port, timeout=self._timeout) as client:
            result = client.write_register(address=address, value=value, slave=self._unit_id)
            if result.isError():
                raise AdapterError("MODBUS_WRITE_ERROR", f"Error writing register {address}", self._entry.name)

    def _normalize(
        self,
        address: int,
        raw_registers: list,
        config: RegisterConfig | None,
    ) -> Dict[str, Any]:
        """
        Data Semantic Distance resolution:
        raw register value → named, scaled, unit-tagged response
        """
        if config is None:
            # No mapping defined — return raw value
            return {"register": address, "raw_value": raw_registers[0]}

        if config.type == RegisterType.FLOAT32:
            # Two registers combined into IEEE 754 float (big-endian)
            packed = struct.pack(">HH", raw_registers[0], raw_registers[1])
            raw_value = struct.unpack(">f", packed)[0]
        elif config.type == RegisterType.INT16:
            raw_value = raw_registers[0] if raw_registers[0] < 32768 else raw_registers[0] - 65536
        else:
            # UINT16 default
            raw_value = raw_registers[0]

        normalized = (raw_value * config.scale) + config.offset

        logger.debug(
            f"[Modbus:{self._entry.name}] register={address} "
            f"raw={raw_value} → {config.name}={normalized} {config.unit}"
        )

        return {
            config.name: round(normalized, 4),
            "unit": config.unit,
            "register": address,
        }
