from __future__ import annotations

import json
import logging
import os
import psycopg
from psycopg.rows import dict_row
import uuid
from typing import Annotated, Optional

logger = logging.getLogger(__name__)

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from . import cube_client
from .cube_meta import get_cube_meta_context
from .models import (
    AnalyticsReport,
    BarChartBlock,
    CubeQuery,
    FormatterDecision,
    LineChartBlock,
    TableBlock,
    TextBlock,
    ThoughtBlock,
    render_report_as_text,
)
from .specialists import SPECIALISTS
from .tools import cube_builder_tool

MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    specialist_domain: Optional[str]
    cube_query: Optional[dict]
    cube_result: Optional[dict]
    cube_error: Optional[str]
    retry_count: int
    thought_log: list[str]
    analytics_report: Optional[dict]


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

def _get_llm() -> BaseChatModel:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("VERTEX_AI_API_KEY", "")
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

    if api_key and api_key.startswith("AIza"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=api_key)

    # Use Vertex AI with service account or ADC credentials
    from langchain_google_vertexai import ChatVertexAI

    project = os.environ.get("CUBEJS_DB_BQ_PROJECT_ID", "")
    kwargs: dict = {"model_name": "gemini-2.0-flash", "project": project}
    if creds_path:
        from google.oauth2 import service_account

        credentials = service_account.Credentials.from_service_account_file(creds_path)
        kwargs["credentials"] = credentials
    return ChatVertexAI(**kwargs)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def router_node(state: AgentState) -> dict:
    """Classify the user question into a specialist domain."""
    llm = _get_llm()
    system = SystemMessage(
        content=(
            "You are a routing agent. Given the user's question and conversation "
            "history, respond with ONLY one word: either 'marketing' or 'sales'.\n\n"
            "Marketing topics: ads, campaigns, impressions, clicks, CTR, CPC, CPM, "
            "ROAS, CPA, attribution, email performance, ad spend, channel revenue.\n\n"
            "Sales topics: orders, revenue, products, customers, gross profit, margins, "
            "discounts, returns, shipping, AOV, SKUs, variants, stores.\n\n"
            "For follow-up questions (e.g. 'what about last month?'), infer the domain "
            "from the prior conversation.\n\n"
            "If unsure, default to 'marketing'."
        )
    )
    # Follow-up questions like "What about last month?" are ambiguous without prior
    # context. Passing recent messages lets the router infer the domain from the
    # ongoing conversation. A window of 6 messages (~3 turns) keeps the prompt
    # small while providing enough context.
    recent_messages = state["messages"][-6:]

    response = await llm.ainvoke([system] + recent_messages)
    domain = response.content.strip().lower()
    if domain not in SPECIALISTS:
        domain = "marketing"

    thought = f"Analyzing your question — routing to the {domain} analytics specialist."
    return {
        "specialist_domain": domain,
        # Per-turn scratch fields (query, result, error, report) persist in the
        # checkpoint between turns and must be reset at the start of each new turn
        # to avoid stale data from the previous turn leaking into the pipeline.
        "cube_query": None,
        "cube_result": None,
        "cube_error": None,
        "analytics_report": None,
        "retry_count": 0,
        "thought_log": [thought],
    }


async def specialist_node(state: AgentState) -> dict:
    """Use the specialist LLM + tool to build a CubeQuery."""
    config = SPECIALISTS[state["specialist_domain"]]
    llm = _get_llm()
    llm_with_tools = llm.bind_tools([cube_builder_tool])

    cube_meta_context = await get_cube_meta_context()
    system_parts = [
        config.system_instructions,
        "\n\n",
        cube_meta_context,
    ]

    # If retrying after a cube error, include the error for self-correction
    cube_error = state.get("cube_error")
    if cube_error:
        system_parts.append(
            f"\n\n## Previous Query Error\nYour last query failed with: {cube_error}\n"
            "Please fix the query and try again with corrected member names or structure."
        )

    system = SystemMessage(content="".join(system_parts))
    messages = [system] + state["messages"]

    response = await llm_with_tools.ainvoke(messages)

    # Extract the tool call result
    cube_query = None
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_result = cube_builder_tool.invoke(tool_call["args"])
        if tool_result.get("status") == "ok":
            cube_query = tool_result["query"]
            logger.info("CubeQuery from tool:\n%s", CubeQuery(**cube_query).model_dump_json(indent=2))
        else:
            return {
                "cube_error": tool_result.get("message", "Tool validation failed"),
                "retry_count": state.get("retry_count", 0) + 1,
            }

    if cube_query is None:
        # LLM didn't call the tool – build a minimal AnalyticsReport with text
        report = AnalyticsReport(
            report_id=str(uuid.uuid4()),
            summary_title="Response",
            blocks=[
                *[ThoughtBlock(content=t) for t in state.get("thought_log", [])],
                TextBlock(content=response.content),
            ],
        )
        logger.info("AnalyticsReport (text-only):\n%s", report.model_dump_json(indent=2))
        # Store the response as an AIMessage so the checkpointer persists it.
        # In subsequent turns, the specialist LLM sees the full conversation
        # (user questions + agent answers) and can handle follow-ups.
        ai_text = render_report_as_text(report)
        return {
            "analytics_report": report.model_dump(),
            "cube_query": None,
            "messages": [AIMessage(content=ai_text)],
        }

    measures = cube_query.get("measures", [])
    dims = cube_query.get("dimensions", [])
    thought = f"Querying {', '.join(measures)} by {', '.join(dims) or 'total'}."
    return {
        "cube_query": cube_query,
        "thought_log": state.get("thought_log", []) + [thought],
    }


async def data_validator_node(state: AgentState) -> dict:
    """Execute the CubeQuery against CubeJS."""
    raw_query = state.get("cube_query")
    if not raw_query:
        return {"cube_error": "No query to execute", "retry_count": state.get("retry_count", 0) + 1}

    try:
        query = CubeQuery(**raw_query) if isinstance(raw_query, dict) else raw_query
        logger.info("CubeQuery for execution:\n%s", query.model_dump_json(indent=2))
        result = await cube_client.execute_cube_query(query)
        return {"cube_result": result, "cube_error": None}
    except Exception as exc:
        return {
            "cube_error": str(exc),
            "retry_count": state.get("retry_count", 0) + 1,
        }


async def formatter_node(state: AgentState) -> dict:
    """Generate a structured AnalyticsReport from the query results."""
    llm = _get_llm()
    cube_result = state.get("cube_result", {})
    data = cube_result.get("data", [])
    preview = data[:20]

    cube_query = state.get("cube_query", {})
    system = SystemMessage(
        content=(
            "You are an analytics report formatter. Given CubeJS query results, decide "
            "how to present them. Always include a table. Optionally include a chart:\n"
            '- "line" when data has a time dimension with granularity (trend over time)\n'
            '- "bar" when data has categorical dimensions with few groups (comparisons)\n'
            "- null when only a narrative makes sense\n\n"
            "Write a clear, concise narrative with key findings and specific numbers. "
            "Directly address the user's question in your narrative."
        )
    )
    # Without the original question, the formatter LLM only sees raw data and may
    # write a generic summary instead of directly answering what the user asked.
    user_questions = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    question_text = user_questions[-1].content if user_questions else ""
    user_msg = HumanMessage(
        content=(
            f"User's question: {question_text}\n\n"
            f"Query: {json.dumps(cube_query)}\n\n"
            f"Results ({len(data)} rows, showing first {len(preview)}):\n"
            f"{json.dumps(preview, indent=2)}"
        )
    )

    structured_llm = llm.with_structured_output(FormatterDecision)
    decision: FormatterDecision = await structured_llm.ainvoke([system, user_msg])
    logger.info("FormatterDecision:\n%s", decision.model_dump_json(indent=2))

    blocks = []

    # ThoughtBlocks from accumulated log
    for thought in state.get("thought_log", []):
        blocks.append(ThoughtBlock(content=thought))

    # TextBlock with narrative
    blocks.append(TextBlock(content=decision.narrative))

    # TableBlock (always)
    blocks.append(TableBlock(
        title=decision.table_title,
        columns=decision.table_columns,
        cube_query=CubeQuery(**cube_query),
    ))

    # Chart block (optional, based on LLM decision)
    if decision.chart_type == "line":
        blocks.append(LineChartBlock(
            title=decision.chart_title or "Chart",
            x_axis_key=decision.chart_x_or_category or "",
            y_axis_key=decision.chart_y_or_value or "",
            cube_query=CubeQuery(**cube_query),
        ))
    elif decision.chart_type == "bar":
        blocks.append(BarChartBlock(
            title=decision.chart_title or "Chart",
            category_key=decision.chart_x_or_category or "",
            value_key=decision.chart_y_or_value or "",
            cube_query=CubeQuery(**cube_query),
        ))

    # Inject actual data into visualization blocks
    for block in blocks:
        if isinstance(block, (LineChartBlock, BarChartBlock, TableBlock)):
            block.data = data

    report = AnalyticsReport(
        report_id=str(uuid.uuid4()),
        summary_title=decision.summary_title,
        blocks=blocks,
    )
    logger.info("AnalyticsReport:\n%s", report.model_dump_json(indent=2))
    # Store the formatted response as an AIMessage so the checkpointer persists it.
    # In subsequent turns the LLM sees the full conversation (user questions +
    # agent answers) and can handle follow-ups like "what about last month?".
    ai_text = render_report_as_text(report)
    return {
        "analytics_report": report.model_dump(),
        "messages": [AIMessage(content=ai_text)],
    }


async def formatter_error_node(state: AgentState) -> dict:
    """Generate an AnalyticsReport with error information after retries are exhausted."""
    cube_error = state.get("cube_error", "Unknown error")
    blocks = [ThoughtBlock(content=t) for t in state.get("thought_log", [])]
    blocks.append(TextBlock(
        content=(
            f"I wasn't able to retrieve the data. **Error:** {cube_error}\n\n"
            "Could you try rephrasing your question?"
        )
    ))

    report = AnalyticsReport(
        report_id=str(uuid.uuid4()),
        summary_title="Error",
        blocks=blocks,
    )
    logger.info("AnalyticsReport (error):\n%s", report.model_dump_json(indent=2))
    # Persist the error response as an AIMessage so the conversation history
    # reflects that this turn failed — the user can see it and try again.
    ai_text = render_report_as_text(report)
    return {
        "analytics_report": report.model_dump(),
        "messages": [AIMessage(content=ai_text)],
    }


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def after_specialist(state: AgentState) -> str:
    """Route after specialist: if we have a query, validate; if text, go to end."""
    if state.get("cube_query") is not None:
        return "data_validator"
    # LLM responded with text directly (no tool call)
    return "end"


def after_data_validator(state: AgentState) -> str:
    """Route after data validation: success -> formatter, error -> retry or error."""
    if state.get("cube_result") is not None:
        return "formatter"
    if state.get("retry_count", 0) > MAX_RETRIES:
        return "formatter_error"
    return "specialist"  # retry


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_workflow() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("specialist", specialist_node)
    workflow.add_node("data_validator", data_validator_node)
    workflow.add_node("formatter", formatter_node)
    workflow.add_node("formatter_error", formatter_error_node)

    workflow.set_entry_point("router")
    workflow.add_edge("router", "specialist")
    workflow.add_conditional_edges("specialist", after_specialist, {
        "data_validator": "data_validator",
        "end": END,
    })
    workflow.add_conditional_edges("data_validator", after_data_validator, {
        "formatter": "formatter",
        "formatter_error": "formatter_error",
        "specialist": "specialist",
    })
    workflow.add_edge("formatter", END)
    workflow.add_edge("formatter_error", END)

    return workflow


_memory: AsyncPostgresSaver | None = None


async def _get_checkpointer() -> AsyncPostgresSaver:
    global _memory
    if _memory is None:
        db_url = os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/server")
        # Strip SQLAlchemy dialect suffix for psycopg3 native connection
        conn_string = db_url.replace("postgresql+psycopg://", "postgresql://")
        conn = await psycopg.AsyncConnection.connect(conn_string, autocommit=True, row_factory=dict_row)
        _memory = AsyncPostgresSaver(conn=conn)
        await _memory.setup()
    return _memory


async def get_graph():
    """Build and compile the graph with Postgres checkpointer for persistent multi-turn."""
    workflow = build_workflow()
    return workflow.compile(checkpointer=await _get_checkpointer())
