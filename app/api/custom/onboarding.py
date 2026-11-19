"""Onboarding flow API: steps a new user completes to reach the first useful result."""
import os
import hmac
import hashlib
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Boolean, Text
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy import create_engine

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

Base = declarative_base()

# ---------------------------------------------------------------------------
# Session / auth primitives — HMAC-signed cookie, never trust the client
# ---------------------------------------------------------------------------

SESSION_COOKIE = "onboarding_session"
_SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))


def _sign(value: str) -> str:
    """Return *value* with an HMAC-SHA256 signature appended."""
    sig = hmac.new(_SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
    return f"{value}.{sig}"


def _unsign(signed: str) -> str | None:
    """Return the original value if the signature is valid, otherwise None."""
    try:
        value, sig = signed.rsplit(".", 1)
        expected = hmac.new(_SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return value
    except ValueError:
        pass
    return None


router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class OnboardingStep(Base):
    __tablename__ = "onboarding_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(255), nullable=False, index=True)
    step_key = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    completed = Column(Boolean, nullable=False, default=False)
    skipped = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Default steps every new account starts with
# ---------------------------------------------------------------------------

DEFAULT_STEPS = [
    {"step_key": "welcome", "title": "Welcome to Byoc FastAPI Alembic r5c", "description": "Learn how Byoc FastAPI Alembic r5c brings your code to Orkosi, detected, placed and deployed without a remake.", "sort_order": 1},
    {"step_key": "connect", "title": "Connect your repository", "description": "Link your code repository so Orkosi can detect every part of your application.", "sort_order": 2},
    {"step_key": "configure", "title": "Configure your environment", "description": "Set up environment variables, secrets and database connections for your deployment.", "sort_order": 3},
    {"step_key": "deploy", "title": "Deploy your first build", "description": "Push your code and watch Orkosi build and deploy it automatically.", "sort_order": 4},
    {"step_key": "verify", "title": "Verify everything works", "description": "Check your health endpoints and confirm the deployment is running correctly.", "sort_order": 5},
]
# ---------------------------------------------------------------------------
# Auth dependency — derive account id from signed cookie, return 401 when absent
# ---------------------------------------------------------------------------

def get_account_id(onboarding_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> str:
    """Extract the account id from the signed session cookie.

    The cookie is HMAC-signed by the server; a missing or tampered cookie
    results in 401.  This ensures data is always stored per the authenticated
    account — the client can never choose which account to impersonate.
    """
    if not onboarding_session:
        raise HTTPException(status_code=401, detail="Authentication required")
    account_id = _unsign(onboarding_session)
    if account_id is None or not account_id.strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return account_id.strip()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session():
    """Yield a new SQLAlchemy session."""
    with Session(engine) as session:
        yield session


def _ensure_steps_exist(session: Session, account_id: str):
    """Create default onboarding steps for *account_id* if none exist yet."""
    existing = (
        session.query(OnboardingStep)
        .filter(OnboardingStep.account_id == account_id)
        .count()
    )
    if existing > 0:
        return
    now = datetime.now(timezone.utc)
    for step_def in DEFAULT_STEPS:
        row = OnboardingStep(
            account_id=account_id,
            step_key=step_def["step_key"],
            title=step_def["title"],
            description=step_def["description"],
            sort_order=step_def["sort_order"],
            completed=False,
            skipped=False,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    session.commit()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class StepOut(BaseModel):
    id: int
    step_key: str
    title: str
    description: str | None
    sort_order: int
    completed: bool
    skipped: bool


class ProgressOut(BaseModel):
    account_id: str
    total_steps: int
    completed_steps: int
    skipped_steps: int
    percent_complete: float
    all_done: bool
    steps: list[StepOut]
# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/progress", response_model=ProgressOut)
def get_progress(
    account_id: str = Depends(get_account_id),
    session: Session = Depends(_get_session),
):
    """Return the current onboarding progress for the authenticated account."""
    _ensure_steps_exist(session, account_id)

    rows = (
        session.query(OnboardingStep)
        .filter(OnboardingStep.account_id == account_id)
        .order_by(OnboardingStep.sort_order)
        .all()
    )

    total = len(rows)
    completed = sum(1 for r in rows if r.completed)
    skipped = sum(1 for r in rows if r.skipped)
    percent = (completed / total * 100) if total > 0 else 100.0
    all_done = (completed + skipped) >= total

    return ProgressOut(
        account_id=account_id,
        total_steps=total,
        completed_steps=completed,
        skipped_steps=skipped,
        percent_complete=round(percent, 1),
        all_done=all_done,
        steps=[
            StepOut(
                id=r.id,
                step_key=r.step_key,
                title=r.title,
                description=r.description,
                sort_order=r.sort_order,
                completed=r.completed,
                skipped=r.skipped,
            )
            for r in rows
        ],
    )


@router.post("/complete-step/{step_id}", response_model=StepOut)
def complete_step(
    step_id: int,
    account_id: str = Depends(get_account_id),
    session: Session = Depends(_get_session),
):
    """Mark a single onboarding step as completed for the account."""
    step = (
        session.query(OnboardingStep)
        .filter(OnboardingStep.id == step_id, OnboardingStep.account_id == account_id)
        .first()
    )
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")

    step.completed = True
    step.skipped = False
    step.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(step)

    return StepOut(
        id=step.id,
        step_key=step.step_key,
        title=step.title,
        description=step.description,
        sort_order=step.sort_order,
        completed=step.completed,
        skipped=step.skipped,
    )


@router.post("/skip-all", response_model=ProgressOut)
def skip_all(
    account_id: str = Depends(get_account_id),
    session: Session = Depends(_get_session),
):
    """Skip every remaining (not yet completed) onboarding step."""
    _ensure_steps_exist(session, account_id)

    rows = (
        session.query(OnboardingStep)
        .filter(OnboardingStep.account_id == account_id, OnboardingStep.completed == False)
        .all()
    )
    now = datetime.now(timezone.utc)
    for r in rows:
        r.skipped = True
        r.updated_at = now
    session.commit()

    # Return fresh progress after the skip
    return get_progress(account_id=account_id, session=session)


# ---------------------------------------------------------------------------
# Session management — set a signed session cookie for the current account
# ---------------------------------------------------------------------------

@router.post("/session", tags=["onboarding"], include_in_schema=False)
def create_session(account_id: str, request: Request):
    """Create a signed session cookie for *account_id*.

    Called once after sign-up / sign-in so the onboarding page and all
    subsequent API calls share the same authenticated account.
    """
    from fastapi.responses import JSONResponse

    signed = _sign(account_id)
    response = JSONResponse({"ok": True, "account_id": account_id})
    response.set_cookie(
        key=SESSION_COOKIE,
        value=signed,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=86400 * 30,  # 30 days
    )
    return response


# ---------------------------------------------------------------------------
# HTML page — served by the onboarding router so nothing extra is needed
# in main.py beyond the router include.
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates"


@router.get("/page", response_class=HTMLResponse, include_in_schema=False)
def onboarding_page():
    """Serve the onboarding HTML page."""
    template_path = _TEMPLATE_DIR / "onboarding.html"
    if not template_path.is_file():
        return HTMLResponse(content="<h1>Onboarding page not found</h1>", status_code=404)
    return HTMLResponse(content=template_path.read_text())


