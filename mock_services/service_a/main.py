from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Service A - REST/JSON Mock")


class OrderPayload(BaseModel):
    id: int


@app.get("/health")
def health():
    return {"status": "ok", "service": "service-a"}


@app.post("/getOrder")
def get_order(payload: OrderPayload):
    return {
        "order_id": payload.id,
        "item": "bolt",
        "quantity": 100,
        "status": "confirmed",
    }


@app.post("/createOrder")
def create_order(payload: dict):
    return {
        "order_id": 999,
        "item": payload.get("item", "unknown"),
        "status": "created",
    }
