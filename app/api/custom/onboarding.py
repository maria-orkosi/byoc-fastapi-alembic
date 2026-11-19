"""Onboarding flow API: steps a new user completes to reach the first useful result."""
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, String, Boolean, Text
from sqlalchemy.orm import declarative_base, Session
from sqlalchemy import create_engine

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

Base = declarative_base()

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
# Auth dependency — derive account id from request, return 401 when absent
# ---------------------------------------------------------------------------

def get_account_id(x_account_id: str = Header(..., alias="X-Account-ID")) -> str:
    """Require an X-Account-ID header. Returns 401 when the header is missing.

    In production this would be replaced by a dependency that extracts the
    account from the authenticated session / user object.
    """
    if not x_account_id or not x_account_id.strip():
        raise HTTPException(status_code=401, detail="Authentication required")
    return x_account_id.strip()


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


