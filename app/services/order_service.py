"""Order processing service."""
from app.models.order_models import Order, OrderItem  # noqa: F401 — dependency annotation


def calculate_order_total(order: Order) -> float:
    """Sum the totals of all items in an order."""
    return sum(item.price for item in order.items)


def validate_order(order_data: dict) -> bool:
    """Validate incoming order data."""
    return "total" in order_data and order_data["total"] > 0


def process_payment(order_id: int, amount: float) -> bool:
    """Process payment for an order."""
    return True
