from __future__ import annotations

import json
import uuid
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage

from .graph import get_graph
from .models import (
    AnalyticsReport,
    BarChartBlock,
    LineChartBlock,
    TableBlock,
    TextBlock,
    ThoughtBlock,
)


def _tool_call_lines(tool_name: str, args: dict) -> list[str]:
    """Generate Vercel AI SDK data stream tool-call + tool-result line pair."""
    call_id = f"call_{uuid.uuid4().hex[:24]}"
    call_line = f'9:{json.dumps({"toolCallId": call_id, "toolName": tool_name, "args": args})}\n'
    result_line = f'a:{json.dumps({"toolCallId": call_id, "result": "{}"})}\n'
    return [call_line, result_line]


def report_to_content_parts(report_data: dict) -> list[dict]:
    """Convert an AnalyticsReport dict into assistant-ui ThreadMessageLike content parts.

    Returns a list of {"type": "text", ...} and {"type": "tool-call", ...} entries
    that assistant-ui can render when loading chat history.
    """
    report = AnalyticsReport(**report_data)
    parts: list[dict] = []

    # Collect text content (title + text blocks)
    text_pieces: list[str] = []
    title_emitted = False

    for block in report.blocks:
        if isinstance(block, ThoughtBlock):
            continue

        if isinstance(block, TextBlock):
            if not title_emitted:
                text_pieces.append(f"## {report.summary_title}\n\n")
                title_emitted = True
            text_pieces.append(block.content + "\n\n")

        elif isinstance(block, LineChartBlock):
            # Flush accumulated text before a tool-call
            if text_pieces:
                parts.append({"type": "text", "text": "".join(text_pieces)})
                text_pieces = []
            call_id = f"call_{uuid.uuid4().hex[:24]}"
            parts.append({
                "type": "tool-call",
                "toolCallId": call_id,
                "toolName": "chart_line",
                "args": {
                    "title": block.title,
                    "x_axis_key": block.x_axis_key,
                    "y_axis_key": block.y_axis_key,
                    "data": block.data or [],
                },
                "result": "{}",
            })

        elif isinstance(block, BarChartBlock):
            if text_pieces:
                parts.append({"type": "text", "text": "".join(text_pieces)})
                text_pieces = []
            call_id = f"call_{uuid.uuid4().hex[:24]}"
            parts.append({
                "type": "tool-call",
                "toolCallId": call_id,
                "toolName": "chart_bar",
                "args": {
                    "title": block.title,
                    "category_key": block.category_key,
                    "value_key": block.value_key,
                    "data": block.data or [],
                },
                "result": "{}",
            })

        elif isinstance(block, TableBlock):
            if text_pieces:
                parts.append({"type": "text", "text": "".join(text_pieces)})
                text_pieces = []
            call_id = f"call_{uuid.uuid4().hex[:24]}"
            parts.append({
                "type": "tool-call",
                "toolCallId": call_id,
                "toolName": "table",
                "args": {
                    "title": block.title,
                    "columns": block.columns,
                    "data": block.data or [],
                },
                "result": "{}",
            })

    # Flush any remaining text
    if text_pieces:
        parts.append({"type": "text", "text": "".join(text_pieces)})

    # Ensure at least one text part exists (assistant-ui requires it)
    if not parts:
        parts.append({"type": "text", "text": ""})

    return parts


async def langgraph_to_datastream(
    messages: list[dict], thread_id: str
) -> AsyncGenerator[str, None]:
    """Bridge LangGraph execution to Vercel AI SDK data stream protocol v1.

    Yields lines in the format:
        f:{"messageId":"..."}            - start frame
        0:"text chunk"                   - text delta
        9:{"toolCallId":...}             - tool call (visualization blocks)
        a:{"toolCallId":...,"result":..} - tool result
        e:{"finishReason":"stop"}        - finish step
        d:{"finishReason":"stop"}        - done
    """
    graph = await get_graph()
    message_id = str(uuid.uuid4())

    # The frontend sends the full message history per Vercel AI SDK convention,
    # but we only need the latest user message. The LangGraph checkpointer
    # maintains the full conversation state server-side — sending all messages
    # would create duplicates because `add_messages` appends by ID and new
    # HumanMessage objects get fresh IDs each time.
    user_messages = [msg for msg in messages if msg.get("role") == "user"]
    last_user = user_messages[-1] if user_messages else {"content": ""}
    lc_messages = [HumanMessage(content=last_user["content"])]

    # Start frame
    yield f'f:{json.dumps({"messageId": message_id})}\n'

    config = {"configurable": {"thread_id": thread_id}}
    input_state = {"messages": lc_messages}
    emitted_thought_count = 0

    async for event in graph.astream(input_state, config=config, stream_mode="updates"):
        for node_name, node_output in event.items():
            # Stream new thoughts incrementally as italic blockquotes
            thought_log = node_output.get("thought_log")
            if thought_log and isinstance(thought_log, list):
                new_thoughts = thought_log[emitted_thought_count:]
                for thought in new_thoughts:
                    yield f'0:{json.dumps(f"> *{thought}*{chr(10)}{chr(10)}")}\n'
                emitted_thought_count = len(thought_log)

            # Stream final report block-by-block
            report_data = node_output.get("analytics_report")
            if report_data:
                report = AnalyticsReport(**report_data)
                title_emitted = False

                for block in report.blocks:
                    if isinstance(block, ThoughtBlock):
                        # Already streamed incrementally above; skip duplicates
                        continue

                    elif isinstance(block, TextBlock):
                        # Stream title before the first text block only
                        if not title_emitted:
                            title_text = f"## {report.summary_title}\n\n"
                            for word in title_text.split(" "):
                                yield f'0:{json.dumps(word + " ")}\n'
                            title_emitted = True
                        for word in block.content.split(" "):
                            yield f'0:{json.dumps(word + " ")}\n'
                        yield f'0:{json.dumps(chr(10) + chr(10))}\n'

                    elif isinstance(block, LineChartBlock):
                        args = {
                            "title": block.title,
                            "x_axis_key": block.x_axis_key,
                            "y_axis_key": block.y_axis_key,
                            "data": block.data or [],
                        }
                        for line in _tool_call_lines("chart_line", args):
                            yield line

                    elif isinstance(block, BarChartBlock):
                        args = {
                            "title": block.title,
                            "category_key": block.category_key,
                            "value_key": block.value_key,
                            "data": block.data or [],
                        }
                        for line in _tool_call_lines("chart_bar", args):
                            yield line

                    elif isinstance(block, TableBlock):
                        args = {
                            "title": block.title,
                            "columns": block.columns,
                            "data": block.data or [],
                        }
                        for line in _tool_call_lines("table", args):
                            yield line

    # Finish + done events
    yield f'e:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}})}\n'
    yield f'd:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}})}\n'
