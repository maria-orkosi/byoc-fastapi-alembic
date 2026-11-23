"""Stripe plan offer — public-facing plan metadata.

getPlanOffer() answers plans the owner configured in Orkosi (or the
product's own Stripe prices).  Falls back to getPlans() from billing.
"""

from app.lib.sys.billing import getPlans as _billing_getPlans


def getPlanOffer():
    """Return the public offer for this product's plans.

    Returns
    -------
    list[dict]
        Each dict has at least ``{ "id": str, "metadata": { "plan": "<slug>" },
        "name": "<title>", "price": … }``.
        Falls back to billing plans when no Stripe offer exists.
    """
    # Return plans from billing — no Stripe integration yet
    billing_plans = _billing_getPlans()
    return [
        {
            "id": f"price_{p['plan']}",
            "metadata": {"plan": p["plan"]},
            "name": p["name"],
            "price": None,
        }
        for p in billing_plans
    ]
