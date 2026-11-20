import json
import os
from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # a pooled connection the server closed (idle-session timeout) is replaced, not raised
app = FastAPI(title="Orders")

BRAND_PATH = Path(__file__).resolve().parent.parent / "brand.json"


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


@app.get("/api/brand")
def get_brand():
    """Return the brand configuration for the landing page."""
    if BRAND_PATH.exists():
        with open(BRAND_PATH, "r") as f:
            return json.load(f)
    return {"companyName": "Byoc FastAPI Alembic r5c"}
