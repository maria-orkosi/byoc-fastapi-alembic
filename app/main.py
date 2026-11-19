"""Sample 3 — FastAPI over Postgres. The platform must find: backend, python, health at /healthz,
start through uvicorn on $PORT (port 8000 by default), Alembic migrations (release: alembic upgrade head),
DATABASE_URL as a database reference and SENDGRID_API_KEY as a required secret."""
import os

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine, text

from app.api.custom.onboarding import router as onboarding_router

DATABASE_URL = os.environ["DATABASE_URL"]
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # a pooled connection the server closed (idle-session timeout) is replaced, not raised
app = FastAPI(title="Orders")
app.include_router(onboarding_router)


@app.get("/healthz")
def healthz():
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"ok": True}


@app.get("/orders")
def orders():
    with engine.connect() as conn:
        rows = conn.execute(text("select id, total from orders order by id")).all()
    return [{"id": r.id, "total": float(r.total)} for r in rows]


_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


@app.get("/app/onboarding", response_class=HTMLResponse, include_in_schema=False)
def onboarding_page():
    """Serve the onboarding page for signed-in users."""
    template_path = _TEMPLATE_DIR / "onboarding.html"
    if not template_path.is_file():
        return HTMLResponse(content="<h1>Onboarding page not found</h1>", status_code=404)
    return HTMLResponse(content=template_path.read_text())
