"""Sample 3 — FastAPI over Postgres. The platform must find: backend, python, health at /healthz,
start through uvicorn on $PORT (port 8000 by default), Alembic migrations (release: alembic upgrade head),
DATABASE_URL as a database reference and SENDGRID_API_KEY as a required secret."""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import create_engine, text

from app.scanner import scan_all

DATABASE_URL = os.environ["DATABASE_URL"]
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)  # a pooled connection the server closed (idle-session timeout) is replaced, not raised
app = FastAPI(title="Orders")

# ---------------------------------------------------------------------------
# Register custom routers
# ---------------------------------------------------------------------------
from app.api.plan_limits import router as plan_limits_router
app.include_router(plan_limits_router, prefix="/api")


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


@app.get("/scan")
def scan_modules():
    """Scan and categorise every Python module under app/."""
    limit_response = _check_scanner_limit()
    if limit_response is not None:
        return limit_response
    return scan_all("app")


# ---------------------------------------------------------------------------
# Plan-limit helpers for main routes
# ---------------------------------------------------------------------------

def _check_scanner_limit():
    """Check plan limit for scanner.  Returns None or a 403 JSONResponse."""
    try:
        from app.lib.sys.billing import resolveUserPlan
        from app.lib.plan_limits import limitsFor, FEATURES

        plan_info = resolveUserPlan(None)
        plan = plan_info.get("plan", "free")
        limits = limitsFor(plan)

        scanner_limit = limits.get("scanner")
        if scanner_limit is not None:
            feature_label = next((f["label"] for f in FEATURES if f["key"] == "scanner"), "Module Scanner")
            return JSONResponse(
                status_code=403,
                content={
                    "code": "PLAN_LIMIT",
                    "message": f"You have reached the {feature_label} limit of your {plan} plan. Please upgrade.",
                    "upgradeUrl": "/pricing",
                },
            )
    except Exception:
        pass
    return None


def _check_migrations_limit():
    """Check plan limit for migration graph.  Returns None or a 403 JSONResponse."""
    try:
        from app.lib.sys.billing import resolveUserPlan
        from app.lib.plan_limits import limitsFor, FEATURES

        plan_info = resolveUserPlan(None)
        plan = plan_info.get("plan", "free")
        limits = limitsFor(plan)

        migrations_limit = limits.get("migrations")
        if migrations_limit is not None:
            feature_label = next((f["label"] for f in FEATURES if f["key"] == "migrations"), "Migrations")
            return JSONResponse(
                status_code=403,
                content={
                    "code": "PLAN_LIMIT",
                    "message": f"You have reached the {feature_label} limit of your {plan} plan. Please upgrade.",
                    "upgradeUrl": "/pricing",
                },
            )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Migration graph endpoints
# ---------------------------------------------------------------------------


def _build_migration_graph_data():
    """Parse migrations, build the DAG, and return serialisable graph data."""
    from app.migrations_graph import (
        parse_all_migrations,
        build_dag,
        find_heads,
    )
    migrations = parse_all_migrations()
    if not migrations:
        return {"nodes": [], "edges": [], "heads": []}

    G = build_dag(migrations)
    heads = find_heads(G)

    nodes_data = []
    for m in migrations:
        nodes_data.append({"id": m.revision, "docstring": m.docstring})

    edges_data = []
    for u, v, d in G.edges(data=True):
        edges_data.append({"source": u, "target": v, "kind": d.get("kind", "parent")})

    return {
        "nodes": nodes_data,
        "edges": edges_data,
        "heads": heads,
    }


@app.get("/migrations-graph")
def migrations_graph_viewer():
    """Serve the interactive migration graph HTML page with injected data."""
    import json

    limit_response = _check_migrations_limit()
    if limit_response is not None:
        return limit_response

    data = _build_migration_graph_data()

    html_path = os.path.join(os.path.dirname(__file__), "static", "migrations-graph.html")
    if os.path.exists(html_path):
        with open(html_path) as f:
            template = f.read()
    else:
        template = "<html><body><h1>Migration Graph</h1><pre>%MIGRATION_DATA%</pre></body></html>"

    return HTMLResponse(template.replace("%MIGRATION_DATA%", json.dumps(data).replace("</", "<\\/")))


@app.get("/api/migrations-graph")
def migrations_graph_api():
    """Return migration graph data as JSON."""
    limit_response = _check_migrations_limit()
    if limit_response is not None:
        return limit_response

    data = _build_migration_graph_data()
    return JSONResponse(data)


# ---------------------------------------------------------------------------
# Pricing page
# ---------------------------------------------------------------------------

@app.get("/pricing")
def pricing_page():
    """Serve the pricing page."""
    pricing_path = os.path.join(os.path.dirname(__file__), "static", "pricing.html")
    if os.path.exists(pricing_path):
        with open(pricing_path) as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<html><body><h1>Pricing</h1><p>Pricing information coming soon.</p></body></html>")


# Mount static files last
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

