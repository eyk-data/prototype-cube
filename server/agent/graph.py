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
    BlockPlan,
    BlockQuerySpec,
    CubeQuery,
    CubeFilter,
    CubeTimeDimension,
    ExecutedBlock,
    LineChartBlock,
    ReportPlan,
    ReviewResult,
    TableBlock,
    TextBlock,
    ThoughtBlock,
    render_report_as_text,
)
from .specialists import SPECIALISTS
from .tools import cube_builder_tool

MAX_REVISIONS = 2


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    specialist_domain: Optional[str]
    # Planning
    report_plan: Optional[dict]
    # Block execution (loop)
    executed_blocks: list[dict]
    current_block_index: int
    block_errors: list[str]
    # Review
    review_result: Optional[dict]
    revision_count: int
    # Carry-forward
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
# Helpers
# ---------------------------------------------------------------------------

def _build_cube_query_from_spec(spec: BlockQuerySpec) -> dict | None:
    """Convert a BlockQuerySpec into a validated CubeQuery dict using the cube_builder_tool."""
    result = cube_builder_tool.invoke({
        "measures": spec.measures,
        "dimensions": spec.dimensions,
        "time_dimensions": spec.time_dimensions,
        "filters": spec.filters,
        "order": spec.order,
        "limit": spec.limit,
    })
    if result.get("status") == "ok":
        return result["query"]
    return None


def _get_user_question(state: AgentState) -> str:
    """Extract the latest user question from messages."""
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    return user_messages[-1].content if user_messages else ""


def _format_conversation_history(messages: list[BaseMessage], max_messages: int = 10) -> str:
    """Format recent conversation turns into a readable string for LLM context.

    Truncates AI messages to avoid flooding the prompt with verbose report JSON.
    """
    recent = messages[-max_messages:]
    parts = []
    for msg in recent:
        if isinstance(msg, HumanMessage):
            parts.append(f"User: {msg.content}")
        elif isinstance(msg, AIMessage):
            content = msg.content
            if len(content) > 1500:
                content = content[:1500] + "... [truncated]"
            parts.append(f"Assistant: {content}")
    return "\n\n".join(parts)


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
    recent_messages = state["messages"][-6:]

    response = await llm.ainvoke([system] + recent_messages)
    domain = response.content.strip().lower()
    if domain not in SPECIALISTS:
        domain = "marketing"

    thought = f"Analyzing your question — routing to the {domain} analytics specialist."
    return {
        "specialist_domain": domain,
        # Reset per-turn state
        "report_plan": None,
        "executed_blocks": [],
        "current_block_index": 0,
        "block_errors": [],
        "review_result": None,
        "revision_count": 0,
        "analytics_report": None,
        "thought_log": [thought],
    }


async def planner_node(state: AgentState) -> dict:
    """Plan a multi-block analytics report using structured output."""
    llm = _get_llm()
    config = SPECIALISTS[state["specialist_domain"]]
    cube_meta_context = await get_cube_meta_context()

    question = _get_user_question(state)

    system_parts = [
        "You are an analytics report planner. Your job is to design a structured report "
        "that best answers the user's question with appropriate data visualizations.\n\n",

        "## Domain Expertise\n",
        config.system_instructions,
        "\n\n",

        "## Available Block Types\n"
        "- **text**: A narrative paragraph explaining insights. Use for introductions, "
        "summaries, and contextual explanations. No query needed.\n"
        "- **chart_line**: A line chart for trends over time. REQUIRES a time dimension "
        "with granularity in the query. Set x_or_category_key to the time dimension "
        "(e.g. 'fact_daily_ads.date.day') and y_or_value_key to the measure.\n"
        "- **chart_bar**: A bar chart for categorical comparisons. Best for comparing "
        "a few groups. Set x_or_category_key to the category dimension and y_or_value_key "
        "to the measure.\n"
        "- **table**: A data table for detailed numbers. Set columns to the list of "
        "member names to display. Good for showing exact values.\n\n",

        "## Data Storytelling Principles\n"
        "1. Lead with the key insight (text block)\n"
        "2. Support with the most impactful visualization\n"
        "3. Add detail with supplementary visuals or tables\n"
        "4. Conclude with context or recommendations if appropriate\n\n",

        "## Query Construction for Each Block\n"
        "- Each block gets its OWN optimized query — do NOT try to reuse one query for all blocks.\n"
        "- Line charts MUST include granularity in time_dimensions (day/week/month).\n"
        "- Bar charts should limit to a reasonable number of categories (5-10 max).\n"
        "- Tables can show more columns and rows than charts.\n"
        "- Text blocks don't need query_spec (set to null).\n"
        "- For text blocks, set text_guidance describing what to write about.\n\n",

        "## Conversational Follow-Ups\n"
        "Before planning any data queries, check the conversation history below.\n"
        "If the user's question can be answered from previous results already in the "
        "conversation (e.g. 'what was the best selling product?' after you already showed "
        "top products), or if the user explicitly says 'do not run a query':\n"
        "- Set `conversational_response` to true\n"
        "- Produce ONLY text blocks (no data blocks)\n"
        "- Write the **actual answer** in `text_guidance` — include specific numbers and "
        "details from the conversation history. Do NOT write vague planning notes.\n"
        "- Respect explicit user instructions like 'do not run a query'\n\n"
        "If the question requires new data not present in conversation history, "
        "set `conversational_response` to false and plan data blocks as normal.\n\n",

        "## Conversation History\n",
        _format_conversation_history(state["messages"][:-1]),
        "\n\n",

        "## Cube Metadata\n",
        cube_meta_context,
    ]

    # If revising after review, include the feedback
    review_result = state.get("review_result")
    if review_result:
        revision_instructions = review_result.get("revision_instructions", "")
        issues = review_result.get("issues", [])
        system_parts.append(
            f"\n\n## Revision Required\n"
            f"Your previous plan was reviewed and needs improvement.\n"
            f"Issues: {json.dumps(issues)}\n"
            f"Instructions: {revision_instructions}\n"
            f"Please create an improved plan addressing these issues."
        )

    system = SystemMessage(content="".join(system_parts))

    # Include conversation history for follow-up context
    messages = [system] + state["messages"]

    structured_llm = llm.with_structured_output(ReportPlan)
    try:
        plan: ReportPlan = await structured_llm.ainvoke(messages)
    except Exception as exc:
        logger.warning("Planner structured output failed: %s", exc)
        # Fall back to a text-only report
        report = AnalyticsReport(
            report_id=str(uuid.uuid4()),
            summary_title="Response",
            blocks=[
                *[ThoughtBlock(content=t) for t in state.get("thought_log", [])],
                TextBlock(content="I wasn't able to plan a report for this question. Could you try rephrasing?"),
            ],
        )
        ai_text = render_report_as_text(report)
        return {
            "analytics_report": report.model_dump(),
            "messages": [AIMessage(content=ai_text)],
        }

    logger.info("ReportPlan:\n%s", plan.model_dump_json(indent=2))

    # Check if the plan has any data blocks at all
    has_data_blocks = any(b.block_type != "text" for b in plan.blocks)

    if not has_data_blocks:
        # Pure text response — no queries needed
        text_parts = []
        for block in plan.blocks:
            if block.text_guidance:
                text_parts.append(block.text_guidance)
        raw_guidance = " ".join(text_parts) if text_parts else plan.narrative_strategy

        if plan.conversational_response:
            # Planner wrote the actual answer (with numbers) in text_guidance
            combined_text = raw_guidance
        else:
            # text_guidance is a planning note — call LLM to generate proper prose
            llm = _get_llm()
            history = _format_conversation_history(state["messages"][:-1])
            gen_prompt = (
                f"User's question: {question}\n\n"
                f"Conversation history:\n{history}\n\n"
                f"Report guidance: {raw_guidance}\n\n"
                "Write a clear, concise response that directly answers the user's question. "
                "Use specific numbers from the conversation history or guidance if available. "
                "Do not use markdown headers."
            )
            response = await llm.ainvoke([HumanMessage(content=gen_prompt)])
            combined_text = response.content.strip()

        report = AnalyticsReport(
            report_id=str(uuid.uuid4()),
            summary_title=plan.summary_title,
            blocks=[
                *[ThoughtBlock(content=t) for t in state.get("thought_log", [])],
                TextBlock(content=combined_text),
            ],
        )
        ai_text = render_report_as_text(report)
        return {
            "analytics_report": report.model_dump(),
            "messages": [AIMessage(content=ai_text)],
        }

    n_blocks = len(plan.blocks)
    thought = f"Planning report: {plan.summary_title} ({n_blocks} blocks)"
    return {
        "report_plan": plan.model_dump(),
        "thought_log": state.get("thought_log", []) + [thought],
        "executed_blocks": [],
        "current_block_index": 0,
    }


async def block_executor_node(state: AgentState) -> dict:
    """Execute a single block from the plan — processes one block per invocation."""
    plan_data = state.get("report_plan")
    if not plan_data:
        return {"block_errors": ["No report plan found"]}

    plan = ReportPlan(**plan_data)
    idx = state.get("current_block_index", 0)

    if idx >= len(plan.blocks):
        return {}  # All blocks processed

    block_plan = plan.blocks[idx]
    executed = state.get("executed_blocks", [])
    block_errors = state.get("block_errors", [])
    thoughts = state.get("thought_log", [])

    if block_plan.block_type == "text":
        # Generate text using LLM with context from previously executed blocks
        llm = _get_llm()
        question = _get_user_question(state)

        # Build context from previously executed blocks
        data_context_parts = []
        for eb_data in executed:
            eb = ExecutedBlock(**eb_data)
            if eb.data:
                data_context_parts.append(
                    f"Block '{eb.block_plan.purpose}' data preview: "
                    f"{json.dumps(eb.data[:5], default=str)}"
                )

        data_context = "\n".join(data_context_parts) if data_context_parts else "No data available yet."

        history = _format_conversation_history(state["messages"][:-1])

        text_prompt = (
            f"User's question: {question}\n\n"
            f"Conversation history:\n{history}\n\n"
            f"Report context: {plan.narrative_strategy}\n\n"
            f"This text block's purpose: {block_plan.purpose}\n"
            f"Guidance: {block_plan.text_guidance or 'Write a clear, concise paragraph.'}\n\n"
            f"Available data from other blocks:\n{data_context}\n\n"
            "Write a clear, concise paragraph that directly addresses the purpose above. "
            "Use specific numbers from the data and conversation history if available. "
            "Do not use markdown headers."
        )

        response = await llm.ainvoke([HumanMessage(content=text_prompt)])
        text_content = response.content.strip()

        executed_block = ExecutedBlock(
            block_id=block_plan.block_id,
            block_plan=block_plan,
            text_content=text_content,
        )
        thought = f"Executed block {idx + 1}/{len(plan.blocks)}: text"

    else:
        # Data block — build query, execute
        spec = block_plan.query_spec
        if not spec:
            executed_block = ExecutedBlock(
                block_id=block_plan.block_id,
                block_plan=block_plan,
                error="No query_spec provided for data block",
            )
            block_errors = block_errors + [f"Block {block_plan.block_id}: no query_spec"]
            thought = f"Executed block {idx + 1}/{len(plan.blocks)}: {block_plan.block_type} (error: no query)"
        else:
            cube_query = _build_cube_query_from_spec(spec)
            if not cube_query:
                executed_block = ExecutedBlock(
                    block_id=block_plan.block_id,
                    block_plan=block_plan,
                    error="Query validation failed",
                )
                block_errors = block_errors + [f"Block {block_plan.block_id}: query validation failed"]
                thought = f"Executed block {idx + 1}/{len(plan.blocks)}: {block_plan.block_type} (validation error)"
            else:
                try:
                    query_obj = CubeQuery(**cube_query) if isinstance(cube_query, dict) else cube_query
                    logger.info("Executing block %s query:\n%s", block_plan.block_id, query_obj.model_dump_json(indent=2))
                    result = await cube_client.execute_cube_query(query_obj)
                    data = result.get("data", [])

                    executed_block = ExecutedBlock(
                        block_id=block_plan.block_id,
                        block_plan=block_plan,
                        cube_query=cube_query,
                        data=data,
                    )
                    thought = f"Executed block {idx + 1}/{len(plan.blocks)}: {block_plan.block_type} ({len(data)} rows)"
                except Exception as exc:
                    error_msg = str(exc)
                    executed_block = ExecutedBlock(
                        block_id=block_plan.block_id,
                        block_plan=block_plan,
                        cube_query=cube_query,
                        error=error_msg,
                    )
                    block_errors = block_errors + [f"Block {block_plan.block_id}: {error_msg}"]
                    thought = f"Executed block {idx + 1}/{len(plan.blocks)}: {block_plan.block_type} (error)"

    return {
        "executed_blocks": executed + [executed_block.model_dump()],
        "current_block_index": idx + 1,
        "block_errors": block_errors,
        "thought_log": thoughts + [thought],
    }


async def reviewer_node(state: AgentState) -> dict:
    """Review the quality of executed blocks and decide whether to approve or revise."""
    llm = _get_llm()
    question = _get_user_question(state)
    plan_data = state.get("report_plan", {})
    executed = state.get("executed_blocks", [])
    revision_count = state.get("revision_count", 0)

    # Build summary of executed blocks for the reviewer
    block_summaries = []
    for eb_data in executed:
        eb = ExecutedBlock(**eb_data)
        summary = f"- {eb.block_id} ({eb.block_plan.block_type}): "
        if eb.error:
            summary += f"ERROR: {eb.error}"
        elif eb.text_content:
            summary += f"text ({len(eb.text_content)} chars)"
        elif eb.data is not None:
            summary += f"{len(eb.data)} rows"
        else:
            summary += "no data"
        block_summaries.append(summary)

    review_prompt = (
        "You are a quality reviewer for analytics reports. Evaluate whether the "
        "executed report blocks adequately answer the user's question.\n\n"
        f"User's question: {question}\n\n"
        f"Report plan: {json.dumps(plan_data, default=str)}\n\n"
        f"Executed blocks:\n" + "\n".join(block_summaries) + "\n\n"
        "Evaluate on these criteria:\n"
        "1. Relevance: Do the blocks answer the user's question?\n"
        "2. Data accuracy: Are there execution errors?\n"
        "3. Visualization fit: Are the chart types appropriate?\n"
        "4. Completeness: Is anything missing?\n\n"
        "Score from 1-5 (5 is best). Set approved=true if score >= 4. "
        "If not approved, provide specific revision_instructions for the planner."
    )

    structured_llm = llm.with_structured_output(ReviewResult)
    try:
        review: ReviewResult = await structured_llm.ainvoke([HumanMessage(content=review_prompt)])
    except Exception as exc:
        logger.warning("Reviewer structured output failed: %s", exc)
        # Default to approved on reviewer failure
        review = ReviewResult(quality_score=4, approved=True)

    logger.info("ReviewResult:\n%s", review.model_dump_json(indent=2))

    thought = f"Review score: {review.quality_score}/5 — {'approved' if review.approved else 'revision needed'}"

    return {
        "review_result": review.model_dump(),
        "revision_count": revision_count + (0 if review.approved else 1),
        "thought_log": state.get("thought_log", []) + [thought],
    }


async def assembler_node(state: AgentState) -> dict:
    """Assemble executed blocks into a final AnalyticsReport. Pure mechanical — no LLM call."""
    plan_data = state.get("report_plan", {})
    plan = ReportPlan(**plan_data)
    executed = state.get("executed_blocks", [])

    blocks = []

    # ThoughtBlocks from accumulated log
    for thought in state.get("thought_log", []):
        blocks.append(ThoughtBlock(content=thought))

    # Convert executed blocks into report blocks
    for eb_data in executed:
        eb = ExecutedBlock(**eb_data)
        bp = eb.block_plan

        if eb.error:
            # Skip blocks with errors
            continue

        if bp.block_type == "text":
            if eb.text_content:
                blocks.append(TextBlock(content=eb.text_content))

        elif bp.block_type == "chart_line":
            spec = bp.query_spec
            if spec and eb.data is not None and eb.cube_query:
                blocks.append(LineChartBlock(
                    title=spec.title,
                    x_axis_key=spec.x_or_category_key or "",
                    y_axis_key=spec.y_or_value_key or "",
                    cube_query=CubeQuery(**eb.cube_query),
                    data=eb.data,
                ))

        elif bp.block_type == "chart_bar":
            spec = bp.query_spec
            if spec and eb.data is not None and eb.cube_query:
                blocks.append(BarChartBlock(
                    title=spec.title,
                    category_key=spec.x_or_category_key or "",
                    value_key=spec.y_or_value_key or "",
                    cube_query=CubeQuery(**eb.cube_query),
                    data=eb.data,
                ))

        elif bp.block_type == "table":
            spec = bp.query_spec
            if spec and eb.data is not None and eb.cube_query:
                columns = spec.columns or list(eb.data[0].keys()) if eb.data else []
                blocks.append(TableBlock(
                    title=spec.title,
                    columns=columns,
                    cube_query=CubeQuery(**eb.cube_query),
                    data=eb.data,
                ))

    # If all blocks had errors, add an error text
    if not any(isinstance(b, (TextBlock, LineChartBlock, BarChartBlock, TableBlock)) for b in blocks):
        error_msgs = state.get("block_errors", [])
        blocks.append(TextBlock(
            content=(
                "I encountered errors while executing the data queries. "
                f"Errors: {'; '.join(error_msgs) if error_msgs else 'Unknown errors'}\n\n"
                "Could you try rephrasing your question?"
            )
        ))

    report = AnalyticsReport(
        report_id=str(uuid.uuid4()),
        summary_title=plan.summary_title,
        blocks=blocks,
    )
    logger.info("AnalyticsReport:\n%s", report.model_dump_json(indent=2))
    ai_text = render_report_as_text(report)
    return {
        "analytics_report": report.model_dump(),
        "messages": [AIMessage(content=ai_text)],
    }


async def formatter_error_node(state: AgentState) -> dict:
    """Generate an AnalyticsReport with error information after catastrophic failure."""
    block_errors = state.get("block_errors", [])
    error_msg = "; ".join(block_errors) if block_errors else "Unknown error"
    blocks = [ThoughtBlock(content=t) for t in state.get("thought_log", [])]
    blocks.append(TextBlock(
        content=(
            f"I wasn't able to retrieve the data. **Error:** {error_msg}\n\n"
            "Could you try rephrasing your question?"
        )
    ))

    report = AnalyticsReport(
        report_id=str(uuid.uuid4()),
        summary_title="Error",
        blocks=blocks,
    )
    logger.info("AnalyticsReport (error):\n%s", report.model_dump_json(indent=2))
    ai_text = render_report_as_text(report)
    return {
        "analytics_report": report.model_dump(),
        "messages": [AIMessage(content=ai_text)],
    }


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------

def after_planner(state: AgentState) -> str:
    """Route after planner: if analytics_report set (text-only) → end; else → block_executor."""
    if state.get("analytics_report") is not None:
        return "end"
    if state.get("report_plan") is not None:
        return "block_executor"
    return "end"


def after_block_executor(state: AgentState) -> str:
    """Route after block executor: loop or proceed to reviewer."""
    plan_data = state.get("report_plan")
    if not plan_data:
        return "reviewer"
    plan = ReportPlan(**plan_data)
    idx = state.get("current_block_index", 0)
    if idx < len(plan.blocks):
        return "block_executor"  # more blocks to process
    return "reviewer"


def after_reviewer(state: AgentState) -> str:
    """Route after reviewer: if approved → assembler; if revision needed → planner."""
    review_data = state.get("review_result")
    if not review_data:
        return "assembler"
    review = ReviewResult(**review_data)
    if review.approved:
        return "assembler"
    # Check revision count safety valve
    if state.get("revision_count", 0) >= MAX_REVISIONS:
        return "assembler"
    return "planner"


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_workflow() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("block_executor", block_executor_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("assembler", assembler_node)
    workflow.add_node("formatter_error", formatter_error_node)

    workflow.set_entry_point("router")
    workflow.add_edge("router", "planner")
    workflow.add_conditional_edges("planner", after_planner, {
        "block_executor": "block_executor",
        "end": END,
    })
    workflow.add_conditional_edges("block_executor", after_block_executor, {
        "block_executor": "block_executor",
        "reviewer": "reviewer",
    })
    workflow.add_conditional_edges("reviewer", after_reviewer, {
        "assembler": "assembler",
        "planner": "planner",
    })
    workflow.add_edge("assembler", END)
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
