#!/usr/bin/env python3
"""Management CLI for Byoc FastAPI Alembic r5c."""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.migrations_graph import (
    parse_migrations,
    build_dag,
    compute_rollback_path,
    render_graph_png,
    render_graph_svg,
    find_heads,
    find_roots,
    graph_to_json,
)


def cmd_migrations_graph(args):
    """Generate a visual dependency graph of all Alembic migrations."""
    migrations = parse_migrations(args.versions_dir)
    if not migrations:
        print("No migrations found.")
        return

    G = build_dag(migrations)
    print(f"Parsed {len(migrations)} migration(s) with {G.number_of_nodes()} node(s) "
          f"and {G.number_of_edges()} edge(s).")
    print(f"Roots: {find_roots(G)}")
    print(f"Heads: {find_heads(G)}")

    png_path = args.output_png or "migrations_graph.png"
    svg_path = args.output_svg or "migrations_graph.svg"

    try:
        result = render_graph_png(G, png_path)
        print(f"PNG graph written to: {result}")
    except ImportError:
        print("matplotlib not available; skipping PNG generation.")

    try:
        result_svg = render_graph_svg(G, svg_path)
        print(f"SVG graph written to: {result_svg}")
    except ImportError:
        print("matplotlib not available; skipping SVG generation.")

    if args.html:
        html_path = args.output_html or "migrations_graph.html"
        _write_html_graph(G, html_path)
        print(f"Interactive HTML graph written to: {html_path}")


def _write_html_graph(G, html_path):
    """Write an interactive HTML graph by reading the shared template from
    ``app/static/migrations-graph.html`` and embedding the graph data."""
    import json

    graph_data = graph_to_json(G)
    data_json = json.dumps(graph_data)

    template_dir = os.path.join(os.path.dirname(__file__), "app", "static")
    template_path = os.path.join(template_dir, "migrations-graph.html")

    if not os.path.isfile(template_path):
        print(f"Warning: template not found at {template_path}, skipping HTML output.")
        return

    with open(template_path, "r", encoding="utf-8") as fh:
        template = fh.read()

    # Embed the full graph JSON so the page can render without an API call
    html = template.replace(
        "/* GRAPH_DATA_PLACEHOLDER */",
        f"var EMBEDDED_GRAPH_DATA = {data_json};",
    )

    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)


def cmd_migrations_rollback(args):
    """Compute and print the downgrade steps to reach a target revision."""
    migrations = parse_migrations(args.versions_dir)
    if not migrations:
        print("No migrations found.")
        return

    G = build_dag(migrations)
    target = args.target_revision
    path = compute_rollback_path(G, target)

    if path is None:
        print(f"Target revision '{target}' is not reachable from any head.")
        print(f"Current heads: {find_heads(G)}")
        return

    if not path:
        print(f"Already at revision '{target}' — nothing to downgrade.")
        return

    print(f"Rollback path from head(s) to revision '{target}':")
    print(f"  Run these commands in order:")
    for step in path:
        print(f"    alembic downgrade {step}")

    if len(path) >= 1:
        print()
        print(f"Or run a single command:")
        print(f"    alembic downgrade {target}")


def main():
    parser = argparse.ArgumentParser(
        description="Byoc FastAPI Alembic r5c management CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    graph_parser = subparsers.add_parser(
        "migrations-graph",
        help="Generate a visual dependency graph of all Alembic migrations",
    )
    graph_parser.add_argument(
        "--versions-dir",
        default="alembic/versions",
        help="Path to the alembic versions directory (default: alembic/versions)",
    )
    graph_parser.add_argument(
        "--output-png",
        default="migrations_graph.png",
        help="Output PNG file path (default: migrations_graph.png)",
    )
    graph_parser.add_argument(
        "--output-svg",
        default="migrations_graph.svg",
        help="Output SVG file path (default: migrations_graph.svg)",
    )
    graph_parser.add_argument(
        "--html",
        action="store_true",
        help="Also generate an interactive HTML version",
    )
    graph_parser.add_argument(
        "--output-html",
        default="migrations_graph.html",
        help="Output HTML file path (default: migrations_graph.html)",
    )

    rollback_parser = subparsers.add_parser(
        "migrations-rollback",
        help="Compute the downgrade steps to reach a target revision",
    )
    rollback_parser.add_argument(
        "target_revision",
        help="Target revision to downgrade to",
    )
    rollback_parser.add_argument(
        "--versions-dir",
        default="alembic/versions",
        help="Path to the alembic versions directory (default: alembic/versions)",
    )

    args = parser.parse_args()

    if args.command == "migrations-graph":
        cmd_migrations_graph(args)
    elif args.command == "migrations-rollback":
        cmd_migrations_rollback(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
