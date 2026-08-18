import asyncio
import sys

sys.path.insert(0, "src")

from langchain_core.messages import AIMessage, HumanMessage
from app.core.config import get_settings
from app.core.llm import get_model_chain
from app.services import rag_service, parse_service


async def main() -> None:
    source = {"text": "Artificial intelligence has revolutionized the educational landscape."}
    _, blocks = parse_service.resolve_source(source)
    store = await rag_service._ensure_index(source, blocks)

    context = rag_service._Context()
    settings = get_settings()
    context.models = [
        model.bind_tools(rag_service._make_tools(store, context))
        for model in get_model_chain(settings.DEFAULT_PROVIDER, settings.DEFAULT_MODEL, temperature=0.4)
    ]
    print("models:", len(context.models))
    graph = rag_service.build_graph(None, context)

    stream = graph.astream_events(
        {"messages": [HumanMessage(content="Where is the most AI-like content?")]},
        config={"recursion_limit": 30},
        version="v2",
    )
    async for event in stream:
        kind = event["event"]
        if kind == "on_chain_end" and event.get("name") == "LangGraph":
            out = event["data"].get("output")
            print("GRAPH END OUTPUT TYPE:", type(out).__name__)
            print("GRAPH END OUTPUT:", repr(out)[:400])
        elif kind in ("on_chat_model_stream", "on_tool_start"):
            print(kind, "|", str(event.get("data", {}))[:120])


asyncio.run(main())