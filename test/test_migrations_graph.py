"""Tests for app.migrations_graph module."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.migrations_graph import (
    parse_migrations,
    build_dag,
    compute_rollback_path,
    find_heads,
    find_roots,
    graph_to_json,
)


def _write_migration(dir_path, filename, revision, down_revision, depends_on, docstring):
    """Helper to write a minimal Alembic migration file."""
    dr = "None" if down_revision is None else f'"{down_revision}"'
    do = "None" if depends_on is None else repr(depends_on)
    content = f'"""{docstring}"""\n'
    content += f'revision = "{revision}"\n'
    content += f'down_revision = {dr}\n'
    content += f'depends_on = {do}\n'
    content += '\ndef upgrade():\n    pass\n\ndef downgrade():\n    pass\n'
    with open(os.path.join(dir_path, filename), "w", encoding="utf-8") as f:
        f.write(content)


class TestParseMigrations:
    """Tests for parse_migrations()."""

    def test_parse_single_migration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "create initial tables")
            migrations = parse_migrations(tmpdir)
            assert len(migrations) == 1
            m = migrations[0]
            assert m["revision"] == "0001"
            assert m["down_revision"] is None
            assert m["depends_on"] is None
            assert m["docstring"] == "create initial tables"

    def test_parse_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "create initial tables")
            _write_migration(tmpdir, "0002_add_col.py", "0002", "0001", None,
                             "add column")
            _write_migration(tmpdir, "0003_idx.py", "0003", "0002", None,
                             "add index")
            migrations = parse_migrations(tmpdir)
            assert len(migrations) == 3
            revisions = [m["revision"] for m in migrations]
            assert revisions == ["0001", "0002", "0003"]

    def test_parse_with_depends_on(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "create initial tables")
            _write_migration(tmpdir, "0002_merge.py", "0002", "0001",
                             ["0001a", "0001b"], "merge branches")
            migrations = parse_migrations(tmpdir)
            merge = [m for m in migrations if m["revision"] == "0002"][0]
            assert merge["depends_on"] == ["0001a", "0001b"]
            assert merge["down_revision"] == "0001"

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = parse_migrations(tmpdir)
            assert migrations == []

    def test_missing_directory(self):
        migrations = parse_migrations("/nonexistent/path")
        assert migrations == []

    def test_skips_init_py(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "__init__.py").write_text("")
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "init")
            migrations = parse_migrations(tmpdir)
            assert len(migrations) == 1


class TestBuildDag:
    """Tests for build_dag()."""

    def test_single_node(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "init")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert G.number_of_nodes() == 1
            assert G.number_of_edges() == 0
            assert "0001" in G.nodes
            assert G.nodes["0001"]["label"] == "0001: init"

    def test_linear_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "init")
            _write_migration(tmpdir, "0002_add.py", "0002", "0001", None,
                             "add column")
            _write_migration(tmpdir, "0003_idx.py", "0003", "0002", None,
                             "add index")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert G.number_of_nodes() == 3
            assert G.number_of_edges() == 2
            assert G.has_edge("0001", "0002")
            assert G.has_edge("0002", "0003")

    def test_depends_on_extra_nodes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "init")
            _write_migration(tmpdir, "0002_merge.py", "0002", "0001",
                             ["0001a", "0001b"], "merge")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert G.has_edge("0001a", "0002")
            assert G.has_edge("0001b", "0002")
            assert G.has_edge("0001", "0002")
            assert "0001a" in G.nodes
            assert "0001b" in G.nodes

    def test_label_includes_first_docstring_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "abcd1234_test.py", "abcd1234", None,
                             None, "add users table\n\nMore details here.")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert G.nodes["abcd1234"]["label"] == "abcd: add users table"


class TestFindHeadsAndRoots:
    """Tests for find_heads() and find_roots()."""

    def test_find_heads_single(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "init")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert find_heads(G) == ["0001"]
            assert find_roots(G) == ["0001"]

    def test_find_heads_chain(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "init")
            _write_migration(tmpdir, "0002_add.py", "0002", "0001", None,
                             "add")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert find_heads(G) == ["0002"]
            assert find_roots(G) == ["0001"]


class TestComputeRollbackPath:
    """Tests for compute_rollback_path()."""

    def test_rollback_to_root(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            _write_migration(tmpdir, "0002_add.py", "0002", "0001", None, "add")
            _write_migration(tmpdir, "0003_idx.py", "0003", "0002", None, "index")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            path = compute_rollback_path(G, "0001")
            assert path is not None
            assert path[0] == "0003"
            assert path[-1] == "0001"
            assert len(path) == 3

    def test_rollback_to_intermediate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            _write_migration(tmpdir, "0002_add.py", "0002", "0001", None, "add")
            _write_migration(tmpdir, "0003_idx.py", "0003", "0002", None, "index")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            path = compute_rollback_path(G, "0002")
            assert path is not None
            assert path[0] == "0003"
            assert path[-1] == "0002"
            assert len(path) == 2

    def test_rollback_unreachable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            path = compute_rollback_path(G, "9999")
            assert path is None

    def test_rollback_empty_graph(self):
        G = build_dag([])
        path = compute_rollback_path(G, "0001")
        assert path is None


class TestGraphToJson:
    """Tests for graph_to_json()."""

    def test_graph_to_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            _write_migration(tmpdir, "0002_add.py", "0002", "0001", None, "add")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            data = graph_to_json(G)
            assert "nodes" in data
            assert "edges" in data
            assert "heads" in data
            assert "roots" in data
            assert len(data["nodes"]) == 2
            assert len(data["edges"]) == 1
            assert data["heads"] == ["0002"]
            assert data["roots"] == ["0001"]
