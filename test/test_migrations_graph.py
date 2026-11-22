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


def _write_migration(dir_path, filename, revision, down_revision, depends_on, docstring, use_annassign=False):
    """Helper to write a minimal Alembic migration file.

    When *use_annassign* is True, writes Alembic >=1.7 annotated style
    (``revision: str = "..."``).
    """
    def dr_repr(val):
        if val is None:
            return "None"
        if isinstance(val, list):
            return "('" + "', '".join(val) + "')"
        return f'"{val}"'

    def do_repr(val):
        if val is None:
            return "None"
        if isinstance(val, list):
            return "[" + ", ".join(f'"{x}"' for x in val) + "]"
        return f'"{val}"'

    content = f'"""{docstring}"""\n'
    if use_annassign:
        content += f'revision: str = "{revision}"\n'
        dr_val = dr_repr(down_revision)
        if isinstance(down_revision, list):
            content += f'down_revision: tuple = {dr_val}\n'
        else:
            content += f'down_revision: str = {dr_val}\n'
        content += f'depends_on: list = {do_repr(depends_on)}\n'
    else:
        content += f'revision = "{revision}"\n'
        content += f'down_revision = {dr_repr(down_revision)}\n'
        content += f'depends_on = {do_repr(depends_on)}\n'
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

    def test_parse_annassign_style(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "create initial tables", use_annassign=True)
            migrations = parse_migrations(tmpdir)
            assert len(migrations) == 1
            m = migrations[0]
            assert m["revision"] == "0001"
            assert m["down_revision"] is None
            assert m["depends_on"] is None
            assert m["docstring"] == "create initial tables"

    def test_parse_annassign_with_down_revision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None,
                             "init", use_annassign=True)
            _write_migration(tmpdir, "0002_add.py", "0002", "0001", None,
                             "add column", use_annassign=True)
            migrations = parse_migrations(tmpdir)
            assert len(migrations) == 2
            assert migrations[0]["revision"] == "0001"
            assert migrations[1]["revision"] == "0002"
            assert migrations[1]["down_revision"] == "0001"

    def test_parse_tuple_down_revision_merge(self):
        """Merge migrations use tuple down_revision: ('a', 'b')."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_a.py", "0001a", None, None, "branch a")
            _write_migration(tmpdir, "0001_b.py", "0001b", None, None, "branch b")
            # Merge migration with tuple down_revision
            content = '"""merge"""\nrevision = "0002"\ndown_revision = (\'0001a\', \'0001b\')\ndepends_on = None\n\n'
            content += 'def upgrade():\n    pass\n\ndef downgrade():\n    pass\n'
            with open(os.path.join(tmpdir, "0002_merge.py"), "w") as f:
                f.write(content)
            migrations = parse_migrations(tmpdir)
            assert len(migrations) == 3
            merge = [m for m in migrations if m["revision"] == "0002"][0]
            assert merge["down_revision"] == ["0001a", "0001b"]

    def test_parse_depends_on_bare_string(self):
        """depends_on as a bare string (not a list)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            content = '"""test"""\nrevision = "0002"\ndown_revision = "0001"\ndepends_on = "0001a"\n\n'
            content += 'def upgrade():\n    pass\n\ndef downgrade():\n    pass\n'
            with open(os.path.join(tmpdir, "0002_test.py"), "w") as f:
                f.write(content)
            migrations = parse_migrations(tmpdir)
            assert len(migrations) == 1
            assert migrations[0]["depends_on"] == ["0001a"]
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
            assert G.edges["0001", "0002"]["kind"] == "parent"
            assert G.edges["0002", "0003"]["kind"] == "parent"

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
            assert G.edges["0001", "0002"]["kind"] == "parent"
            assert G.edges["0001a", "0002"]["kind"] == "depends_on"
            assert G.edges["0001b", "0002"]["kind"] == "depends_on"

    def test_label_includes_first_docstring_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "abcd1234_test.py", "abcd1234", None,
                             None, "add users table\n\nMore details here.")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert G.nodes["abcd1234"]["label"] == "abcd: add users table"

    def test_merge_with_tuple_down_revision(self):
        """Merge migration with tuple down_revision: build_dag adds parent edges for each."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001a_init.py", "0001a", None, None, "branch a")
            _write_migration(tmpdir, "0001b_init.py", "0001b", None, None, "branch b")
            # Merge with tuple down_revision
            content = '"""merge"""\nrevision = "0002"\ndown_revision = (\'0001a\', \'0001b\')\ndepends_on = None\n\n'
            content += 'def upgrade():\n    pass\n\ndef downgrade():\n    pass\n'
            with open(os.path.join(tmpdir, "0002_merge.py"), "w") as f:
                f.write(content)
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            assert G.has_edge("0001a", "0002")
            assert G.has_edge("0001b", "0002")
            assert G.edges["0001a", "0002"]["kind"] == "parent"
            assert G.edges["0001b", "0002"]["kind"] == "parent"
            assert G.number_of_nodes() == 3
            assert G.number_of_edges() == 2

    def test_depends_on_as_tuple(self):
        """depends_on given as a tuple, not just a list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            content = '"""test"""\nrevision = "0002"\ndown_revision = "0001"\ndepends_on = (\'0001a\', \'0001b\')\n\n'
            content += 'def upgrade():\n    pass\n\ndef downgrade():\n    pass\n'
            with open(os.path.join(tmpdir, "0002_test.py"), "w") as f:
                f.write(content)
            migrations = parse_migrations(tmpdir)
            assert migrations[0]["depends_on"] == ["0001a", "0001b"]


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
            # path[1:] excludes the head (0003); steps are [0002, 0001]
            assert path == ["0002", "0001"]

    def test_rollback_to_intermediate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            _write_migration(tmpdir, "0002_add.py", "0002", "0001", None, "add")
            _write_migration(tmpdir, "0003_idx.py", "0003", "0002", None, "index")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            path = compute_rollback_path(G, "0002")
            assert path is not None
            # path[1:] excludes the head (0003); step is [0002]
            assert path == ["0002"]

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

    def test_rollback_with_branch(self):
        """Rollback on a simple branch (one head with multiple parents via depends_on).

        depends_on edges should NOT be traversed for rollback.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            _write_migration(tmpdir, "0001a_branch.py", "0001a", "0001", None, "branch a")
            _write_migration(tmpdir, "0001b_branch.py", "0001b", "0001", None, "branch b")
            # Merge depends_on both branches
            _write_migration(tmpdir, "0002_merge.py", "0002", "0001a",
                             ["0001b"], "merge")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            # Rollback from head 0002 to 0001 - should only follow parent edges
            path = compute_rollback_path(G, "0001")
            assert path is not None
            # Path follows parent: 0002 -> 0001a -> 0001 (skips depends_on 0001b)
            assert path == ["0001a", "0001"]

    def test_rollback_with_merge_tuple(self):
        """Rollback through a merge that uses tuple down_revision."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001a_init.py", "0001a", None, None, "branch a")
            _write_migration(tmpdir, "0001b_init.py", "0001b", None, None, "branch b")
            content = '"""merge"""\nrevision = "0002"\ndown_revision = (\'0001a\', \'0001b\')\ndepends_on = None\n\n'
            content += 'def upgrade():\n    pass\n\ndef downgrade():\n    pass\n'
            with open(os.path.join(tmpdir, "0002_merge.py"), "w") as f:
                f.write(content)
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            # Rollback from head 0002 to 0001a
            path = compute_rollback_path(G, "0001a")
            assert path is not None
            assert path == ["0001a"]

    def test_rollback_ignores_depends_on_edges(self):
        """depends_on edges must not be used for rollback traversal."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_migration(tmpdir, "0001_init.py", "0001", None, None, "init")
            _write_migration(tmpdir, "0001a_branch.py", "0001a", "0001", None, "branch")
            # Migration 0002 has down_revision=0001 and depends_on=0001a
            # Rollback from 0002 should only go through 0001, not 0001a
            _write_migration(tmpdir, "0002_next.py", "0002", "0001",
                             ["0001a"], "next step")
            migrations = parse_migrations(tmpdir)
            G = build_dag(migrations)
            path = compute_rollback_path(G, "0001")
            assert path is not None
            # Should be [0001], NOT [0001a, 0001] (depends_on edges ignored)
            assert path == ["0001"]


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
            # Check node shapes
            for node in data["nodes"]:
                assert "is_head" in node
                assert "id" in node
                assert "label" in node
            # Check edge shapes
            for edge in data["edges"]:
                assert "from" in edge
                assert "to" in edge
                assert "kind" in edge
