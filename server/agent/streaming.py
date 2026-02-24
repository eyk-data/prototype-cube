from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage

from .graph import get_graph
from .models import AnalyticsReport, ThoughtBlock, render_report_as_text


async def langgraph_to_datastream(
    messages: list[dict], thread_id: str
) -> AsyncGenerator[str, None]:
    """Bridge LangGraph execution to Vercel AI SDK data stream protocol v1.

    Yields lines in the format:
        f:{"messageId":"..."}\n          - start frame
        0:"text chunk"\n                 - text delta
        e:{"finishReason":"stop"}\n      - finish step
        d:{"finishReason":"stop"}\n      - done
    """
    graph = await get_graph()
    message_id = str(uuid.uuid4())

    # Convert frontend messages to LangChain format
    lc_messages = []
    for msg in messages:
        if msg.get("role") == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))

    # Start frame
    yield f'f:{json.dumps({"messageId": message_id})}\n'

    config = {"configurable": {"thread_id": thread_id}}
    input_state = {"messages": lc_messages}
    emitted_thought_count = 0

    async for event in graph.astream(input_state, config=config, stream_mode="updates"):
        for node_name, node_output in event.items():
            # Stream new thoughts immediately as markdown blockquotes
            thought_log = node_output.get("thought_log")
            if thought_log and isinstance(thought_log, list):
                new_thoughts = thought_log[emitted_thought_count:]
                for thought in new_thoughts:
                    yield f'0:{json.dumps(f"> *{thought}*{chr(10)}{chr(10)}")}\n'
                emitted_thought_count = len(thought_log)

            # Stream final report (without ThoughtBlocks — already sent above)
            report_data = node_output.get("analytics_report")
            if report_data:
                report = AnalyticsReport(**report_data)
                report.blocks = [b for b in report.blocks if not isinstance(b, ThoughtBlock)]
                text = render_report_as_text(report)
                for word in text.split(" "):
                    yield f'0:{json.dumps(word + " ")}\n'

    # Finish + done events
    yield f'e:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}})}\n'
    yield f'd:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}})}\n'
