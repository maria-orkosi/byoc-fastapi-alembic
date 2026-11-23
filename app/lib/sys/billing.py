"""Billing plan resolution.

resolveUserPlan(user) answers { plan: str } — the plan slug of the
currently signed-in user (or 'free' when there is no user / no active plan).
"""


def resolveUserPlan(user=None):
    """Return the active plan for *user*.

    In production this reads the billing database.  The default
    implementation answers 'free' for unknown or unauthenticated users.

    Parameters
    ----------
    user : any
        A user object or ``None`` (unauthenticated).

    Returns
    -------
    dict
        ``{ "plan": "<slug>" }``
    """
    # For now, always return free
    return {"plan": "free"}


def getPlans():
    """Return the plans defined in the billing system.

    Returns
    -------
    list[dict]
        Each dict has at least ``{ "plan": "<slug>", "name": "<title>" }``.
    """
    return [
        {"plan": "free", "name": "Free"},
        {"plan": "pro", "name": "Pro"},
        {"plan": "enterprise", "name": "Enterprise"},
    ]
