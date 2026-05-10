from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from bridge.config import load_config
from bridge.orchestrator import Orchestrator, OrchestratorError, Step
from bridge.registry import ServiceNotFoundError, ServiceUnavailableError, get_registry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ─── Startup ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading config...")
    config = load_config("config/services.yaml")      # Pydantic validates here

    registry = get_registry()
    registry.register_all(config)

    logger.info("Running initial health checks...")
    await registry.health_check_all()

    logger.info("protocol-bridge ready.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="protocol-bridge",
    description="Integration gateway bridging REST, SOAP, and Modbus TCP services.",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Request / Response schemas ───────────────────────────────────────────────

class StepRequest(BaseModel):
    service: str
    action: str
    payload: Dict[str, Any] = {}


class ExecuteRequest(BaseModel):
    steps: List[StepRequest]


class ExecuteResponse(BaseModel):
    results: List[Dict[str, Any]]


class ErrorResponse(BaseModel):
    error: bool = True
    code: str
    message: str
    service: str
    failed_step: int | None = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/execute", response_model=ExecuteResponse)
async def execute(request: ExecuteRequest):
    """
    Orchestrate a sequence of service calls across protocols.
    Steps are executed sequentially; execution stops on first failure.
    """
    steps = [
        Step(service=s.service, action=s.action, payload=s.payload)
        for s in request.steps
    ]

    registry = get_registry()
    orchestrator = Orchestrator(registry)

    try:
        results = await orchestrator.execute(steps)
        return ExecuteResponse(results=results)

    except (ServiceNotFoundError, ServiceUnavailableError) as e:
        raise HTTPException(status_code=503, detail=str(e))

    except OrchestratorError as e:
        raise HTTPException(status_code=502, detail=e.to_dict())


@app.get("/health")
async def health():
    """Bridge health + status of all registered services."""
    registry = get_registry()
    await registry.health_check_all()
    return {
        "status": "ok",
        "services": registry.status(),
    }


@app.get("/services")
async def list_services():
    """List all registered services and their protocols."""
    registry = get_registry()
    return {
        name: {
            "protocol": entry.config.protocol.value,
            "host": entry.config.host,
            "port": entry.config.port,
            "healthy": entry.healthy,
        }
        for name, entry in registry._services.items()
    }
