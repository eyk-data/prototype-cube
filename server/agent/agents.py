"""Pydantic-AI agent singletons for the analytics workflow."""
from __future__ import annotations

import os

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from .deps import AgentDeps
from .models import LLMReportPlan, QuerySpec, ReviewResult


def _get_model() -> GoogleModel:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("VERTEX_AI_API_KEY", "")

    if api_key and api_key.startswith("AIza"):
        provider = GoogleProvider(api_key=api_key)
        return GoogleModel("gemini-2.0-flash", provider=provider)

    # Vertex AI with service account or ADC
    project = os.environ.get("CUBEJS_DB_BQ_PROJECT_ID", "")
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")

    kwargs: dict = {}
    if project:
        kwargs["project"] = project
    if creds_path:
        from google.oauth2 import service_account
        kwargs["credentials"] = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )

    provider = GoogleProvider(vertexai=True, **kwargs)
    return GoogleModel("gemini-2.0-flash", provider=provider)


def _make_agent(output_type):
    """Create an agent with dynamic instructions from deps."""
    agent = Agent(_get_model(), output_type=output_type, deps_type=AgentDeps)

    @agent.instructions
    def dynamic_instructions(ctx: RunContext[AgentDeps]) -> str:
        return ctx.deps.system_prompt

    return agent


# Lazy singletons — avoids import-time env var reads
_planner_agent: Agent | None = None
_reviewer_agent: Agent | None = None
_query_corrector_agent: Agent | None = None
_text_gen_agent: Agent | None = None


def get_planner_agent() -> Agent:
    global _planner_agent
    if _planner_agent is None:
        _planner_agent = _make_agent(LLMReportPlan)
    return _planner_agent


def get_reviewer_agent() -> Agent:
    global _reviewer_agent
    if _reviewer_agent is None:
        _reviewer_agent = _make_agent(ReviewResult)
    return _reviewer_agent


def get_query_corrector_agent() -> Agent:
    global _query_corrector_agent
    if _query_corrector_agent is None:
        _query_corrector_agent = _make_agent(QuerySpec)
    return _query_corrector_agent


def get_text_gen_agent() -> Agent:
    global _text_gen_agent
    if _text_gen_agent is None:
        _text_gen_agent = _make_agent(str)
    return _text_gen_agent
