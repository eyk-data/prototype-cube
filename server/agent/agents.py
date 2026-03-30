"""Pydantic-AI agent instances for the analytics workflow."""
from __future__ import annotations

import os

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from .deps import AgentDeps
from .models import (
    LLMReportPlan,
    QuerySpec,
    ReportPlan,
    ReviewResult,
    TextBlockSpec,
    llm_plan_to_report_plan,
)
from .prompts import (
    PLANNER_IDENTITY,
    QUERY_CORRECTOR_IDENTITY,
    REVIEWER_IDENTITY,
    TEXT_GEN_IDENTITY,
)


def get_model() -> GoogleModel:
    """Build the Google/Vertex AI model at runtime (avoids import-time env var reads)."""
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


# ---------------------------------------------------------------------------
# Planner agent
# ---------------------------------------------------------------------------

planner_agent: Agent[AgentDeps, LLMReportPlan] = Agent(
    model=None,
    output_type=LLMReportPlan,
    deps_type=AgentDeps,
    instructions=PLANNER_IDENTITY,
    output_retries=2,
    name="planner",
)


@planner_agent.instructions
def planner_cube_meta(ctx: RunContext[AgentDeps]) -> str:
    """Inject cube metadata as dynamic instructions."""
    return f"## Cube Metadata\n{ctx.deps.cube_meta_context}"


def _check_member_names(plan: ReportPlan, valid: set[str]) -> list[str]:
    """Check all member names in a ReportPlan against valid cube members."""
    errors: list[str] = []
    for block in plan.blocks:
        spec = block.spec
        if isinstance(spec, TextBlockSpec):
            continue
        query = spec.query
        prefix = f"Block {block.block_id}"
        for m in query.measures:
            if m not in valid:
                errors.append(f"{prefix}: invalid measure '{m}'")
        for d in query.dimensions:
            if d not in valid:
                errors.append(f"{prefix}: invalid dimension '{d}'")
        if query.time_dimensions:
            for td in query.time_dimensions:
                dim = td.dimension
                if dim and dim not in valid:
                    errors.append(f"{prefix}: invalid time dimension '{dim}'")
        if query.filters:
            for f in query.filters:
                member = f.member
                if member and member not in valid:
                    errors.append(f"{prefix}: invalid filter member '{member}'")
        if query.order:
            for key in query.order:
                base_key = ".".join(key.split(".")[:2]) if key.count(".") >= 2 else key
                if base_key not in valid:
                    errors.append(f"{prefix}: invalid order key '{key}'")
    return errors


@planner_agent.output_validator
def validate_plan_members(ctx: RunContext[AgentDeps], output: LLMReportPlan) -> LLMReportPlan:
    """Validate member names in the plan; raises ModelRetry for self-correction."""
    valid = ctx.deps.valid_members
    if valid is None:
        return output
    errors = _check_member_names(llm_plan_to_report_plan(output), valid)
    if errors:
        raise ModelRetry(
            "Invalid member names:\n" + "\n".join(f"- {e}" for e in errors)
            + "\n\nUse ONLY member names from the Cube Metadata section above."
        )
    return output


# ---------------------------------------------------------------------------
# Reviewer agent (no deps needed — all context in user prompt)
# ---------------------------------------------------------------------------

reviewer_agent: Agent[None, ReviewResult] = Agent(
    model=None,
    output_type=ReviewResult,
    instructions=REVIEWER_IDENTITY,
    name="reviewer",
)

# ---------------------------------------------------------------------------
# Text generation agent (no deps needed)
# ---------------------------------------------------------------------------

text_gen_agent: Agent[None, str] = Agent(
    model=None,
    output_type=str,
    instructions=TEXT_GEN_IDENTITY,
    name="text_gen",
)

# ---------------------------------------------------------------------------
# Query corrector agent
# ---------------------------------------------------------------------------

query_corrector_agent: Agent[AgentDeps, QuerySpec] = Agent(
    model=None,
    output_type=QuerySpec,
    deps_type=AgentDeps,
    instructions=QUERY_CORRECTOR_IDENTITY,
    name="query_corrector",
)


@query_corrector_agent.instructions
def corrector_cube_meta(ctx: RunContext[AgentDeps]) -> str:
    """Inject cube metadata for query correction."""
    return f"## Cube Metadata\n{ctx.deps.cube_meta_context}"
