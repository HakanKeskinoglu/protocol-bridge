from __future__ import annotations

from enum import Enum
from typing import Dict, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class Protocol(str, Enum):
    REST = "rest"
    SOAP = "soap"
    MODBUS = "modbus"


class RegisterType(str, Enum):
    UINT16 = "uint16"
    INT16 = "int16"
    FLOAT32 = "float32"


class RegisterConfig(BaseModel):
    name: str
    type: RegisterType = RegisterType.UINT16
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""


class ServiceConfig(BaseModel):
    host: str
    port: int = Field(gt=0, lt=65536)
    protocol: Protocol
    timeout: float = Field(default=5.0, gt=0)
    retry: int = Field(default=3, ge=1, le=10)

    # Modbus-only fields
    unit_id: Optional[int] = None
    registers: Optional[Dict[int, RegisterConfig]] = None

    @field_validator("registers", mode="before")
    @classmethod
    def parse_register_keys(cls, v):
        if v is None:
            return v
        result = {}
        for k, val in v.items():
            if isinstance(val, RegisterConfig):
                result[int(k)] = val
            else:
                result[int(k)] = RegisterConfig(**val)
        return result


class BridgeConfig(BaseModel):
    services: Dict[str, ServiceConfig]


def load_config(path: str = "config/services.yaml") -> BridgeConfig:
    with open(path, "r") as f:
        raw = yaml.safe_load(f)

    # Pydantic validates here — invalid config raises immediately
    config = BridgeConfig(**raw)
    return config
