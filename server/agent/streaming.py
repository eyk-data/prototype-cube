"""Bridge analytics orchestrator to Vercel AI SDK data stream protocol v1."""
from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncGenerator

from .models import (
    AnalyticsReport,
    BarChartBlock,
    LineChartBlock,
    TableBlock,
    TextBlock,
    ThoughtBlock,
    render_report_as_text,
)
from .orchestrator import run_analytics

logger = logging.getLogger(__name__)


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
            if text_pieces:
                parts.append({"type": "text", "text": "".join(text_pieces)})
                text_pieces = []
            call_id = f"call_{uuid.uuid4().hex[:24]}"
            parts.append({
                "type": "tool-call",
                "toolCallId": call_id,
                "toolName": "chart_line",
                "args": {
                    "type": "chart_line",
                    "title": block.title,
                    "x_axis_key": block.x_axis_key,
                    "y_axis_key": block.y_axis_key,
                    "query_spec": block.cube_query.to_cube_api_payload(),
                    "data_override": block.data or [],
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
                    "type": "chart_bar",
                    "title": block.title,
                    "category_key": block.category_key,
                    "value_key": block.value_key,
                    "query_spec": block.cube_query.to_cube_api_payload(),
                    "data_override": block.data or [],
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
                    "type": "table",
                    "title": block.title,
                    "columns": block.columns,
                    "query_spec": block.cube_query.to_cube_api_payload(),
                    "data_override": block.data or [],
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


def _stream_report_blocks(report: AnalyticsReport):
    """Yield Vercel AI SDK lines for each block in a report."""
    title_emitted = False

    for block in report.blocks:
        if isinstance(block, ThoughtBlock):
            continue

        elif isinstance(block, TextBlock):
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
                "type": "chart_line",
                "title": block.title,
                "x_axis_key": block.x_axis_key,
                "y_axis_key": block.y_axis_key,
                "query_spec": block.cube_query.to_cube_api_payload(),
                "data_override": block.data or [],
            }
            for line in _tool_call_lines("chart_line", args):
                yield line

        elif isinstance(block, BarChartBlock):
            args = {
                "type": "chart_bar",
                "title": block.title,
                "category_key": block.category_key,
                "value_key": block.value_key,
                "query_spec": block.cube_query.to_cube_api_payload(),
                "data_override": block.data or [],
            }
            for line in _tool_call_lines("chart_bar", args):
                yield line

        elif isinstance(block, TableBlock):
            args = {
                "type": "table",
                "title": block.title,
                "columns": block.columns,
                "query_spec": block.cube_query.to_cube_api_payload(),
                "data_override": block.data or [],
            }
            for line in _tool_call_lines("table", args):
                yield line


async def pydanticai_to_datastream(
    messages: list[dict], thread_id: str, conversation_history: str = "",
) -> AsyncGenerator[str, None]:
    """Bridge analytics orchestrator to Vercel AI SDK data stream protocol v1.

    Yields lines in the format:
        f:{"messageId":"..."}            - start frame
        0:"text chunk"                   - text delta
        9:{"toolCallId":...}             - tool call (visualization blocks)
        a:{"toolCallId":...,"result":..} - tool result
        e:{"finishReason":"stop"}        - finish step
        d:{"finishReason":"stop"}        - done
    """
    message_id = str(uuid.uuid4())

    user_messages = [msg for msg in messages if msg.get("role") == "user"]
    last_user = user_messages[-1] if user_messages else {"content": ""}
    content = last_user.get("content", "")
    if isinstance(content, list):
        text_parts = [
            p.get("text", "") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        content = " ".join(text_parts)
    user_question = content if isinstance(content, str) else ""

    # Start frame
    yield f'f:{json.dumps({"messageId": message_id})}\n'

    report: AnalyticsReport | None = None

    async for tag, value in run_analytics(user_question, conversation_history):
        if tag == "thought":
            yield f'0:{json.dumps(f"> *{value}*{chr(10)}{chr(10)}")}\n'
        elif tag == "report":
            report = value

    # Stream report blocks
    if report:
        for line in _stream_report_blocks(report):
            yield line

    # Store assistant message in ChatMessage table
    if report:
        _store_assistant_message(thread_id, report)

    # Finish + done events
    yield f'e:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}})}\n'
    yield f'd:{json.dumps({"finishReason": "stop", "usage": {"promptTokens": 0, "completionTokens": 0}})}\n'


def _store_assistant_message(thread_id: str, report: AnalyticsReport) -> None:
    """Persist the assistant's response as a ChatMessage row."""
    from sqlmodel import Session
    # Import engine from main — avoids circular import at module level
    from server.main import engine, ChatMessage

    ai_text = render_report_as_text(report)
    report_dict = report.model_dump()

    with Session(engine) as session:
        session.add(ChatMessage(
            thread_id=thread_id,
            role="assistant",
            content=ai_text,
            report_data=report_dict,
        ))
        session.commit()
