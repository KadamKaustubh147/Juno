"""Save a PNG of the compiled LangGraph graph -- a quick visual sanity check.

Run (from the "AI service" directory, with Postgres up since importing
`ai.chatbot` opens the checkpointer connection):
    uv run python -m ai.visualize_graph

Writes graph.png in the current directory.
"""

from ai.chatbot import graph

if __name__ == "__main__":
    # draw_mermaid_png() renders via the hosted mermaid.ink API by default (needs
    # internet, no extra deps). Swap to draw_method=MermaidDrawMethod.PYPPETEER for a
    # local/offline render if that's ever a problem.
    png_bytes = graph.get_graph().draw_mermaid_png()

    with open("graph.png", "wb") as f:
        f.write(png_bytes)

    print("Saved graph.png")
