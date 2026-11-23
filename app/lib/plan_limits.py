"""Plan limits — the one place the limits live.

Defines the features this product offers and the limits per plan.
limitsFor(plan) answers { <key>: number | null } for a plan slug or name
in any letter case: no plan gives the free entry, a plan with no entry gives
null for every feature (null means no limit: a customer who paid is never
stopped by a limit nobody wrote), and it never throws.
"""

FEATURES = [
    {"key": "orders", "label": "Orders"},
    {"key": "migrations", "label": "Migrations"},
    {"key": "scanner", "label": "Module Scanner"},
]

PLAN_LIMITS = {
    "free": {
        "orders": 5,
        "migrations": 1,
        "scanner": 2,
    },
    "pro": {
        "orders": 100,
        "migrations": None,
        "scanner": None,
    },
    "enterprise": {
        "orders": None,
        "migrations": None,
        "scanner": None,
    },
}


def limitsFor(plan=None):
    """Return the limit map for *plan*.

    Parameters
    ----------
    plan : str or None
        A plan slug or name in any letter case.  None or empty string
        means the free plan.

    Returns
    -------
    dict
        ``{<feature_key>: int | None, …}`` — ``None`` means unlimited.
    """
    if not plan:
        return {f["key"]: PLAN_LIMITS.get("free", {}).get(f["key"], None) for f in FEATURES}

    try:
        key = str(plan).strip().lower()
    except Exception:
        return {f["key"]: None for f in FEATURES}

    if key in PLAN_LIMITS:
        return {f["key"]: PLAN_LIMITS[key].get(f["key"], None) for f in FEATURES}

    # Unknown plan — no limit on anything
    return {f["key"]: None for f in FEATURES}
