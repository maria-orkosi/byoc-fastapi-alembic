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
    """Write an interactive HTML graph using Plotly."""
    import json
    from app.migrations_graph import graph_to_json

    graph_data = graph_to_json(G)
    nodes_json = json.dumps(graph_data["nodes"])
    edges_json = json.dumps(graph_data["edges"])

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Migrations Graph - Byoc FastAPI Alembic r5c</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body { margin: 0; padding: 20px; background: #111; color: #e0e0e0; font-family: "Inter", sans-serif; }
    h1 { text-align: center; }
    #graph { width: 100%; height: 80vh; }
  </style>
</head>
<body>
  <h1>Migrations Dependency Graph</h1>
  <div id="graph"></div>
  <script>
    var nodes = NODES_PLACEHOLDER;
    var edges = EDGES_PLACEHOLDER;

    var edgeTraces = edges.map(function(e) {
      var src = nodes.findIndex(function(n) { return n.id === e.from; });
      var tgt = nodes.findIndex(function(n) { return n.id === e.to; });
      return {
        x: [src, tgt],
        y: [0, 0],
        mode: 'lines',
        line: { color: '#888', width: 2 },
        hoverinfo: 'none',
        showlegend: false
      };
    });

    var nodeTrace = {
      x: nodes.map(function(_, i) { return i; }),
      y: nodes.map(function() { return 0; }),
      text: nodes.map(function(n) { return n.label; }),
      mode: 'markers+text',
      textposition: 'bottom center',
      marker: { size: 20, color: '#4A90D9' },
      textfont: { color: '#fff' },
      hoverinfo: 'text',
      type: 'scatter',
      showlegend: false
    };

    var layout = {
      title: 'Alembic Migration Chain',
      paper_bgcolor: '#111',
      plot_bgcolor: '#111',
      font: { color: '#e0e0e0' },
      xaxis: { showgrid: false, zeroline: false, showticklabels: false },
      yaxis: { showgrid: false, zeroline: false, showticklabels: false },
      margin: { l: 40, r: 40, t: 60, b: 80 }
    };

    Plotly.newPlot('graph', edgeTraces.concat([nodeTrace]), layout);
  </script>
</body>
</html>"""

    html = html.replace("NODES_PLACEHOLDER", nodes_json)
    html = html.replace("EDGES_PLACEHOLDER", edges_json)

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

    print(f"Rollback path from head(s) to revision '{target}':")
    print(f"  Downgrade sequence (run in order):")
    for step in path:
        print(f"    alembic downgrade {step}")

    if len(path) > 1:
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
