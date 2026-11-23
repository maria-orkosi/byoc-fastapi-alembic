"""Public route: plan limits information.

GET /api/plan-limits — returns { features, plans: [{ plan, name, limits }] }
with one row per plan offered.
"""
from fastapi import APIRouter

from app.lib.plan_limits import FEATURES, limitsFor
from app.lib.sys.stripe import getPlanOffer
from app.lib.sys.billing import getPlans

router = APIRouter()


@router.get("/plan-limits")
def plan_limits():
    """Return the feature list and per-plan limits for the pricing table."""
    plans = []

    try:
        offers = getPlanOffer()
    except Exception:
        offers = []

    if offers:
        for offer in offers:
            plan_slug = (offer.get("metadata", {}) or {}).get("plan", "")
            plans.append({
                "plan": plan_slug,
                "name": offer.get("name", plan_slug),
                "limits": limitsFor(plan_slug),
            })
    else:
        try:
            billing_plans = getPlans()
        except Exception:
            billing_plans = []

        for bp in billing_plans:
            slug = bp.get("plan", "")
            plans.append({
                "plan": slug,
                "name": bp.get("name", slug),
                "limits": limitsFor(slug),
            })

    return {
        "features": FEATURES,
        "plans": plans,
    }
