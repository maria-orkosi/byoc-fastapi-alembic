"""Sample 3 — FastAPI over Postgres. The platform must find: backend, python, health at /healthz,
start through uvicorn on $PORT (port 8000 by default), Alembic migrations (release: alembic upgrade head),
DATABASE_URL as a database reference and SENDGRID_API_KEY as a required secret."""
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
# pool_pre_ping=True ensures stale connections are recycled before use
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
app = FastAPI(title="Orders")

# Mount static files for frontend assets
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


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


# --- Migration Graph API endpoints ---


@app.get("/migrations/graph", response_class=JSONResponse)
def migrations_graph_json():
    """Return the migration graph as JSON for frontend consumption."""
    from app.migrations_graph import parse_migrations, build_dag, graph_to_json

    migrations = parse_migrations()
    G = build_dag(migrations)
    return graph_to_json(G)


@app.get("/migrations/graph.png", response_class=FileResponse)
def migrations_graph_png():
    """Return the migration graph as a PNG image."""
    from app.migrations_graph import parse_migrations, build_dag, render_graph_png

    migrations = parse_migrations()
    G = build_dag(migrations)
    output_path = os.path.join(static_dir, "migrations_graph.png")
    try:
        render_graph_png(G, output_path)
        return FileResponse(output_path, media_type="image/png")
    except ImportError:
        raise HTTPException(status_code=501, detail="matplotlib is not installed")


@app.get("/migrations/graph.svg", response_class=FileResponse)
def migrations_graph_svg():
    """Return the migration graph as an SVG image."""
    from app.migrations_graph import parse_migrations, build_dag, render_graph_svg

    migrations = parse_migrations()
    G = build_dag(migrations)
    output_path = os.path.join(static_dir, "migrations_graph.svg")
    try:
        render_graph_svg(G, output_path)
        return FileResponse(output_path, media_type="image/svg+xml")
    except ImportError:
        raise HTTPException(status_code=501, detail="matplotlib is not installed")


@app.get("/migrations/graph.html", response_class=HTMLResponse)
def migrations_graph_html():
    """Serve the interactive HTML migration graph page."""
    html_path = os.path.join(static_dir, "migrations-graph.html")
    if not os.path.isfile(html_path):
        raise HTTPException(status_code=404, detail="Interactive graph page not found")
    with open(html_path, "r", encoding="utf-8") as fh:
        return HTMLResponse(content=fh.read())


@app.get("/migrations/rollback/{target_revision}", response_class=JSONResponse)
def migrations_rollback(target_revision: str):
    """Compute the rollback path from current heads to a target revision."""
    from app.migrations_graph import (
        parse_migrations,
        build_dag,
        compute_rollback_path,
        find_heads,
    )

    migrations = parse_migrations()
    G = build_dag(migrations)
    path = compute_rollback_path(G, target_revision)

    if path is None:
        raise HTTPException(
            status_code=404,
            detail=f"Target revision '{target_revision}' is not reachable from any head. "
            f"Current heads: {find_heads(G)}",
        )

    return {
        "target_revision": target_revision,
        "downgrade_steps": path,
        "commands": [f"alembic downgrade {step}" for step in path] if path else [],
    }
