"""Background tasks for order processing."""
from celery import shared_task  # noqa: F401


@shared_task
def send_order_confirmation(order_id: int):
    """Send an order confirmation email asynchronously."""
    pass


@shared_task
def cleanup_expired_orders():
    """Periodic task to clean up expired orders."""
    pass


# Celery beat schedule
CELERY_BEAT_SCHEDULE = {
    "cleanup-expired-orders": {
        "task": "app.tasks.order_tasks.cleanup_expired_orders",
        "schedule": 3600.0,  # every hour
    },
}
