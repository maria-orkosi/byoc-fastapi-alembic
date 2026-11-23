"""API route definitions for orders."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.lib.sys.billing import resolveUserPlan
from app.lib.plan_limits import limitsFor, FEATURES

router = APIRouter(prefix="/api/v1")


@router.get("/orders")
def list_orders():
    """List all orders."""
    return []


def _check_order_limit(request: Request):
    """Check whether the current user can create another order.

    Returns None if OK, otherwise a 403 JSONResponse.
    """
    try:
        plan_info = resolveUserPlan(None)
    except Exception:
        # If plan resolution fails, fall back to free
        plan_info = {"plan": "free"}

    plan = plan_info.get("plan", "free")
    limits = limitsFor(plan)

    order_limit = limits.get("orders")
    if order_limit is not None:
        # Count orders owned by the current user
        try:
            user_id = getattr(request.state, "user_id", None)
            from app.main import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                if user_id is not None:
                    row = conn.execute(
                        text("select count(*) as cnt from orders where user_id = :uid"),
                        {"uid": user_id},
                    ).first()
                else:
                    # No user context — count all orders, same as before
                    row = conn.execute(text("select count(*) as cnt from orders")).first()
                current_count = int(row.cnt) if row else 0
        except Exception:
            # On DB error, assume the limit is reached rather than bypassing it
            current_count = order_limit

        if current_count >= order_limit:
            feature_label = next((f["label"] for f in FEATURES if f["key"] == "orders"), "Orders")
            return JSONResponse(
                status_code=403,
                content={
                    "code": "PLAN_LIMIT",
                    "message": f"You have reached the {feature_label} limit of your {plan} plan. Please upgrade to create more orders.",
                    "upgradeUrl": "/pricing",
                },
            )
    return None


@router.post("/orders")
def create_order(request: Request):
    """Create a new order."""
    limit_response = _check_order_limit(request)
    if limit_response is not None:
        return limit_response
    return {"created": True}


@router.get("/orders/{order_id}")
def get_order(order_id: int):
    """Get a single order."""
    return {"id": order_id}

