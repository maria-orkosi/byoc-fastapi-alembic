"""Parse Alembic migrations, build a dependency DAG, visualise it, and compute
rollback paths."""

import ast
from pathlib import Path
from typing import Optional

import networkx as nx


def _extract_assignment_value(filepath: str, var_name: str):
    """Parse a Python file and return the value assigned to *var_name*.

    Returns:
        * ``None`` when the variable is not found or assigned ``None``.
        * A ``str`` for single-string assignments.
        * A ``list[str]`` for tuple/list assignments (e.g. merge ``down_revision``).
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    def _value_from_node(node):
        """Extract the value from an assignment value node."""
        if isinstance(node, ast.Constant):
            if node.value is None:
                return None
            if isinstance(node.value, str):
                return node.value
            return node.value
        if isinstance(node, (ast.Tuple, ast.List)):
            values = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    values.append(elt.value)
            return values if values else None
        return None

    for node in ast.walk(tree):
        # Handle plain assignments: revision = "abc"
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    return _value_from_node(node.value)

        # Handle annotated assignments: revision: str = "abc"
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == var_name:
                if node.value is not None:
                    return _value_from_node(node.value)

    return None


def _extract_docstring(filepath: str) -> Optional[str]:
    """Return the module-level docstring (the Alembic migration message)."""
    with open(filepath, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    doc = ast.get_docstring(tree)
    return doc


def _extract_depends_on(filepath: str) -> Optional[list]:
    """Return the ``depends_on`` list from a migration file, or None.

    Handles bare strings, tuples, and lists, as well as ``ast.AnnAssign``.
    """
    with open(filepath, "r", encoding="utf-8") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    def _collect_strings(node):
        """Collect string values from a Constant, Tuple, or List node."""
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str):
                return [node.value]
            if node.value is None:
                return None
        if isinstance(node, (ast.Tuple, ast.List)):
            values = []
            for elt in node.elts:
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                    values.append(elt.value)
            return values if values else None
        return None

    for node in ast.walk(tree):
        # Plain assignment: depends_on = [...]
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "depends_on":
                    return _collect_strings(node.value)

        # Annotated assignment: depends_on: type = [...]
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "depends_on":
                if node.value is not None:
                    return _collect_strings(node.value)

    return None


def parse_migrations(versions_dir: str = "alembic/versions") -> list[dict]:
    """Parse every ``.py`` migration file in *versions_dir* and return a list of
    dicts with keys: *revision*, *down_revision*, *depends_on*, *docstring*,
    *file*."""
    migrations = []
    versions_path = Path(versions_dir)
    if not versions_path.is_dir():
        return migrations

    for py_file in sorted(versions_path.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        filepath = str(py_file)
        revision = _extract_assignment_value(filepath, "revision")
        if revision is None:
            continue
        down_revision = _extract_assignment_value(filepath, "down_revision")
        depends_on = _extract_depends_on(filepath)
        docstring = _extract_docstring(filepath)

        migrations.append(
            {
                "revision": revision,
                "down_revision": down_revision,
                "depends_on": depends_on,
                "docstring": docstring,
                "file": filepath,
            }
        )

    return migrations


def build_dag(migrations: list[dict]) -> nx.DiGraph:
    """Build a directed acyclic graph where nodes are revision IDs and edges
    point from a parent (down_revision) to child (revision).

    Branch merges declared via ``depends_on`` are also added as edges
    with ``kind=\"depends_on\"``.

    When ``down_revision`` is a list (merge migration), one ``kind=\"parent\"``
    edge is added for each element.
    """
    G = nx.DiGraph()

    for m in migrations:
        rev = m["revision"]
        first_line = (
            m["docstring"].split("\n")[0].strip()
            if m["docstring"]
            else ""
        )
        label = f"{rev[:4]}: {first_line}" if first_line else rev[:4]
        G.add_node(rev, label=label, docstring=m.get("docstring"), file=m.get("file"))

        down = m["down_revision"]
        if down is not None:
            # Handle both a single string and a list of parent revisions
            parents = down if isinstance(down, list) else [down]
            for parent in parents:
                G.add_edge(parent, rev, kind="parent")
                if parent not in G.nodes:
                    G.add_node(parent, label=parent[:4])

        if m.get("depends_on"):
            for dep in m["depends_on"]:
                if dep not in G.nodes:
                    G.add_node(dep, label=dep[:4])
                G.add_edge(dep, rev, kind="depends_on")

    return G


def find_heads(G: nx.DiGraph) -> list[str]:
    """Return nodes with no outgoing edges (heads)."""
    return [n for n in G.nodes if G.out_degree(n) == 0]


def find_roots(G: nx.DiGraph) -> list[str]:
    """Return nodes with no incoming edges (roots)."""
    return [n for n in G.nodes if G.in_degree(n) == 0]


def compute_rollback_path(
    G: nx.DiGraph, target_revision: str
) -> Optional[list[str]]:
    """Compute the ordered list of downgrade steps from every current head
    down to (and including) *target_revision*.

    Only ``kind='parent'`` edges are traversed — ``depends_on`` edges are
    excluded so the printed ``alembic downgrade`` sequence is valid.

    For merge heads (one head with multiple parent edges), the steps are
    ordered so that downgrading each revision directly (``alembic downgrade
    <rev>``) is valid.

    Returns a list of revision IDs to downgrade **to** (each step moves
    the database from one revision to its parent).  The first step is
    always a downgrade from a head to its parent; the final step
    downgrades to *target_revision* itself.

    If the target is not reachable from any head, returns None.
    """
    heads = find_heads(G)
    if not heads:
        return None

    # Build a subgraph containing only 'parent' edges (ignore 'depends_on')
    parent_G = nx.DiGraph()
    for u, v, d in G.edges(data=True):
        if d.get("kind", "parent") == "parent":
            parent_G.add_edge(u, v)
    # Copy node data
    for n, data in G.nodes(data=True):
        if n not in parent_G:
            parent_G.add_node(n, **data)

    rev = parent_G.reverse(copy=True)

    for head in heads:
        if head == target_revision:
            # We are already at target; single downgrade to it (no-op) -> empty
            return []
        try:
            path = nx.shortest_path(rev, source=head, target=target_revision)
            # path = [head, parent_of_head, ..., target_revision]
            # The downgrade steps are the intermediate revision IDs
            # excluding the head itself (since we start there):
            # downgrade to path[1], then path[2], ..., target_revision
            return path[1:]  # list of revisions to downgrade **to**
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue

    return None


def render_graph_png(
    G: nx.DiGraph, output_path: str = "migrations_graph.png"
) -> str:
    """Render the migration DAG as a PNG image using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pos = nx.spring_layout(G, seed=42, k=2)
    labels = nx.get_node_attributes(G, "label")
    heads = find_heads(G)

    plt.figure(figsize=(12, 8))

    # Separate edges by kind
    parent_edges = [(u, v) for u, v, d in G.edges(data=True)
                    if d.get("kind") != "depends_on"]
    depends_on_edges = [(u, v) for u, v, d in G.edges(data=True)
                        if d.get("kind") == "depends_on"]

    # Draw parent edges (solid)
    nx.draw_networkx_edges(G, pos, edgelist=parent_edges,
                           arrowstyle="->", arrowsize=20,
                           edge_color="gray", alpha=0.7)

    # Draw depends_on edges (dashed, different color)
    nx.draw_networkx_edges(G, pos, edgelist=depends_on_edges,
                           arrowstyle="->", arrowsize=20,
                           edge_color="orange", style="dashed", alpha=0.7)

    # Draw regular nodes
    regular_nodes = [n for n in G.nodes if n not in heads]
    nx.draw_networkx_nodes(G, pos, nodelist=regular_nodes,
                           node_size=1800, node_color="steelblue", alpha=0.9)

    # Draw head nodes with a different color / border
    if heads:
        nx.draw_networkx_nodes(G, pos, nodelist=heads,
                               node_size=2000, node_color="darkorange",
                               edgecolors="gold", linewidths=2, alpha=0.9)

    nx.draw_networkx_labels(
        G, pos, labels=labels, font_size=8, font_color="white", font_weight="bold"
    )

    plt.title("Alembic Migrations Graph", fontsize=14, fontweight="bold")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()
    return output_path


def render_graph_svg(
    G: nx.DiGraph, output_path: str = "migrations_graph.svg"
) -> str:
    """Render the migration DAG as an SVG image using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    pos = nx.spring_layout(G, seed=42, k=2)
    labels = nx.get_node_attributes(G, "label")
    heads = find_heads(G)

    plt.figure(figsize=(12, 8))

    # Separate edges by kind
    parent_edges = [(u, v) for u, v, d in G.edges(data=True)
                    if d.get("kind") != "depends_on"]
    depends_on_edges = [(u, v) for u, v, d in G.edges(data=True)
                        if d.get("kind") == "depends_on"]

    # Draw parent edges (solid)
    nx.draw_networkx_edges(G, pos, edgelist=parent_edges,
                           arrowstyle="->", arrowsize=20,
                           edge_color="gray", alpha=0.7)

    # Draw depends_on edges (dashed, different color)
    nx.draw_networkx_edges(G, pos, edgelist=depends_on_edges,
                           arrowstyle="->", arrowsize=20,
                           edge_color="orange", style="dashed", alpha=0.7)

    # Draw regular nodes
    regular_nodes = [n for n in G.nodes if n not in heads]
    nx.draw_networkx_nodes(G, pos, nodelist=regular_nodes,
                           node_size=1800, node_color="steelblue", alpha=0.9)

    # Draw head nodes with a different color / border
    if heads:
        nx.draw_networkx_nodes(G, pos, nodelist=heads,
                               node_size=2000, node_color="darkorange",
                               edgecolors="gold", linewidths=2, alpha=0.9)

    nx.draw_networkx_labels(
        G, pos, labels=labels, font_size=8, font_color="white", font_weight="bold"
    )

    plt.title("Alembic Migrations Graph", fontsize=14, fontweight="bold")
    plt.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", format="svg")
    plt.close()
    return output_path


def graph_to_json(G: nx.DiGraph) -> dict:
    """Serialize the graph to a JSON-friendly dict for frontend use."""
    heads = find_heads(G)
    nodes = []
    for node_id in G.nodes:
        nodes.append(
            {
                "id": node_id,
                "label": G.nodes[node_id].get("label", node_id[:4]),
                "docstring": G.nodes[node_id].get("docstring"),
                "is_head": node_id in heads,
            }
        )
    edges = []
    for u, v, d in G.edges(data=True):
        edges.append({
            "from": u,
            "to": v,
            "kind": d.get("kind", "parent"),
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "heads": heads,
        "roots": find_roots(G),
    }
