"""Chat with the graph from the terminal.

Run (from the "backend" directory):
    uv run python -m scripts.chat_cli

Needs Postgres reachable via DATABASE_URL, same as the API.
"""

from app.orchestration.graph import graph

if __name__ == "__main__":
    # user_id is required for retrieve_memories/ingest_memory to do anything -- without
    # it they silently no-op, same as when the API omits it.
    config = {"configurable": {"thread_id": "1", "user_id": "1"}}

    print("Type 'quit' to exit.")

    while True:
        user_input = input("You: ")

        if user_input.lower() in ("quit", "exit"):
            break

        print("AI: ", end="", flush=True)

        # stream_mode="messages" yields (chunk, metadata) as the LLM produces tokens, from
        # *any* node that calls the LLM -- including `summarize`, if it runs this turn. Its
        # metadata["langgraph_node"] tells us which node emitted the chunk, so we only print
        # the actual reply, not the internal summary text.
        for chunk, metadata in graph.stream(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
            stream_mode="messages",
        ):
            if metadata.get("langgraph_node") == "chatbot":
                print(chunk.content, end="", flush=True)

        print()
