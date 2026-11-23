"""Migration graph — parse Alembic versions, build a DAG, visualise and compute rollback paths.

Supports:
- Static image output (PNG/SVG) via matplotlib
- Interactive HTML output via plotly
- Rollback path calculation via shortest-path on the reversed DAG

Handles Alembic migration file patterns:
- ``revision = "abc"``  (ast.Assign)
- ``revision: str = "abc"``  (ast.AnnAssign, Alembic >=1.7)
- ``down_revision = None``  (root migration)
- ``down_revision = ("a", "b")``  (merge migration, tuple)
- ``depends_on`` as a string, list or tuple
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import networkx as nx


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class MigrationInfo:
    revision: str
    down_revision: str | list[str] | None  # None for roots; list for merges
    depends_on: list[str] = field(default_factory=list)
    docstring: str = ""
    file_path: str = ""


# ---------------------------------------------------------------------------
# Sentinel for "not found"
# ---------------------------------------------------------------------------

_SENTINEL = object()


# ---------------------------------------------------------------------------
# AST helpers — handle both ast.Assign and ast.AnnAssign
# ---------------------------------------------------------------------------

def _node_to_value(node: ast.expr) -> Any:
    """Convert an AST expression node to its Python value."""
    if isinstance(node, ast.Constant):
        return node.value  # None, "abc", 123
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_node_to_value(elt) for elt in node.elts]
    if isinstance(node, ast.Name) and node.id == "None":
        return None
    # Fallback
    return _SENTINEL


def _extract_assignment_value(tree: ast.AST, var_name: str) -> Any:
    """Extract the value assigned to *var_name* from a module AST.

    Handles both ``ast.Assign`` (``rev = "abc"``) and ``ast.AnnAssign``
    (``rev: str = "abc"``).  Returns the Python value (string, None, tuple of
    strings, list of strings) or ``_SENTINEL`` when the variable is not found.
    """
    for node in ast.walk(tree):
        # --- ast.Assign:  revision = "0001"  /  down_revision = ("a","b")
        if isinstance(node, ast.Assign):
            for target in (node.targets if isinstance(node.targets, list) else [node.targets]):
                if isinstance(target, ast.Name) and target.id == var_name:
                    return _node_to_value(node.value)

        # --- ast.AnnAssign:  revision: str = "0001"
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == var_name:
                if node.value is not None:
                    return _node_to_value(node.value)
                return None

    return _SENTINEL


def _extract_depends_on(tree: ast.AST) -> list[str]:
    """Extract the ``depends_on`` value from a migration module AST.

    Handles ``depends_on = "abc"``, ``depends_on = ["a","b"]``,
    ``depends_on: str = "abc"`` (AnnAssign) and the tuple form
    ``depends_on = ("a","b")``.
    """
    raw = _extract_assignment_value(tree, "depends_on")
    if raw is _SENTINEL:
        return []

    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        result: list[str] = []
        for item in raw:
            if isinstance(item, str):
                result.append(item)
        return result
    return []


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_migration_file(filepath: str) -> MigrationInfo | None:
    """Parse a single Alembic migration file and return a MigrationInfo.

    Returns None when *filepath* does not contain a valid ``revision``.
    """
    path = Path(filepath)
    if not path.exists() or path.suffix != ".py":
        return None

    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    # revision
    revision = _extract_assignment_value(tree, "revision")
    if revision is _SENTINEL or revision is None:
        return None
    revision = str(revision)

    # down_revision — may be None, a string, or a tuple/list
    down_rev = _extract_assignment_value(tree, "down_revision")
    if down_rev is _SENTINEL:
        down_rev = None

    # Normalise down_revision: always None, str, or list[str]
    if down_rev is not None and not isinstance(down_rev, str):
        if isinstance(down_rev, list):
            down_rev = [str(r) for r in down_rev]
        else:
            down_rev = str(down_rev)

    # depends_on
    depends_on = _extract_depends_on(tree)

    # docstring — first meaningful line of the module docstring
    docstring = ""
    if (isinstance(tree, ast.Module) and tree.body and
            isinstance(tree.body[0], ast.Expr) and
            isinstance(tree.body[0].value, (ast.Constant, ast.Str))):
        raw_doc = ""
        val = tree.body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            raw_doc = val.value
        elif hasattr(val, 's'):
            raw_doc = val.s
        first_line = raw_doc.strip().split("\n")[0].strip()
        if first_line and not first_line.startswith("Revision ID:"):
            docstring = first_line
        elif first_line.startswith("Revision ID:"):
            lines = raw_doc.strip().split("\n")
            for line in lines[1:]:
                stripped = line.strip()
                if stripped:
                    docstring = stripped
                    break

    return MigrationInfo(
        revision=revision,
        down_revision=down_rev,
        depends_on=depends_on,
        docstring=docstring,
        file_path=str(path),
    )


def parse_all_migrations(versions_dir: str = "alembic/versions") -> list[MigrationInfo]:
    """Parse every ``.py`` file in *versions_dir* and return a list of MigrationInfo."""
    vdir = Path(versions_dir)
    if not vdir.exists() or not vdir.is_dir():
        return []

    migrations: list[MigrationInfo] = []
    for pyfile in sorted(vdir.glob("*.py")):
        if pyfile.name.startswith("_"):
            continue
        info = parse_migration_file(str(pyfile))
        if info is not None:
            migrations.append(info)
    return migrations


# ---------------------------------------------------------------------------
# DAG construction
# ---------------------------------------------------------------------------

def build_dag(migrations: list[MigrationInfo]) -> nx.DiGraph:
    """Build a directed acyclic graph from a list of MigrationInfo.

    Each node is a revision id.  Two edge kinds are added:

    * ``parent`` — solid edge from *down_revision* to *revision* (the
      conventional Alembic chain).  For merge migrations with a tuple/list
      ``down_revision``, one ``parent`` edge is added per element.
    * ``depends_on`` — dashed edge from each entry in ``depends_on`` to
      *revision*, representing an explicit dependency that is NOT the
      standard upgrade/downgrade path.
    """
    G = nx.DiGraph()

    for m in migrations:
        G.add_node(m.revision)

        # Parent edges (solid)
        if m.down_revision is not None:
            if isinstance(m.down_revision, list):
                for parent in m.down_revision:
                    G.add_edge(str(parent), m.revision, kind="parent")
            else:
                G.add_edge(str(m.down_revision), m.revision, kind="parent")

        # depends_on edges (dashed)
        for dep in m.depends_on:
            G.add_edge(dep, m.revision, kind="depends_on")

    return G


def find_heads(G: nx.DiGraph) -> list[str]:
    """Return revisions that have NO outgoing *parent* edges — the current heads."""
    heads: list[str] = []
    for node in G.nodes():
        has_parent_edge_out = False
        for _, __, data in G.out_edges(node, data=True):
            if data.get("kind") == "parent":
                has_parent_edge_out = True
                break
        if not has_parent_edge_out:
            heads.append(node)
    return heads


def find_roots(G: nx.DiGraph) -> list[str]:
    """Return revisions that have NO incoming *parent* edges — the roots."""
    roots: list[str] = []
    for node in G.nodes():
        has_parent_edge_in = False
        for _, __, data in G.in_edges(node, data=True):
            if data.get("kind") == "parent":
                has_parent_edge_in = True
                break
        if not has_parent_edge_in:
            roots.append(node)
    return roots


# ---------------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------------

def _hierarchical_pos(G: nx.DiGraph) -> dict[str, tuple[float, float]]:
    """Compute a simple layered layout for the DAG.

    Roots go to layer 0; each node's layer is max(parent layers) + 1.
    Nodes on the same layer are spread horizontally.
    """
    from collections import deque

    layers: dict[str, int] = {}
    roots = find_roots(G)

    q = deque()
    for r in roots:
        layers[r] = 0
        q.append(r)

    while q:
        node = q.popleft()
        for _, child, data in G.out_edges(node, data=True):
            if data.get("kind") == "parent":
                nl = layers[node] + 1
                if child not in layers or layers[child] < nl:
                    layers[child] = nl
                    q.append(child)

    # Any node without a layer gets layer 0
    for n in G.nodes():
        if n not in layers:
            layers[n] = 0

    # Group by layer
    layer_nodes: dict[int, list[str]] = {}
    for n, l in layers.items():
        layer_nodes.setdefault(l, []).append(n)

    pos: dict[str, tuple[float, float]] = {}
    for l, nodes in layer_nodes.items():
        for i, n in enumerate(sorted(nodes)):
            x = (i + 1) / (len(nodes) + 1) * 10
            y = -l * 3
            pos[n] = (x, y)

    return pos



# ---------------------------------------------------------------------------
# Static image output (matplotlib)
# ---------------------------------------------------------------------------

def generate_graph_image(
    G: nx.DiGraph,
    migrations: dict[str, MigrationInfo],
    output_path: str,
    fmt: str = "png",
) -> str:
    """Render the migration graph as a static image (PNG or SVG) via matplotlib.

    Returns the path to the generated file.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    pos = _hierarchical_pos(G)
    heads = set(find_heads(G))

    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_title("Alembic Migration Graph", fontweight="bold")

    # Draw parent edges (solid)
    parent_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("kind") == "parent"]
    nx.draw_networkx_edges(G, pos, edgelist=parent_edges, ax=ax,
                           edge_color="#4a9eff", arrows=True, arrowsize=15, width=1.5)

    # Draw depends_on edges (dashed)
    dep_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("kind") == "depends_on"]
    if dep_edges:
        nx.draw_networkx_edges(G, pos, edgelist=dep_edges, ax=ax,
                               edge_color="#ff8c42", arrows=True, arrowsize=15,
                               width=1.5, style="dashed")

    # Draw nodes
    node_colors: list[str] = []
    for n in G.nodes():
        if n in heads:
            node_colors.append("#2ecc71")
        else:
            node_colors.append("#4a9eff")

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                           node_size=1200, alpha=0.9)

    # Labels: revision prefix (4 chars) + first docstring line
    labels: dict[str, str] = {}
    for n in G.nodes():
        prefix = n[:4]
        ds = migrations.get(n, MigrationInfo(revision=n)).docstring
        if ds:
            label = f"{prefix}\n{ds[:40]}"
        else:
            label = prefix
        labels[n] = label

    nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=8,
                            font_color="white", font_weight="bold")

    # Legend
    legend_patches = [
        mpatches.Patch(color="#4a9eff", label="Parent edge (solid)"),
        mpatches.Patch(color="#2ecc71", label="Head revision"),
    ]
    if dep_edges:
        legend_patches.append(mpatches.Patch(color="#ff8c42", label="depends_on edge (dashed)"))
    ax.legend(handles=legend_patches, loc="upper right")

    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, format=fmt, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path



# ---------------------------------------------------------------------------
# Interactive HTML output (plotly)
# ---------------------------------------------------------------------------

def generate_html_graph(
    G: nx.DiGraph,
    migrations: dict[str, MigrationInfo],
    output_path: str,
) -> str:
    """Render the migration graph as an interactive HTML page via plotly.

    Returns the path to the generated file.
    """
    import plotly.graph_objects as go

    pos = _hierarchical_pos(G)
    heads = set(find_heads(G))

    # Parent edges (solid)
    parent_edge_x: list[float] = []
    parent_edge_y: list[float] = []
    for u, v, d in G.edges(data=True):
        if d.get("kind") != "parent":
            continue
        xu, yu = pos[u]
        xv, yv = pos[v]
        parent_edge_x.extend([xu, xv, None])
        parent_edge_y.extend([yu, yv, None])

    parent_edge_trace = go.Scatter(
        x=parent_edge_x, y=parent_edge_y,
        mode="lines",
        line={"color": "#4a9eff", "width": 1.5},
        hoverinfo="none",
        name="parent",
        showlegend=True,
    )

    # depends_on edges (dashed)
    dep_edge_x: list[float] = []
    dep_edge_y: list[float] = []
    for u, v, d in G.edges(data=True):
        if d.get("kind") != "depends_on":
            continue
        xu, yu = pos[u]
        xv, yv = pos[v]
        dep_edge_x.extend([xu, xv, None])
        dep_edge_y.extend([yu, yv, None])

    dep_edge_trace = None
    if dep_edge_x:
        dep_edge_trace = go.Scatter(
            x=dep_edge_x, y=dep_edge_y,
            mode="lines",
            line={"color": "#ff8c42", "width": 1.5, "dash": "dash"},
            hoverinfo="none",
            name="depends_on",
            showlegend=True,
        )

    # Nodes
    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    node_colors: list[str] = []
    for n in G.nodes():
        x, y = pos[n]
        node_x.append(x)
        node_y.append(y)
        prefix = n[:4]
        ds = migrations.get(n, MigrationInfo(revision=n)).docstring
        text = f"<b>{prefix}</b>"
        if ds:
            text += f"<br>{ds[:60]}"
        node_text.append(text)
        node_colors.append("#2ecc71" if n in heads else "#4a9eff")

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_text,
        textposition="middle center",
        textfont={"size": 10, "color": "white"},
        marker={
            "size": 30,
            "color": node_colors,
            "line": {"width": 2, "color": "#ffffff"},
        },
        hoverinfo="text",
        name="nodes",
        showlegend=False,
    )

    # Build figure
    data = [parent_edge_trace]
    if dep_edge_trace is not None:
        data.append(dep_edge_trace)
    data.append(node_trace)

    fig = go.Figure(data=data)
    fig.update_layout(
        title="Alembic Migration Graph",
        titlefont={"size": 16},
        showlegend=True,
        hovermode="closest",
        xaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        yaxis={"showgrid": False, "zeroline": False, "showticklabels": False},
        plot_bgcolor="#1a1a2e",
        paper_bgcolor="#1a1a2e",
        font={"color": "#e0e0e0"},
        margin={"l": 20, "r": 20, "t": 50, "b": 20},
    )

    fig.write_html(output_path, include_plotlyjs="cdn")
    return output_path



# ---------------------------------------------------------------------------
# Rollback path calculation
# ---------------------------------------------------------------------------

def compute_rollback_path(
    G: nx.DiGraph,
    migrations: dict[str, MigrationInfo],
    target_rev: str,
    current_head: str | None = None,
) -> list[str]:
    """Compute the ordered sequence of downgrade steps from *current_head* to *target_rev*.

    Only follows **parent** edges (the standard Alembic chain), never depends_on edges.
    Returns a list of revision ids to downgrade through, in the order they should be
    applied (starting from the head and moving towards the target).
    """
    if current_head is None:
        heads = find_heads(G)
        if not heads:
            return []
        current_head = heads[0]

    if target_rev not in G.nodes():
        raise ValueError(f"Target revision {target_rev!r} not found in the migration graph")

    # Build a reversed subgraph using only parent edges
    revG = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if d.get("kind") == "parent":
            revG.add_edge(v, u)  # reverse direction

    if current_head not in revG.nodes():
        raise ValueError(f"Current head {current_head!r} not in the reversed graph")

    try:
        path = nx.shortest_path(revG, source=current_head, target=target_rev)
    except nx.NetworkXNoPath:
        raise ValueError(
            f"No downgrade path from head {current_head!r} to target {target_rev!r}"
        )

    return path


def format_downgrade_commands(path: list[str]) -> list[str]:
    """Convert a rollback path into a list of ``alembic downgrade`` commands."""
    if len(path) < 2:
        return []
    commands: list[str] = []
    for i in range(len(path) - 1):
        commands.append(f"alembic downgrade {path[i + 1]}")
    return commands

