"""API route definitions for orders."""
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/orders")
def list_orders():
    """List all orders."""
    return []


@router.post("/orders")
def create_order():
    """Create a new order."""
    return {"created": True}


@router.get("/orders/{order_id}")
def get_order(order_id: int):
    """Get a single order."""
    return {"id": order_id}
