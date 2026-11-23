#!/usr/bin/env python3
"""Management CLI for the Byoc FastAPI Alembic application.

Commands:
    migrations-graph       Generate a visual dependency graph of all migrations
    migrations-rollback    Print the ordered alembic downgrade steps to reach a target revision
"""

from __future__ import annotations

import argparse
import os
import sys


def _setup_path():
    """Ensure the project root is on sys.path."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def cmd_migrations_graph(args: argparse.Namespace) -> None:
    """Generate a migration dependency graph."""
    from app.migrations_graph import (
        parse_all_migrations,
        build_dag,
        find_heads,
        generate_graph_image,
        generate_html_graph,
        MigrationInfo,
    )

    versions_dir = args.versions_dir or "alembic/versions"
    migrations = parse_all_migrations(versions_dir)

    if not migrations:
        print("No migrations found.")
        return

    mig_dict: dict[str, MigrationInfo] = {m.revision: m for m in migrations}
    G = build_dag(migrations)
    heads = find_heads(G)

    print(f"Parsed {len(migrations)} migration(s), {len(G.nodes())} node(s), "
          f"{len(G.edges())} edge(s)")
    if heads:
        print(f"Head revision(s): {', '.join(heads)}")
    else:
        print("No head revisions detected.")

    # Generate PNG
    png_path = args.output_png or "migrations_graph.png"
    generate_graph_image(G, mig_dict, png_path, fmt="png")
    print(f"PNG written to {png_path}")

    # Generate SVG
    svg_path = args.output_svg or "migrations_graph.svg"
    generate_graph_image(G, mig_dict, svg_path, fmt="svg")
    print(f"SVG written to {svg_path}")

    # Optionally generate interactive HTML
    if args.html:
        html_path = args.output_html or "migrations_graph.html"
        generate_html_graph(G, mig_dict, html_path)
        print(f"Interactive HTML written to {html_path}")


def cmd_migrations_rollback(args: argparse.Namespace) -> None:
    """Print the ordered alembic downgrade commands to reach a target revision."""
    from app.migrations_graph import (
        parse_all_migrations,
        build_dag,
        find_heads,
        compute_rollback_path,
        format_downgrade_commands,
        MigrationInfo,
    )

    versions_dir = args.versions_dir or "alembic/versions"
    migrations = parse_all_migrations(versions_dir)

    if not migrations:
        print("No migrations found.")
        return

    mig_dict: dict[str, MigrationInfo] = {m.revision: m for m in migrations}
    G = build_dag(migrations)
    heads = find_heads(G)

    current_head = args.head or (heads[0] if heads else None)
    if current_head is None:
        print("No head revision found — cannot compute rollback path.")
        return

    target = args.target
    if not target:
        print("Error: target revision is required.", file=sys.stderr)
        sys.exit(1)

    try:
        path = compute_rollback_path(G, mig_dict, target, current_head)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if len(path) < 2:
        print(f"Already at target revision {target!r}.")
        return

    commands = format_downgrade_commands(path)
    print(f"Rollback from {current_head!r} to {target!r}:")
    for cmd in commands:
        print(f"  {cmd}")


def main() -> None:
    _setup_path()

    parser = argparse.ArgumentParser(
        description="Management CLI for Byoc FastAPI Alembic",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- migrations-graph ---
    graph_parser = sub.add_parser(
        "migrations-graph",
        help="Generate a visual dependency graph of all migrations",
    )
    graph_parser.add_argument(
        "--versions-dir",
        default="alembic/versions",
        help="Path to Alembic versions directory (default: alembic/versions)",
    )
    graph_parser.add_argument(
        "--output-png",
        default=None,
        help="Output PNG path (default: migrations_graph.png)",
    )
    graph_parser.add_argument(
        "--output-svg",
        default=None,
        help="Output SVG path (default: migrations_graph.svg)",
    )
    graph_parser.add_argument(
        "--html",
        action="store_true",
        help="Also generate an interactive HTML version",
    )
    graph_parser.add_argument(
        "--output-html",
        default=None,
        help="Output HTML path (default: migrations_graph.html)",
    )

    # --- migrations-rollback ---
    rollback_parser = sub.add_parser(
        "migrations-rollback",
        help="Print the ordered alembic downgrade steps to reach a target revision",
    )
    rollback_parser.add_argument(
        "target",
        help="Target revision to downgrade to",
    )
    rollback_parser.add_argument(
        "--versions-dir",
        default="alembic/versions",
        help="Path to Alembic versions directory (default: alembic/versions)",
    )
    rollback_parser.add_argument(
        "--head",
        default=None,
        help="Current head revision (default: auto-detected)",
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
