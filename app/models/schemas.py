"""Pydantic request/response schemas."""
from pydantic import BaseModel


class OrderCreate(BaseModel):
    total: float


class OrderResponse(BaseModel):
    id: int
    total: float
