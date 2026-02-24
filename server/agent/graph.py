from __future__ import annotations

import json
import os
from typing import Annotated, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from . import cube_client
from .models import CubeQuery
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
    streamed_text: str


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
            "You are a routing agent. Given the user's question, respond with ONLY "
            "one word: either 'marketing' or 'sales'.\n\n"
            "Marketing topics: ads, campaigns, impressions, clicks, CTR, CPC, CPM, "
            "ROAS, CPA, attribution, email performance, ad spend, channel revenue.\n\n"
            "Sales topics: orders, revenue, products, customers, gross profit, margins, "
            "discounts, returns, shipping, AOV, SKUs, variants, stores.\n\n"
            "If unsure, default to 'marketing'."
        )
    )
    # Get the last user message
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    last_msg = user_messages[-1] if user_messages else HumanMessage(content="")

    response = await llm.ainvoke([system, last_msg])
    domain = response.content.strip().lower()
    if domain not in SPECIALISTS:
        domain = "marketing"

    return {
        "specialist_domain": domain,
        "cube_query": None,
        "cube_result": None,
        "cube_error": None,
        "retry_count": 0,
    }


async def specialist_node(state: AgentState) -> dict:
    """Use the specialist LLM + tool to build a CubeQuery."""
    config = SPECIALISTS[state["specialist_domain"]]
    llm = _get_llm()
    llm_with_tools = llm.bind_tools([cube_builder_tool])

    system_parts = [
        config.system_instructions,
        "\n\n",
        config.cube_meta_context,
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
        else:
            return {
                "cube_error": tool_result.get("message", "Tool validation failed"),
                "retry_count": state.get("retry_count", 0) + 1,
            }

    if cube_query is None:
        # LLM didn't call the tool – use text response directly
        return {"streamed_text": response.content, "cube_query": None}

    return {"cube_query": cube_query}


async def data_validator_node(state: AgentState) -> dict:
    """Execute the CubeQuery against CubeJS."""
    raw_query = state.get("cube_query")
    if not raw_query:
        return {"cube_error": "No query to execute", "retry_count": state.get("retry_count", 0) + 1}

    try:
        query = CubeQuery(**raw_query) if isinstance(raw_query, dict) else raw_query
        result = await cube_client.execute_cube_query(query)
        return {"cube_result": result, "cube_error": None}
    except Exception as exc:
        return {
            "cube_error": str(exc),
            "retry_count": state.get("retry_count", 0) + 1,
        }


async def formatter_node(state: AgentState) -> dict:
    """Generate a narrative summary from the query results."""
    llm = _get_llm()
    cube_result = state.get("cube_result", {})
    data = cube_result.get("data", [])
    preview = data[:20]

    cube_query = state.get("cube_query", {})
    system = SystemMessage(
        content=(
            "You are an analytics report writer. Given CubeJS query results, write a "
            "clear, concise markdown narrative with key findings. Include specific numbers. "
            "Do NOT wrap your response in code blocks. Just write the analysis directly."
        )
    )
    user_msg = HumanMessage(
        content=(
            f"Query: {json.dumps(cube_query)}\n\n"
            f"Results ({len(data)} rows, showing first {len(preview)}):\n"
            f"{json.dumps(preview, indent=2)}"
        )
    )

    response = await llm.ainvoke([system, user_msg])
    return {"streamed_text": response.content}


async def formatter_error_node(state: AgentState) -> dict:
    """Generate a user-friendly error message after retries are exhausted."""
    cube_error = state.get("cube_error", "Unknown error")
    return {
        "streamed_text": (
            "I wasn't able to retrieve the data for your question. "
            f"The query failed after multiple attempts.\n\n**Error:** {cube_error}\n\n"
            "This could be due to an invalid metric or dimension name. "
            "Could you try rephrasing your question?"
        )
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


_memory = MemorySaver()


def get_graph():
    """Build and compile the graph with in-memory checkpointer for multi-turn."""
    workflow = build_workflow()
    return workflow.compile(checkpointer=_memory)
