"""Module scanner — auto‑detects and categorises every Python module under app/.

Classifies each .py file into exactly one category:
  route, model, service, background_job, utility, or unknown.

Outputs a JSON‑serialisable summary mapping module paths to categories and metadata.
"""
from __future__ import annotations

import ast
import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RouteMeta:
    http_methods: list[str] = field(default_factory=list)
    path_prefix: str = ""
    endpoint_count: int = 0
    routes: list[dict[str, str]] = field(default_factory=list)  # {method, path, handler}


@dataclass
class ModelMeta:
    model_type: str = ""          # "orm" | "pydantic" | "both"
    class_names: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)


@dataclass
class ServiceMeta:
    public_functions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class BackgroundJobMeta:
    task_names: list[str] = field(default_factory=list)
    trigger_type: str = ""         # "celery" | "BackgroundTasks" | "unknown"
    schedule: str = ""             # cron-like description or empty


@dataclass
class ModuleInfo:
    path: str
    category: str                  # route | model | service | background_job | utility | unknown
    route_meta: RouteMeta | None = None
    model_meta: ModelMeta | None = None
    service_meta: ServiceMeta | None = None
    background_job_meta: BackgroundJobMeta | None = None
    unknown_reason: str = ""

# ---------------------------------------------------------------------------
# AST‑based detection helpers
# ---------------------------------------------------------------------------

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options", "trace"}


def _is_route_module(tree: ast.AST, source: str) -> tuple[bool, RouteMeta | None]:
    """Detect whether *tree* defines APIRouter instances or route decorators.

    Collects per-endpoint routes with full paths (router prefix + endpoint path),
    HTTP method, and handler name.
    """
    meta = RouteMeta()
    has_router = False
    routes_seen: set[tuple[str, str, str]] = set()  # dedup

    for node in ast.walk(tree):
        # APIRouter instantiation
        if isinstance(node, ast.Assign):
            for target in node.targets if isinstance(node.targets, list) else [node.targets]:
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                    func = node.value.func
                    if (isinstance(func, ast.Name) and func.id == "APIRouter") or \
                       (isinstance(func, ast.Attribute) and func.attr == "APIRouter"):
                        has_router = True
                        for kw in node.value.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                meta.path_prefix = kw.value.value

        # @router.<method> or @app.<method> decorator
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            handler_name = node.name
            for decorator in node.decorator_list:
                endpoint_path = ""

                # Unwrap @<name>(...), @<attr>(...) etc.
                if isinstance(decorator, ast.Call):
                    dec_func = decorator.func
                    # Extract path from first arg if it's a string constant
                    if decorator.args:
                        first = decorator.args[0]
                        if isinstance(first, ast.Constant) and isinstance(first.value, str):
                            endpoint_path = first.value
                elif isinstance(decorator, ast.Attribute):
                    dec_func = decorator
                elif isinstance(decorator, ast.Name):
                    # @shared_task, @lru_cache, etc. — skip
                    continue
                else:
                    continue

                # Skip plain Name funcs wrapped in Call (e.g. @shared_task(bind=True))
                if isinstance(dec_func, ast.Name):
                    continue

                if isinstance(dec_func, ast.Attribute):
                    method, _ = _extract_decorator_info(dec_func)
                    if method:
                        has_router = True
                        if method.lower() not in meta.http_methods:
                            meta.http_methods.append(method.lower())
                        # Build full path
                        full_path = (meta.path_prefix or "") + endpoint_path
                        route_key = (method.lower(), full_path, handler_name)
                        if route_key not in routes_seen:
                            routes_seen.add(route_key)
                            meta.routes.append({
                                "method": method.lower(),
                                "path": full_path,
                                "handler": handler_name,
                            })

    if has_router:
        meta.endpoint_count = len(meta.routes)
        meta.http_methods = sorted(set(meta.http_methods))
        return True, meta

    return False, None


def _extract_decorator_info(dec: ast.Attribute | ast.Call | ast.Name) -> tuple[str, str]:
    """Return (http_method, path_prefix) from a decorator AST node.

    Also returns (path, handler_name) when passed a decorated function node via
    the `method` field for path, and `prefix` for the handler name — callers
    that care about full routes use _extract_endpoint_info instead.
    """
    if isinstance(dec, ast.Name):
        # @shared_task, @lru_cache, @field_validator etc. — not HTTP
        return "", ""
    if isinstance(dec, ast.Attribute):
        if dec.attr.lower() in _HTTP_METHODS:
            return dec.attr.lower(), ""
        return "", ""
    if isinstance(dec, ast.Call):
        sub = dec.func
        if isinstance(sub, ast.Name):
            # @shared_task(bind=True), @field_validator("x"), etc. — not HTTP
            return "", ""
        if isinstance(sub, ast.Attribute):
            method = ""
            path = ""
            if sub.attr.lower() in _HTTP_METHODS:
                method = sub.attr.lower()
            if dec.args:
                first = dec.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    path = first.value
            return method, path
    return "", ""


def _is_model_module(tree: ast.AST) -> tuple[bool, ModelMeta | None]:
    """Detect SQLAlchemy ORM classes and Pydantic BaseModel subclasses."""
    meta = ModelMeta()
    orm_found = False
    pydantic_found = False

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue

        for base in node.bases:
            if isinstance(base, ast.Name):
                bn = base.id
                if bn in ("Base", "DeclarativeBase"):
                    orm_found = True
                    meta.class_names.append(node.name)
                    _collect_relationships(node, meta)
                elif bn == "BaseModel":
                    pydantic_found = True
                    meta.class_names.append(node.name)

            elif isinstance(base, ast.Attribute):
                if base.attr == "BaseModel":
                    pydantic_found = True
                    meta.class_names.append(node.name)
                elif base.attr in ("Base", "DeclarativeBase"):
                    orm_found = True
                    meta.class_names.append(node.name)
                    _collect_relationships(node, meta)

    if orm_found and pydantic_found:
        meta.model_type = "both"
    elif orm_found:
        meta.model_type = "orm"
    elif pydantic_found:
        meta.model_type = "pydantic"
    else:
        return False, None

    return True, meta


def _collect_relationships(class_node: ast.ClassDef, meta: ModelMeta) -> None:
    """Walk a class body to find __tablename__ and relationship() calls."""
    for body_node in ast.walk(class_node):
        if isinstance(body_node, ast.Assign):
            for t in (body_node.targets if isinstance(body_node.targets, list) else [body_node.targets]):
                if isinstance(t, ast.Name) and t.id == "__tablename__":
                    if isinstance(body_node.value, ast.Constant):
                        meta.relationships.append(
                            f"{class_node.name} -> table {body_node.value.value}"
                        )
        if isinstance(body_node, ast.Call):
            f = body_node.func
            if isinstance(f, ast.Name) and f.id == "relationship":
                meta.relationships.append(f"{class_node.name} has relationship")
            elif isinstance(f, ast.Attribute) and f.attr == "relationship":
                meta.relationships.append(f"{class_node.name} has relationship")


def _is_service_module(tree: ast.AST) -> tuple[bool, ServiceMeta | None]:
    """Detect business‑logic modules — functions without HTTP decorators or DB model defs."""
    meta = ServiceMeta()
    has_route = False
    has_model = False
    public_funcs: list[str] = []
    dependencies: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            for d in node.decorator_list:
                d_node = d.func if isinstance(d, ast.Call) else d
                if isinstance(d_node, ast.Attribute) and d_node.attr.lower() in _HTTP_METHODS:
                    has_route = True
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                if isinstance(base, ast.Name) and base.id in ("Base", "BaseModel", "DeclarativeBase"):
                    has_model = True
                elif isinstance(base, ast.Attribute) and base.attr in ("Base", "BaseModel", "DeclarativeBase"):
                    has_model = True

    if has_route or has_model:
        return False, None

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                public_funcs.append(node.name)
            for arg in node.args.args:
                if arg.annotation:
                    anno = ast.unparse(arg.annotation)
                    dependencies.add(anno)

    if not public_funcs:
        return False, None

    meta.public_functions = public_funcs
    meta.dependencies = sorted(dependencies)
    return True, meta


def _is_background_job_module(tree: ast.AST) -> tuple[bool, BackgroundJobMeta | None]:
    """Detect Celery tasks, BackgroundTasks usage, or files in tasks/workers dirs."""
    meta = BackgroundJobMeta()
    task_names: list[str] = []
    trigger = ""

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                d_node = decorator.func if isinstance(decorator, ast.Call) else decorator
                if isinstance(d_node, ast.Name) and d_node.id == "shared_task":
                    task_names.append(node.name)
                    trigger = "celery"
                elif isinstance(d_node, ast.Attribute) and d_node.attr in ("task", "shared_task"):
                    task_names.append(node.name)
                    trigger = "celery"

        if isinstance(node, ast.FunctionDef):
            for body_node in ast.walk(node):
                if isinstance(body_node, ast.Name) and body_node.id == "BackgroundTasks":
                    task_names.append(node.name)
                    trigger = "BackgroundTasks"

        if isinstance(node, ast.Assign):
            for target in (node.targets if isinstance(node.targets, list) else [node.targets]):
                if isinstance(target, ast.Name) and target.id in ("CELERY_BEAT_SCHEDULE", "beat_schedule"):
                    meta.schedule = "cron-like schedule detected"
                    if not trigger:
                        trigger = "celery"

    if not task_names and not trigger:
        return False, None

    meta.task_names = task_names
    meta.trigger_type = trigger or "unknown"
    return True, meta


def _is_utility_module(tree: ast.AST, module_path: str) -> bool:
    """Heuristic: small modules with helpers, config, constants, or init files."""
    if module_path.endswith("__init__.py"):
        return True

    func_count = 0
    class_count = 0
    assign_count = 0

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_count += 1
        elif isinstance(node, ast.ClassDef):
            class_count += 1
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            assign_count += 1

    if assign_count > 0 and func_count <= 2 and class_count == 0:
        return True

    return False


def _safe_parse(filepath: str) -> ast.AST | None:
    """Parse a .py file to AST, returning None on failure."""
    try:
        with open(filepath, "r", encoding="utf-8") as fh:
            source = fh.read()
        return ast.parse(source)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def scan_module(filepath: str) -> ModuleInfo:
    """Classify a single Python module and return its metadata."""
    rel = os.path.relpath(filepath, start=os.getcwd())
    tree = _safe_parse(filepath)
    if tree is None:
        return ModuleInfo(path=rel, category="unknown", unknown_reason="parse error")

    is_route, route_meta = _is_route_module(tree, "")
    if is_route:
        return ModuleInfo(path=rel, category="route", route_meta=route_meta)

    is_model, model_meta = _is_model_module(tree)
    if is_model:
        return ModuleInfo(path=rel, category="model", model_meta=model_meta)

    is_bg, bg_meta = _is_background_job_module(tree)
    if is_bg:
        return ModuleInfo(path=rel, category="background_job", background_job_meta=bg_meta)

    is_svc, svc_meta = _is_service_module(tree)
    if is_svc:
        return ModuleInfo(path=rel, category="service", service_meta=svc_meta)

    if _is_utility_module(tree, rel):
        return ModuleInfo(path=rel, category="utility")

    reason = "no detectable route, model, service, or background-job patterns"
    return ModuleInfo(path=rel, category="unknown", unknown_reason=reason)


def scan_all(package_name: str = "app") -> dict[str, Any]:
    """Scan every .py module under *package_name* and return a summary dict.

    Returns a JSON‑serialisable dict with the shape:
        {
            "package": "<name>",
            "modules": [ { module_info }, … ],
            "summary": { "total": …, "by_category": {…}, … }
        }
    """
    try:
        pkg = importlib.import_module(package_name)
    except (ImportError, ModuleNotFoundError):
        pkg_path = Path(package_name)
        if not pkg_path.exists():
            pkg_path = Path("app")
        module_files = sorted(pkg_path.rglob("*.py"))
        module_paths = [str(p) for p in module_files if "__pycache__" not in str(p)]
    else:
        pkg_path = Path(pkg.__file__).parent if pkg.__file__ else Path(package_name)
        module_files = sorted(pkg_path.rglob("*.py"))
        module_paths = [str(p) for p in module_files if "__pycache__" not in str(p)]

    modules: list[dict[str, Any]] = []
    for mp in module_paths:
        info = scan_module(mp)
        modules.append(_info_to_dict(info))

    counts: dict[str, int] = {}
    for m in modules:
        cat = m["category"]
        counts[cat] = counts.get(cat, 0) + 1

    return {
        "package": package_name,
        "modules": modules,
        "summary": {
            "total": len(modules),
            "by_category": counts,
            "unknown_count": counts.get("unknown", 0),
        },
    }


def _info_to_dict(info: ModuleInfo) -> dict[str, Any]:
    """Serialize a ModuleInfo to a plain dict."""
    d: dict[str, Any] = {
        "path": info.path,
        "category": info.category,
    }
    if info.route_meta:
        d["route_meta"] = {
            "http_methods": info.route_meta.http_methods,
            "path_prefix": info.route_meta.path_prefix,
            "endpoint_count": info.route_meta.endpoint_count,
            "routes": info.route_meta.routes,
        }
    if info.model_meta:
        d["model_meta"] = {
            "model_type": info.model_meta.model_type,
            "class_names": info.model_meta.class_names,
            "relationships": info.model_meta.relationships,
        }
    if info.service_meta:
        d["service_meta"] = {
            "public_functions": info.service_meta.public_functions,
            "dependencies": info.service_meta.dependencies,
        }
    if info.background_job_meta:
        d["background_job_meta"] = {
            "task_names": info.background_job_meta.task_names,
            "trigger_type": info.background_job_meta.trigger_type,
            "schedule": info.background_job_meta.schedule,
        }
    if info.unknown_reason:
        d["unknown_reason"] = info.unknown_reason
    return d

