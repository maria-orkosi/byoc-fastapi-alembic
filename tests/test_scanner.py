"""Tests for app.scanner — module auto‑detection and categorisation."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scanner import scan_module, scan_all
from app.scanner import _is_route_module, _is_model_module, _is_service_module
from app.scanner import _is_background_job_module, _is_utility_module
from app.scanner import ModuleInfo



# ---------------------------------------------------------------------------
# Unit tests for AST detection helpers
# ---------------------------------------------------------------------------

def test_detect_route_with_apirouter():
    source = """
from fastapi import APIRouter
router = APIRouter(prefix="/api/v1")

@router.get("/items")
def list_items():
    pass

@router.post("/items")
def create_item():
    pass
"""
    import ast
    tree = ast.parse(source)
    is_route, meta = _is_route_module(tree, source)
    assert is_route is True
    assert meta is not None
    assert meta.path_prefix == "/api/v1"
    assert sorted(meta.http_methods) == ["get", "post"]
    assert meta.endpoint_count == 2


def test_detect_route_with_app_decorators():
    source = """
from fastapi import FastAPI
app = FastAPI()

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.post("/orders")
def create():
    pass
"""
    import ast
    tree = ast.parse(source)
    is_route, meta = _is_route_module(tree, source)
    assert is_route is True
    assert meta is not None
    assert meta.endpoint_count == 2
    assert "get" in meta.http_methods
    assert "post" in meta.http_methods


def test_detect_orm_model():
    source = """
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
"""
    import ast
    tree = ast.parse(source)
    is_model, meta = _is_model_module(tree)
    assert is_model is True
    assert meta is not None
    assert meta.model_type == "orm"
    assert "User" in meta.class_names
    assert any("users" in r for r in meta.relationships)


def test_detect_pydantic_model():
    source = """
from pydantic import BaseModel

class ItemCreate(BaseModel):
    name: str
    price: float
"""
    import ast
    tree = ast.parse(source)
    is_model, meta = _is_model_module(tree)
    assert is_model is True
    assert meta is not None
    assert meta.model_type == "pydantic"
    assert "ItemCreate" in meta.class_names


def test_detect_service():
    source = """
from app.models.user import User

def get_user_by_id(user_id: int) -> User:
    return User.query.get(user_id)

def validate_email(email: str) -> bool:
    return "@" in email
"""
    import ast
    tree = ast.parse(source)
    is_svc, meta = _is_service_module(tree)
    assert is_svc is True
    assert meta is not None
    assert "get_user_by_id" in meta.public_functions
    assert "validate_email" in meta.public_functions


def test_detect_background_job_celery():
    source = """
from celery import shared_task

@shared_task
def send_email(to: str):
    pass

@shared_task
def cleanup():
    pass

CELERY_BEAT_SCHEDULE = {}
"""
    import ast
    tree = ast.parse(source)
    is_bg, meta = _is_background_job_module(tree)
    assert is_bg is True
    assert meta is not None
    assert meta.trigger_type == "celery"
    assert "send_email" in meta.task_names
    assert "cleanup" in meta.task_names
    assert meta.schedule == "cron-like schedule detected"


def test_detect_utility_init():
    import ast
    tree = ast.parse("")
    assert _is_utility_module(tree, "app/__init__.py") is True
    assert _is_utility_module(tree, "app/api/__init__.py") is True


def test_non_route_is_not_identified():
    source = """
def helper():
    return 42
"""
    import ast
    tree = ast.parse(source)
    is_route, _ = _is_route_module(tree, source)
    assert is_route is False


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

def test_scan_all_returns_valid_structure():
    result = scan_all("app")
    assert isinstance(result, dict)
    assert "package" in result
    assert result["package"] == "app"
    assert "modules" in result
    assert "summary" in result
    assert "total" in result["summary"]
    assert "by_category" in result["summary"]
    assert "unknown_count" in result["summary"]
    assert isinstance(result["modules"], list)
    assert len(result["modules"]) > 0


def test_scan_all_has_no_unknowns():
    result = scan_all("app")
    unknowns = [m['path'] for m in result['modules'] if m['category'] == 'unknown']
    assert result["summary"]["unknown_count"] == 0, f"Unexpected unknowns: {unknowns}"


def test_every_module_has_category():
    result = scan_all("app")
    valid_categories = {"route", "model", "service", "background_job", "utility", "unknown"}
    for mod in result["modules"]:
        assert mod["category"] in valid_categories, (
            f"Invalid category '{mod['category']}' for {mod['path']}"
        )


def test_route_modules_have_route_meta():
    result = scan_all("app")
    routes = [m for m in result["modules"] if m["category"] == "route"]
    assert len(routes) > 0, "Expected at least one route module"
    for r in routes:
        assert "route_meta" in r, f"route_meta missing for {r['path']}"
        assert "http_methods" in r["route_meta"]
        assert "endpoint_count" in r["route_meta"]
        assert "path_prefix" in r["route_meta"]
        assert "routes" in r["route_meta"]


def test_model_modules_have_model_meta():
    result = scan_all("app")
    models = [m for m in result["modules"] if m["category"] == "model"]
    assert len(models) > 0, "Expected at least one model module"
    for m in models:
        assert "model_meta" in m, f"model_meta missing for {m['path']}"
        assert "model_type" in m["model_meta"]
        assert m["model_meta"]["model_type"] in ("orm", "pydantic", "both")
        assert "class_names" in m["model_meta"]


def test_service_modules_have_service_meta():
    result = scan_all("app")
    services = [m for m in result["modules"] if m["category"] == "service"]
    assert len(services) > 0, "Expected at least one service module"
    for s in services:
        assert "service_meta" in s, f"service_meta missing for {s['path']}"
        assert "public_functions" in s["service_meta"]


def test_background_job_modules_have_bg_meta():
    result = scan_all("app")
    bg_jobs = [m for m in result["modules"] if m["category"] == "background_job"]
    assert len(bg_jobs) > 0, "Expected at least one background_job module"
    for bj in bg_jobs:
        assert "background_job_meta" in bj, f"background_job_meta missing for {bj['path']}"
        assert "task_names" in bj["background_job_meta"]
        assert "trigger_type" in bj["background_job_meta"]


def test_scan_module_returns_module_info():
    info = scan_module("app/main.py")
    assert isinstance(info, ModuleInfo)
    assert info.category == "route"


def test_scan_module_nonexistent_file():
    info = scan_module("nonexistent.py")
    assert info.category == "unknown"
    assert "parse error" in info.unknown_reason


def test_json_serializable():
    result = scan_all("app")
    json_str = json.dumps(result)
    parsed = json.loads(json_str)
    assert parsed == result


# ---------------------------------------------------------------------------
# Regression tests for non-HTTP decorators (reviewer-requested)
# ---------------------------------------------------------------------------

def test_non_http_decorators_do_not_crash_scan():
    """shared_task(bind=True) and field_validator must not crash scan_module."""
    import ast
    import tempfile

    source = (
        '"""Module with non-HTTP decorators."""\n'
        'from celery import shared_task\n'
        '\n'
        '@shared_task(bind=True)\n'
        'def my_task(self):\n'
        '    pass\n'
        '\n'
        'from pydantic import field_validator\n'
        '\n'
        'class MyModel:\n'
        '    @field_validator("x")\n'
        '    def validate_x(cls, v):\n'
        '        return v\n'
    )

    # 1) Parse and call _is_route_module, _is_background_job_module, _is_model_module
    tree = ast.parse(source)
    is_route, route_meta = _is_route_module(tree, source)
    assert is_route is False, (
        "Should not classify a module with @shared_task and @field_validator as route"
    )

    is_bg, bg_meta = _is_background_job_module(tree)
    assert is_bg is True, "Should detect @shared_task as background job"
    assert bg_meta is not None
    assert "my_task" in bg_meta.task_names, (
        f"my_task should be reported as celery task, got {bg_meta.task_names}"
    )

    is_model, model_meta = _is_model_module(tree)
    # field_validator on a class that inherits from object, not BaseModel — no model detected
    assert is_model is False

    # 2) Write to temp file and call scan_module to ensure no crash
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
        tf.write(source)
        tmp_path = tf.name

    try:
        info = scan_module(tmp_path)
        # The module has celery tasks — it should be classified as background_job
        assert info.category == "background_job", (
            f"Expected background_job, got {info.category}"
        )
    finally:
        os.unlink(tmp_path)



def test_async_handler_with_background_tasks():
    """async def route handler with BackgroundTasks must be reported in the output."""
    import ast
    import tempfile

    source = (
        '"""Route with BackgroundTasks."""\n'
        'from fastapi import APIRouter, BackgroundTasks\n'
        '\n'
        'router = APIRouter(prefix="/api/v1")\n'
        '\n'
        '@router.post("/items")\n'
        'async def create_item(background_tasks: BackgroundTasks):\n'
        '    background_tasks.add_task(some_task)\n'
        '    return {"created": True}\n'
    )

    # Parse and check _is_route_module detects the BackgroundTasks arg
    tree = ast.parse(source)
    is_route, route_meta = _is_route_module(tree, source)
    assert is_route is True, "Should detect APIRouter usage"
    assert route_meta is not None
    assert len(route_meta.background_tasks) > 0, (
        f"Expected background_tasks in route_meta, got {route_meta.background_tasks}"
    )
    bt_handlers = [bt["handler"] for bt in route_meta.background_tasks]
    assert "create_item" in bt_handlers, (
        f"create_item should have BackgroundTasks, got handlers: {bt_handlers}"
    )
    for bt in route_meta.background_tasks:
        assert bt["trigger"] == "BackgroundTasks"

    # Also check _is_background_job_module detects it
    is_bg, bg_meta = _is_background_job_module(tree)
    assert is_bg is True, "Should detect BackgroundTasks as background job"
    assert bg_meta is not None
    assert "create_item" in bg_meta.task_names, (
        f"create_item should be in task_names, got {bg_meta.task_names}"
    )

    # Write to temp file, scan_module should still classify as route (primary category)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
        tf.write(source)
        tmp_path = tf.name

    try:
        info = scan_module(tmp_path)
        assert info.category == "route", (
            f"Expected route category, got {info.category}"
        )
        assert info.route_meta is not None
        assert len(info.route_meta.background_tasks) > 0, (
            "BackgroundTasks should be reported in route_meta"
        )
    finally:
        os.unlink(tmp_path)

def test_route_module_reports_endpoint_paths_and_handlers():
    """app/api/orders.py must report per-endpoint paths and handler names."""
    info = scan_module("app/api/orders.py")
    assert info.category == "route"
    assert info.route_meta is not None
    assert len(info.route_meta.routes) > 0, \
        "Expected at least one route in route_meta.routes"

    # Check that routes contains expected entries
    handlers = {r["handler"] for r in info.route_meta.routes}
    assert "list_orders" in handlers
    assert "create_order" in handlers
    assert "get_order" in handlers

    # Check full paths include the router prefix + endpoint path
    paths = {r["path"] for r in info.route_meta.routes}
    assert "/api/v1/orders" in paths
    assert "/api/v1/orders/{order_id}" in paths

    # Check methods
    methods = {r["method"] for r in info.route_meta.routes}
    assert "get" in methods
    assert "post" in methods


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [
        test_detect_route_with_apirouter,
        test_detect_route_with_app_decorators,
        test_detect_orm_model,
        test_detect_pydantic_model,
        test_detect_service,
        test_detect_background_job_celery,
        test_detect_utility_init,
        test_non_route_is_not_identified,
        test_scan_all_returns_valid_structure,
        test_scan_all_has_no_unknowns,
        test_every_module_has_category,
        test_route_modules_have_route_meta,
        test_model_modules_have_model_meta,
        test_service_modules_have_service_meta,
        test_background_job_modules_have_bg_meta,
        test_scan_module_returns_module_info,
        test_scan_module_nonexistent_file,
        test_json_serializable,
        test_non_http_decorators_do_not_crash_scan,
        test_async_handler_with_background_tasks,
        test_route_module_reports_endpoint_paths_and_handlers,
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
