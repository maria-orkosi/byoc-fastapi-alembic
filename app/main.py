"""Sample 3 — FastAPI over Postgres. The platform must find: backend, python, health at /healthz,
start through uvicorn on $PORT (port 8000 by default), Alembic migrations (release: alembic upgrade head),
DATABASE_URL as a database reference and SENDGRID_API_KEY as a required secret."""
import os

from fastapi import FastAPI
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
engine = create_engine(DATABASE_URL)
app = FastAPI(title="Orders")


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
