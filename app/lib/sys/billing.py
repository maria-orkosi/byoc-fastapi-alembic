"""Billing plan resolution.

resolveUserPlan(user) answers { plan: str } — the plan slug of the
currently signed-in user (or 'free' when there is no user / no active plan).
"""

# User ID → plan mapping for demonstration purposes.
# In production this reads from the billing database.
_USER_PLANS = {}


def resolveUserPlan(user=None):
    """Return the active plan for *user*.

    In production this reads the billing database.  The default
    implementation answers 'free' for unknown or unauthenticated users.

    Parameters
    ----------
    user : any
        A user object, user id string, or ``None`` (unauthenticated).

    Returns
    -------
    dict
        ``{ "plan": "<slug>" }``
    """
    if user is None:
        return {"plan": "free"}

    # Accept either a user dict with an 'id' or a plain string/int id
    try:
        uid = user.get("id") if isinstance(user, dict) else str(user)
    except Exception:
        uid = str(user)

    plan = _USER_PLANS.get(uid, "free")
    return {"plan": plan}


def getPlans():
    """Return the plans defined in the billing system.

    Returns
    -------
    list[dict]
        Each dict has at least ``{ "plan": "<slug>", "name": "<title>" }``.
    """
    return [
        {"plan": "free", "name": "Free"},
    ]
