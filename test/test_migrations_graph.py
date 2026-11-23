"""Tests for app.migrations_graph — Alembic migration parsing, DAG construction,
graph generation, and rollback path computation."""

from __future__ import annotations

import ast
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.migrations_graph import (
    MigrationInfo,
    _SENTINEL,
    _node_to_value,
    _extract_assignment_value,
    _extract_depends_on,
    parse_migration_file,
    parse_all_migrations,
    build_dag,
    find_heads,
    find_roots,
    _hierarchical_pos,
    compute_rollback_path,
    format_downgrade_commands,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp_file(content: str, suffix: str = ".py") -> str:
    """Write content to a temporary file and return its path."""
    fd, path = tempfile.mkstemp(suffix=suffix, text=True)
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path



# ---------------------------------------------------------------------------
# Tests: AST helpers
# ---------------------------------------------------------------------------

def test_extract_revision_assign():
    source = 'revision = "abc123"\n'
    tree = ast.parse(source)
    val = _extract_assignment_value(tree, "revision")
    assert val == "abc123"


def test_extract_revision_ann_assign():
    source = 'revision: str = "abc123"\n'
    tree = ast.parse(source)
    val = _extract_assignment_value(tree, "revision")
    assert val == "abc123"


def test_extract_down_revision_none():
    source = "down_revision = None\n"
    tree = ast.parse(source)
    val = _extract_assignment_value(tree, "down_revision")
    assert val is None


def test_extract_down_revision_none_ann_assign():
    source = "down_revision: str | None = None\n"
    tree = ast.parse(source)
    val = _extract_assignment_value(tree, "down_revision")
    assert val is None


def test_extract_down_revision_tuple():
    """Merge migrations use tuple down_revision."""
    source = "down_revision = ('aaa', 'bbb')\n"
    tree = ast.parse(source)
    val = _extract_assignment_value(tree, "down_revision")
    assert isinstance(val, list)
    assert val == ["aaa", "bbb"]


def test_extract_depends_on_string():
    source = 'depends_on = "xyz"\n'
    tree = ast.parse(source)
    val = _extract_depends_on(tree)
    assert val == ["xyz"]


def test_extract_depends_on_list():
    source = "depends_on = ['aaa', 'bbb']\n"
    tree = ast.parse(source)
    val = _extract_depends_on(tree)
    assert val == ["aaa", "bbb"]


def test_extract_depends_on_tuple():
    source = "depends_on = ('aaa', 'bbb')\n"
    tree = ast.parse(source)
    val = _extract_depends_on(tree)
    assert val == ["aaa", "bbb"]


def test_extract_depends_on_ann_assign():
    source = "depends_on: str = 'xyz'\n"
    tree = ast.parse(source)
    val = _extract_depends_on(tree)
    assert val == ["xyz"]


def test_extract_depends_on_missing():
    source = "revision = 'abc'\n"
    tree = ast.parse(source)
    val = _extract_depends_on(tree)
    assert val == []


# ---------------------------------------------------------------------------
# Tests: parse_migration_file
# ---------------------------------------------------------------------------

def test_parse_root_migration():
    """Root migration has down_revision = None."""
    source = '''"""orders table

Revision ID: 0001
Revises:
"""
revision = "0001"
down_revision = None
'''
    path = _write_temp_file(source)
    try:
        info = parse_migration_file(path)
        assert info is not None
        assert info.revision == "0001"
        assert info.down_revision is None
        assert info.depends_on == []
        assert info.docstring == "orders table"
    finally:
        os.unlink(path)


def test_parse_chain_migration():
    """Migration that follows another."""
    source = '''"""add users table

Revision ID: 0002
Revises: 0001
"""
revision = "0002"
down_revision = "0001"
'''
    path = _write_temp_file(source)
    try:
        info = parse_migration_file(path)
        assert info is not None
        assert info.revision == "0002"
        assert info.down_revision == "0001"
        assert info.docstring == "add users table"
    finally:
        os.unlink(path)


def test_parse_merge_migration():
    """Merge migration with tuple down_revision."""
    source = '''"""merge branches

Revision ID: 0003
Revises: 0001, 0002
"""
revision = "0003"
down_revision = ("0001", "0002")
'''
    path = _write_temp_file(source)
    try:
        info = parse_migration_file(path)
        assert info is not None
        assert info.revision == "0003"
        assert isinstance(info.down_revision, list)
        assert info.down_revision == ["0001", "0002"]
        assert info.docstring == "merge branches"
    finally:
        os.unlink(path)


def test_parse_ann_assign_style():
    """Alembic >=1.7 template style with annotated assignments."""
    source = '''"""add items table

Revision ID: a1b2
Revises: 0001
"""
revision: str = "a1b2"
down_revision: str | None = "0001"
depends_on: str | None = None
'''
    path = _write_temp_file(source)
    try:
        info = parse_migration_file(path)
        assert info is not None
        assert info.revision == "a1b2"
        assert info.down_revision == "0001"
        assert info.docstring == "add items table"
    finally:
        os.unlink(path)


def test_parse_depends_on():
    """Migration with depends_on."""
    source = '''"""add constraints

Revision ID: 0004
Revises: 0003
"""
revision = "0004"
down_revision = "0003"
depends_on = "0002"
'''
    path = _write_temp_file(source)
    try:
        info = parse_migration_file(path)
        assert info is not None
        assert info.revision == "0004"
        assert info.down_revision == "0003"
        assert info.depends_on == ["0002"]
    finally:
        os.unlink(path)


def test_parse_nonexistent_file():
    info = parse_migration_file("/nonexistent/path.py")
    assert info is None


def test_parse_non_python_file():
    info = parse_migration_file("/tmp/not_a_python.txt")
    assert info is None



# ---------------------------------------------------------------------------
# Tests: parse_all_migrations
# ---------------------------------------------------------------------------

def test_parse_all_empty_dir():
    """Non-existent or empty directory returns empty list."""
    with tempfile.TemporaryDirectory() as td:
        result = parse_all_migrations(td)
        assert result == []


def test_parse_all_skips_non_py():
    """Only .py files with valid revisions are parsed."""
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path
        (Path(td) / "readme.md").write_text("hello")
        (Path(td) / "not_a_migration.py").write_text("x = 1\n")
        result = parse_all_migrations(td)
        assert len(result) == 0


def test_parse_all_finds_migrations():
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path
        (Path(td) / "0001_init.py").write_text(
            'revision = "0001"\ndown_revision = None\n'
        )
        (Path(td) / "0002_add_users.py").write_text(
            '"""add users\n\nrevision = "0002"\ndown_revision = "0001"\n"""\n'
        )
        result = parse_all_migrations(td)
        assert len(result) == 2
        revs = {m.revision for m in result}
        assert revs == {"0001", "0002"}



# ---------------------------------------------------------------------------
# Tests: DAG construction
# ---------------------------------------------------------------------------

def test_build_dag_linear_chain():
    m1 = MigrationInfo(revision="0001", down_revision=None, docstring="first")
    m2 = MigrationInfo(revision="0002", down_revision="0001", docstring="second")
    m3 = MigrationInfo(revision="0003", down_revision="0002", docstring="third")
    G = build_dag([m1, m2, m3])
    assert set(G.nodes()) == {"0001", "0002", "0003"}
    assert G.has_edge("0001", "0002")
    assert G.has_edge("0002", "0003")
    assert G["0001"]["0002"]["kind"] == "parent"


def test_build_dag_merge():
    """Merge migration creates multiple parent edges."""
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    m3 = MigrationInfo(revision="0003", down_revision="0001")
    m4 = MigrationInfo(revision="0004", down_revision=["0002", "0003"])
    G = build_dag([m1, m2, m3, m4])
    assert G.has_edge("0002", "0004")
    assert G.has_edge("0003", "0004")
    assert G["0002"]["0004"]["kind"] == "parent"
    assert G["0003"]["0004"]["kind"] == "parent"


def test_build_dag_depends_on_edges():
    """depends_on creates edges with kind='depends_on'."""
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001", depends_on=["000X"])
    G = build_dag([m1, m2])
    assert G.has_edge("000X", "0002")
    assert G["000X"]["0002"]["kind"] == "depends_on"


def test_find_heads_single():
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    G = build_dag([m1, m2])
    heads = find_heads(G)
    assert heads == ["0002"]


def test_find_heads_branch():
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    m3 = MigrationInfo(revision="0003", down_revision="0001")
    G = build_dag([m1, m2, m3])
    heads = set(find_heads(G))
    assert heads == {"0002", "0003"}


def test_find_roots():
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    G = build_dag([m1, m2])
    roots = find_roots(G)
    assert roots == ["0001"]



# ---------------------------------------------------------------------------
# Tests: Rollback path
# ---------------------------------------------------------------------------

def test_rollback_linear_chain():
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    m3 = MigrationInfo(revision="0003", down_revision="0002")
    G = build_dag([m1, m2, m3])
    mig_dict = {m.revision: m for m in [m1, m2, m3]}

    path = compute_rollback_path(G, mig_dict, "0001", current_head="0003")
    assert path == ["0003", "0002", "0001"]


def test_rollback_does_not_follow_depends_on():
    """Rollback should only use parent edges, not depends_on edges."""
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    m3 = MigrationInfo(revision="0003", down_revision="0002", depends_on=["000X"])
    G = build_dag([m1, m2, m3])
    mig_dict = {m.revision: m for m in [m1, m2, m3]}

    path = compute_rollback_path(G, mig_dict, "0001", current_head="0003")
    assert path == ["0003", "0002", "0001"]


def test_rollback_unreachable_target():
    """Target not reachable via parent edges should raise ValueError."""
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    G = build_dag([m1, m2])
    mig_dict = {m.revision: m for m in [m1, m2]}

    G.add_node("9999")
    try:
        compute_rollback_path(G, mig_dict, "9999", current_head="0002")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_format_downgrade_commands():
    path = ["0003", "0002", "0001"]
    cmds = format_downgrade_commands(path)
    assert cmds == [
        "alembic downgrade 0002",
        "alembic downgrade 0001",
    ]


def test_format_downgrade_commands_single():
    """Single-element path yields no commands."""
    cmds = format_downgrade_commands(["0001"])
    assert cmds == []


def test_format_downgrade_commands_empty():
    cmds = format_downgrade_commands([])
    assert cmds == []



# ---------------------------------------------------------------------------
# Tests: Layout
# ---------------------------------------------------------------------------

def test_hierarchical_pos():
    m1 = MigrationInfo(revision="0001", down_revision=None)
    m2 = MigrationInfo(revision="0002", down_revision="0001")
    m3 = MigrationInfo(revision="0003", down_revision="0002")
    G = build_dag([m1, m2, m3])
    pos = _hierarchical_pos(G)
    assert set(pos.keys()) == {"0001", "0002", "0003"}
    # Root should be higher (less negative y) than children
    assert pos["0001"][1] > pos["0002"][1]
    assert pos["0002"][1] > pos["0003"][1]


# ---------------------------------------------------------------------------
# Tests: Graph image generation
# ---------------------------------------------------------------------------

def test_generate_graph_image_png():
    from app.migrations_graph import generate_graph_image
    m1 = MigrationInfo(revision="0001", down_revision=None, docstring="first")
    m2 = MigrationInfo(revision="0002", down_revision="0001", docstring="second")
    G = build_dag([m1, m2])
    mig_dict = {m.revision: m for m in [m1, m2]}

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        out_path = tf.name

    try:
        result = generate_graph_image(G, mig_dict, out_path, fmt="png")
        assert result == out_path
        assert os.path.getsize(out_path) > 0
    finally:
        os.unlink(out_path)


def test_generate_graph_image_svg():
    from app.migrations_graph import generate_graph_image
    m1 = MigrationInfo(revision="0001", down_revision=None, docstring="first")
    m2 = MigrationInfo(revision="0002", down_revision="0001", docstring="second")
    G = build_dag([m1, m2])
    mig_dict = {m.revision: m for m in [m1, m2]}

    with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tf:
        out_path = tf.name

    try:
        result = generate_graph_image(G, mig_dict, out_path, fmt="svg")
        assert result == out_path
        assert os.path.getsize(out_path) > 0
    finally:
        os.unlink(out_path)


def test_generate_html_graph():
    from app.migrations_graph import generate_html_graph
    m1 = MigrationInfo(revision="0001", down_revision=None, docstring="first")
    m2 = MigrationInfo(revision="0002", down_revision="0001", docstring="second")
    G = build_dag([m1, m2])
    mig_dict = {m.revision: m for m in [m1, m2]}

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tf:
        out_path = tf.name

    try:
        result = generate_html_graph(G, mig_dict, out_path)
        assert result == out_path
        assert os.path.getsize(out_path) > 0
        content = open(out_path).read()
        assert "plotly" in content.lower() or "<html" in content.lower()
    finally:
        os.unlink(out_path)



# ---------------------------------------------------------------------------
# Tests: Integration — real alembic/versions directory
# ---------------------------------------------------------------------------

def test_parse_real_migrations():
    """Parse the actual alembic/versions directory in the project."""
    versions_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "alembic", "versions",
    )
    if not os.path.isdir(versions_dir):
        return

    result = parse_all_migrations(versions_dir)
    assert isinstance(result, list)
    assert len(result) >= 1

    G = build_dag(result)
    assert len(G.nodes()) >= 1
    heads = find_heads(G)
    assert len(heads) >= 1
    roots = find_roots(G)
    assert len(roots) >= 1


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [
        test_extract_revision_assign,
        test_extract_revision_ann_assign,
        test_extract_down_revision_none,
        test_extract_down_revision_none_ann_assign,
        test_extract_down_revision_tuple,
        test_extract_depends_on_string,
        test_extract_depends_on_list,
        test_extract_depends_on_tuple,
        test_extract_depends_on_ann_assign,
        test_extract_depends_on_missing,
        test_parse_root_migration,
        test_parse_chain_migration,
        test_parse_merge_migration,
        test_parse_ann_assign_style,
        test_parse_depends_on,
        test_parse_nonexistent_file,
        test_parse_non_python_file,
        test_parse_all_empty_dir,
        test_parse_all_skips_non_py,
        test_parse_all_finds_migrations,
        test_build_dag_linear_chain,
        test_build_dag_merge,
        test_build_dag_depends_on_edges,
        test_find_heads_single,
        test_find_heads_branch,
        test_find_roots,
        test_rollback_linear_chain,
        test_rollback_does_not_follow_depends_on,
        test_rollback_unreachable_target,
        test_format_downgrade_commands,
        test_format_downgrade_commands_single,
        test_format_downgrade_commands_empty,
        test_hierarchical_pos,
        test_generate_graph_image_png,
        test_generate_graph_image_svg,
        test_generate_html_graph,
        test_parse_real_migrations,
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

