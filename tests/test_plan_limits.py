"""Tests for plan limits, billing, and the plan-limits API."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lib.plan_limits import FEATURES, PLAN_LIMITS, limitsFor
from app.lib.sys.billing import resolveUserPlan, getPlans
from app.lib.sys.stripe import getPlanOffer


# ---------------------------------------------------------------------------
# plan_limits.py tests
# ---------------------------------------------------------------------------

def test_limitsFor_no_plan_returns_free():
    """limitsFor(None) or limitsFor('') returns free limits."""
    free_limits = limitsFor(None)
    assert free_limits["orders"] == PLAN_LIMITS["free"]["orders"]
    assert free_limits["migrations"] == PLAN_LIMITS["free"]["migrations"]
    assert free_limits["scanner"] == PLAN_LIMITS["free"]["scanner"]

    empty_limits = limitsFor("")
    assert empty_limits == free_limits


def test_limitsFor_known_plan_returns_correct_limits():
    """limitsFor for a known plan returns the limits for that plan."""
    free_limits = limitsFor("free")
    assert free_limits["orders"] == PLAN_LIMITS["free"]["orders"]
    assert free_limits["migrations"] == PLAN_LIMITS["free"]["migrations"]
    assert free_limits["scanner"] == PLAN_LIMITS["free"]["scanner"]


def test_limitsFor_unknown_plan_returns_all_null():
    """limitsFor for an unknown plan returns None for every feature."""
    unknown_limits = limitsFor("superdeluxe")
    for f in FEATURES:
        assert unknown_limits[f["key"]] is None


def test_limitsFor_case_insensitive():
    """limitsFor is case-insensitive."""
    free_upper = limitsFor("FREE")
    free_mixed = limitsFor("Free")
    free_lower = limitsFor("free")
    assert free_upper == free_lower == free_mixed


def test_limitsFor_never_throws():
    """limitsFor never raises an exception."""
    limitsFor(None)
    limitsFor("")
    limitsFor("free")
    limitsFor("nonexistent")
    limitsFor(123)  # type: ignore


def test_limitsFor_strips_whitespace():
    """limitsFor handles leading/trailing whitespace."""
    free_limits = limitsFor("  free  ")
    assert free_limits["orders"] == PLAN_LIMITS["free"]["orders"]


# ---------------------------------------------------------------------------
# billing.py tests
# ---------------------------------------------------------------------------

def test_resolveUserPlan_returns_dict_with_plan():
    """resolveUserPlan returns a dict with a 'plan' key."""
    result = resolveUserPlan(None)
    assert isinstance(result, dict)
    assert "plan" in result
    assert result["plan"] == "free"


def test_getPlans_returns_list():
    """getPlans returns a list of plan dicts."""
    plans = getPlans()
    assert isinstance(plans, list)
    assert len(plans) > 0
    for p in plans:
        assert "plan" in p
        assert "name" in p


# ---------------------------------------------------------------------------
# stripe.py tests
# ---------------------------------------------------------------------------

def test_getPlanOffer_returns_list_with_metadata():
    """getPlanOffer returns a list of offer dicts with metadata.plan."""
    offers = getPlanOffer()
    assert isinstance(offers, list)
    assert len(offers) > 0
    for o in offers:
        assert "id" in o
        assert "metadata" in o
        assert "plan" in o["metadata"]
        assert "name" in o


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_plan_limits_integrates_with_billing():
    """The plan-limits API can build rows from billing plans."""
    billing_plans = getPlans()
    rows = []
    for bp in billing_plans:
        slug = bp["plan"]
        rows.append({
            "plan": slug,
            "name": bp["name"],
            "limits": limitsFor(slug),
        })

    assert len(rows) == len(billing_plans)
    for row in rows:
        for f in FEATURES:
            assert f["key"] in row["limits"]


def test_plan_limits_integrates_with_offer():
    """The plan-limits API can build rows from Stripe offers."""
    offers = getPlanOffer()
    rows = []
    for offer in offers:
        plan_slug = (offer.get("metadata", {}) or {}).get("plan", "")
        rows.append({
            "plan": plan_slug,
            "name": offer.get("name", plan_slug),
            "limits": limitsFor(plan_slug),
        })

    assert len(rows) == len(offers)
    for row in rows:
        for f in FEATURES:
            assert f["key"] in row["limits"]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [
        test_limitsFor_no_plan_returns_free,
        test_limitsFor_known_plan_returns_correct_limits,
        test_limitsFor_unknown_plan_returns_all_null,
        test_limitsFor_case_insensitive,
        test_limitsFor_never_throws,
        test_limitsFor_strips_whitespace,
        test_resolveUserPlan_returns_dict_with_plan,
        test_getPlans_returns_list,
        test_getPlanOffer_returns_list_with_metadata,
        test_plan_limits_integrates_with_billing,
        test_plan_limits_integrates_with_offer,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {test.__name__}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
