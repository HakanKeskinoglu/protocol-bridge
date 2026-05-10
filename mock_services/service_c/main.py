import asyncio
import struct
import logging

from pymodbus.datastore import ModbusSlaveContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import StartAsyncTcpServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_context() -> ModbusServerContext:
    packed = struct.pack(">f", 87.5)
    hi, lo = struct.unpack(">HH", packed)

    registers = [0] * 110
    registers[100] = 256    # temperature: 25.6°C
    registers[101] = 215    # pressure: 2.15 bar
    registers[102] = hi     # fuel_level high word
    registers[103] = lo     # fuel_level low word

    store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, registers))
    return ModbusServerContext(slaves=store, single=True)


async def main():
    context = build_context()
    logger.info("Starting Modbus TCP server on 0.0.0.0:5020")
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", 5020))


if __name__ == "__main__":
    asyncio.run(main())