"""Tests for the onboarding API endpoints."""
import os
import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.orm import declarative_base, Session

# Override DATABASE_URL before importing app modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

# Recreate the engine and models for the test DB
_test_engine = create_engine("sqlite:///:memory:", echo=False)
_TestBase = declarative_base()


class OnboardingStep(_TestBase):
    __tablename__ = "onboarding_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(255), nullable=False)
    step_key = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    completed = Column(Boolean, nullable=False, default=False)
    skipped = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


_TestBase.metadata.create_all(bind=_test_engine)

# Patch the module-level engine and Base used by the onboarding module
import app.api.custom.onboarding as onboarding
onboarding.Base = _TestBase
onboarding.engine = _test_engine

from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers — build a signed cookie the same way the server does
# ---------------------------------------------------------------------------

def _signed_cookie(account_id: str) -> str:
    """Return the HMAC-signed cookie value for *account_id*."""
    return onboarding._sign(account_id)


def _cookies_for(account_id: str) -> dict:
    """Return a dict suitable for client.get(..., cookies=...) or client.post(...)."""
    return {"onboarding_session": _signed_cookie(account_id)}


@pytest.fixture(autouse=True)
def cleanup():
    """Truncate the onboarding_steps table before each test."""
    with Session(_test_engine) as session:
        session.query(OnboardingStep).delete()
        session.commit()
    yield


# ---------------------------------------------------------------------------
# GET /api/onboarding/progress
# ---------------------------------------------------------------------------

def test_get_progress_creates_default_steps_for_new_account():
    """First call for an account creates default steps and returns them."""
    resp = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-1"))
    assert resp.status_code == 200

    data = resp.json()
    assert data["account_id"] == "acc-1"
    assert data["total_steps"] == 5
    assert data["completed_steps"] == 0
    assert data["skipped_steps"] == 0
    assert data["percent_complete"] == 0.0
    assert data["all_done"] is False
    assert len(data["steps"]) == 5
    for step in data["steps"]:
        assert step["completed"] is False
        assert step["skipped"] is False


def test_get_progress_returns_401_without_cookie():
    """Missing session cookie returns 401."""
    resp = client.get("/api/onboarding/progress")
    assert resp.status_code == 401


def test_get_progress_returns_401_with_tampered_cookie():
    """A tampered (unsigned) cookie returns 401."""
    resp = client.get("/api/onboarding/progress", cookies={"onboarding_session": "fake.invalidsig"})
    assert resp.status_code == 401


def test_two_accounts_get_separate_progress():
    """Two different accounts get independent onboarding steps."""
    resp_a = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-a"))
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["account_id"] == "acc-a"

    step_a = data_a["steps"][0]
    resp_complete = client.post(
        f"/api/onboarding/complete-step/{step_a['id']}",
        cookies=_cookies_for("acc-a"),
    )
    assert resp_complete.status_code == 200

    resp_b = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-b"))
    assert resp_b.status_code == 200
    data_b = resp_b.json()
    assert data_b["account_id"] == "acc-b"
    assert data_b["completed_steps"] == 0

    resp_a2 = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-a"))
    data_a2 = resp_a2.json()
    assert data_a2["completed_steps"] == 1


# ---------------------------------------------------------------------------
# POST /api/onboarding/complete-step/{step_id}
# ---------------------------------------------------------------------------

def test_complete_step():
    """Completing a step marks it as completed."""
    resp = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-c"))
    steps = resp.json()["steps"]
    step_id = steps[0]["id"]

    resp2 = client.post(
        f"/api/onboarding/complete-step/{step_id}",
        cookies=_cookies_for("acc-c"),
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["id"] == step_id
    assert data["completed"] is True
    assert data["skipped"] is False


def test_complete_step_not_found_wrong_account():
    """Cannot complete a step that belongs to a different account."""
    resp = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-d"))
    step_id = resp.json()["steps"][0]["id"]

    resp2 = client.post(
        f"/api/onboarding/complete-step/{step_id}",
        cookies=_cookies_for("acc-e"),
    )
    assert resp2.status_code == 404


def test_complete_step_not_found_invalid_id():
    """Non-existent step id returns 404."""
    resp = client.post(
        "/api/onboarding/complete-step/99999",
        cookies=_cookies_for("acc-f"),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/onboarding/skip-all
# ---------------------------------------------------------------------------

def test_skip_all():
    """Skip-all marks all uncompleted steps as skipped."""
    client.get("/api/onboarding/progress", cookies=_cookies_for("acc-g"))
    resp = client.post("/api/onboarding/skip-all", cookies=_cookies_for("acc-g"))
    assert resp.status_code == 200
    data = resp.json()
    assert data["account_id"] == "acc-g"
    assert data["skipped_steps"] == 5
    assert data["completed_steps"] == 0
    assert data["all_done"] is True
    for step in data["steps"]:
        assert step["skipped"] is True
        assert step["completed"] is False


def test_skip_all_preserves_completed_steps():
    """Skip-all only affects steps that are not yet completed."""
    resp = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-h"))
    step_id = resp.json()["steps"][0]["id"]
    client.post(
        f"/api/onboarding/complete-step/{step_id}",
        cookies=_cookies_for("acc-h"),
    )

    resp2 = client.post("/api/onboarding/skip-all", cookies=_cookies_for("acc-h"))
    data = resp2.json()
    assert data["completed_steps"] == 1
    assert data["skipped_steps"] == 4
    assert data["all_done"] is True


# ---------------------------------------------------------------------------
# POST /api/onboarding/session
# ---------------------------------------------------------------------------

def test_create_session_sets_cookie():
    """POST /session creates the signed cookie."""
    resp = client.post("/api/onboarding/session?account_id=test-account")
    assert resp.status_code == 200
    assert resp.json()["account_id"] == "test-account"
    # The response should contain the Set-Cookie header
    cookies_from_resp = resp.cookies
    assert "onboarding_session" in cookies_from_resp

    # Use the cookie to fetch progress
    cookie_val = cookies_from_resp["onboarding_session"]
    resp2 = client.get(
        "/api/onboarding/progress",
        cookies={"onboarding_session": cookie_val},
    )
    assert resp2.status_code == 200
    assert resp2.json()["account_id"] == "test-account"


# ---------------------------------------------------------------------------
# Response shape validation
# ---------------------------------------------------------------------------

def test_progress_response_shape():
    """Verify the GET /progress response matches ProgressOut schema."""
    resp = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-i"))
    data = resp.json()

    assert "account_id" in data
    assert "total_steps" in data
    assert "completed_steps" in data
    assert "skipped_steps" in data
    assert "percent_complete" in data
    assert "all_done" in data
    assert "steps" in data
    assert isinstance(data["steps"], list)

    step = data["steps"][0]
    assert "id" in step
    assert "step_key" in step
    assert "title" in step
    assert "sort_order" in step
    assert "completed" in step
    assert "skipped" in step


def test_step_out_response_shape():
    """Verify the POST /complete-step response matches StepOut schema."""
    resp = client.get("/api/onboarding/progress", cookies=_cookies_for("acc-j"))
    step_id = resp.json()["steps"][0]["id"]

    resp2 = client.post(
        f"/api/onboarding/complete-step/{step_id}",
        cookies=_cookies_for("acc-j"),
    )
    data = resp2.json()

    assert "id" in data
    assert "step_key" in data
    assert "title" in data
    assert "sort_order" in data
    assert "completed" in data
    assert "skipped" in data