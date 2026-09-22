"""Render the orchestration graph to a PNG without connecting to Postgres.

Run from ``backend/``:
    .venv/bin/python -m scripts.render_graph

Or choose a destination:
    .venv/bin/python -m scripts.render_graph --output /tmp/juno-graph.png

The renderer uses Mermaid Ink, so it needs an internet connection.  It builds the
same compiled graph as the application, attaching an in-memory checkpointer so no
database is opened or modified.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

# Importing the graph reaches the embedding module through its memory nodes.  Disable
# ONNX Runtime's optional device telemetry before that import, keeping this inspection
# script from creating telemetry state beside the image.
os.environ.setdefault("ORT_DISABLE_TELEMETRY_EVENTS", "1")

from langgraph.checkpoint.memory import MemorySaver

from app.orchestration.graph_builder import build_graph


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "artifacts" / "orchestration-graph.png"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Juno's LangGraph orchestration flow.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"PNG to create (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    output: Path = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    graph = build_graph(MemorySaver()).get_graph()
    try:
        graph.draw_mermaid_png(
            output_file_path=str(output),
            background_color="white",
            padding=24,
            frontmatter_config={"config": {"theme": "neutral"}},
        )
    except Exception as exc:
        raise SystemExit(
            "Could not render the graph PNG. Mermaid Ink must be reachable; "
            f"details: {exc}"
        ) from exc

    print(f"Graph image written to {output}")


if __name__ == "__main__":
    main()
