"""Analytics workflow orchestrator using plain async functions.

Replaces the pydantic-graph node/state/graph pattern with a single async
generator that yields thoughts and produces an AnalyticsReport.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import AsyncGenerator

import httpx

from . import cube_client
from .agents import (
    get_planner_agent,
    get_query_corrector_agent,
    get_reviewer_agent,
    get_text_gen_agent,
)
from .cube_meta import get_cube_meta_context, get_valid_member_names
from .deps import AgentDeps
from .models import (
    AnalyticsReport,
    BarChartBlock,
    BarChartBlockSpec,
    BlockPlan,
    CubeQuery,
    ExecutedBlock,
    LineChartBlock,
    LineChartBlockSpec,
    QuerySpec,
    ReportPlan,
    ReviewResult,
    TableBlock,
    TableBlockSpec,
    TextBlock,
    TextBlockSpec,
    ThoughtBlock,
    llm_plan_to_report_plan,
    render_report_as_text,
)
from .prompts import build_planner_system_prompt

logger = logging.getLogger(__name__)

MAX_REVISIONS = 2
MAX_BLOCK_RETRIES = 2
TRANSIENT_RETRY_DELAY = 1.0


# ---------------------------------------------------------------------------
# Helpers (kept verbatim from nodes.py)
# ---------------------------------------------------------------------------


def _build_cube_query(spec: QuerySpec) -> CubeQuery | None:
    """Convert a QuerySpec into a validated CubeQuery, or None on error."""
    try:
        query = CubeQuery(
            measures=spec.measures,
            dimensions=spec.dimensions,
            timeDimensions=spec.time_dimensions or [],
            filters=spec.filters or [],
            order=spec.order,
            limit=spec.limit,
        )
        logger.info("CubeQuery built:\n%s", query.model_dump_json(indent=2))
        return query
    except Exception as exc:
        logger.warning("CubeQuery build failed: %s", exc)
        return None


def _validate_plan_members(plan: ReportPlan, valid_members: set[str]) -> list[str]:
    """Check all member names in a ReportPlan against valid cube members."""
    errors: list[str] = []
    for block in plan.blocks:
        spec = block.spec
        if isinstance(spec, TextBlockSpec):
            continue
        query = spec.query
        prefix = f"Block {block.block_id}"
        for m in query.measures:
            if m not in valid_members:
                errors.append(f"{prefix}: invalid measure '{m}'")
        for d in query.dimensions:
            if d not in valid_members:
                errors.append(f"{prefix}: invalid dimension '{d}'")
        if query.time_dimensions:
            for td in query.time_dimensions:
                dim = td.dimension
                if dim and dim not in valid_members:
                    errors.append(f"{prefix}: invalid time dimension '{dim}'")
        if query.filters:
            for f in query.filters:
                member = f.member
                if member and member not in valid_members:
                    errors.append(f"{prefix}: invalid filter member '{member}'")
        if query.order:
            for key in query.order:
                base_key = ".".join(key.split(".")[:2]) if key.count(".") >= 2 else key
                if base_key not in valid_members:
                    errors.append(f"{prefix}: invalid order key '{key}'")
    return errors


def _is_transient_error(exc: Exception) -> bool:
    """Return True for transient errors that may succeed on retry."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
        return True
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
        return True
    return False


def _make_early_exit_report(
    title: str,
    text: str,
    thoughts: list[str],
) -> AnalyticsReport:
    """Build an AnalyticsReport for early-exit paths (error fallback, text-only)."""
    return AnalyticsReport(
        report_id=str(uuid.uuid4()),
        summary_title=title,
        blocks=[
            *[ThoughtBlock(content=t) for t in thoughts],
            TextBlock(content=text),
        ],
    )


async def _llm_correct_query(
    block_plan: BlockPlan,
    failed_query: CubeQuery,
    error_msg: str,
    deps: AgentDeps,
) -> QuerySpec | None:
    """Ask the LLM to fix a failed Cube query."""
    correction_prompt = (
        "A Cube query failed. Fix the query based on the error and metadata.\n\n"
        f"Block purpose: {block_plan.purpose}\n"
        f"Block type: {block_plan.spec.type}\n\n"
        f"Failed query:\n{failed_query.model_dump_json(indent=2)}\n\n"
        f"Error:\n{error_msg}\n\n"
        f"Cube metadata:\n{deps.cube_meta_context}\n\n"
        "Return a corrected QuerySpec. Use only valid member names from the metadata."
    )
    try:
        correction_deps = AgentDeps(
            dataset=deps.dataset,
            cube_meta_context=deps.cube_meta_context,
            valid_members=deps.valid_members,
            system_prompt="You are a Cube query correction assistant. Fix the failed query.",
        )
        result = await get_query_corrector_agent().run(
            correction_prompt, deps=correction_deps,
        )
        return result.output
    except Exception as exc:
        logger.warning("LLM query correction failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Pre-fetch (moved from workflow.py)
# ---------------------------------------------------------------------------


async def prefetch_deps() -> AgentDeps:
    """Pre-fetch cube metadata and build AgentDeps."""
    dataset = os.environ.get("CUBEJS_BQ_DATASET", "")
    cube_meta_context = await get_cube_meta_context()
    valid_members = await get_valid_member_names()
    return AgentDeps(
        dataset=dataset,
        cube_meta_context=cube_meta_context,
        valid_members=valid_members,
    )


# ---------------------------------------------------------------------------
# Orchestrator — async generator
# ---------------------------------------------------------------------------


async def run_analytics(
    user_question: str,
    conversation_history: str = "",
) -> AsyncGenerator[tuple[str, str | AnalyticsReport], None]:
    """Run the full analytics workflow as an async generator.

    Yields tuples of:
        ("thought", text)           — progress updates
        ("report", AnalyticsReport) — the final report (always last)
    """
    deps = await prefetch_deps()

    # Local variables replacing AgentState
    thought_log: list[str] = []
    review_result: ReviewResult | None = None
    revision_count = 0

    for _revision_round in range(1 + MAX_REVISIONS):
        # Fresh per-round state
        executed_blocks: list[ExecutedBlock] = []
        block_errors: list[str] = []

        # -----------------------------------------------------------
        # PLANNER PHASE
        # -----------------------------------------------------------
        is_revision = (
            review_result is not None
            and not review_result.approved
            and 0 < revision_count < MAX_REVISIONS
        )

        revision_feedback = review_result.model_dump() if review_result else None
        system_content = build_planner_system_prompt(
            cube_meta=deps.cube_meta_context,
            history=conversation_history,
            revision_feedback=revision_feedback if revision_feedback else None,
        )

        planner_deps = AgentDeps(
            dataset=deps.dataset,
            cube_meta_context=deps.cube_meta_context,
            valid_members=deps.valid_members,
            system_prompt=system_content,
        )

        user_prompt = user_question
        if conversation_history:
            user_prompt = f"Conversation history:\n{conversation_history}\n\nUser question: {user_question}"

        try:
            result = await get_planner_agent().run(user_prompt, deps=planner_deps)
            raw_plan = result.output
            plan = llm_plan_to_report_plan(raw_plan)

            # Validate member names
            if deps.valid_members is not None:
                member_errors = _validate_plan_members(plan, deps.valid_members)
                if member_errors:
                    logger.warning("Plan has invalid member names: %s", member_errors)
                    validation_msg = (
                        "\n\n## Member Name Validation Errors\n"
                        "Your previous plan used invalid cube member names. Fix these:\n"
                        + "\n".join(f"- {e}" for e in member_errors)
                        + "\n\nUse ONLY member names from the Cube Metadata section above."
                    )
                    retry_deps = AgentDeps(
                        dataset=deps.dataset,
                        cube_meta_context=deps.cube_meta_context,
                        valid_members=deps.valid_members,
                        system_prompt=system_content + validation_msg,
                    )
                    retry_result = await get_planner_agent().run(user_prompt, deps=retry_deps)
                    raw_plan = retry_result.output
                    plan = llm_plan_to_report_plan(raw_plan)
                    retry_errors = _validate_plan_members(plan, deps.valid_members)
                    if retry_errors:
                        logger.warning("Plan still has invalid members after retry: %s", retry_errors)

        except Exception as exc:
            logger.warning("Planner structured output failed: %s", exc)
            report = _make_early_exit_report(
                title="Response",
                text="I wasn't able to plan a report for this question. Could you try rephrasing?",
                thoughts=thought_log,
            )
            yield ("report", report)
            return

        # Reorder: data blocks first, text blocks last
        data_blocks = [b for b in plan.blocks if not isinstance(b.spec, TextBlockSpec)]
        text_blocks = [b for b in plan.blocks if isinstance(b.spec, TextBlockSpec)]
        plan.blocks = data_blocks + text_blocks

        logger.info("ReportPlan:\n%s", plan.model_dump_json(indent=2))

        routing_thought = f"Routing to {plan.domain} analytics specialist."

        has_data_blocks = any(not isinstance(b.spec, TextBlockSpec) for b in plan.blocks)

        if not has_data_blocks:
            # Pure text response — no queries needed
            text_parts = []
            for block in plan.blocks:
                if isinstance(block.spec, TextBlockSpec) and block.spec.text_guidance:
                    text_parts.append(block.spec.text_guidance)
            raw_guidance = " ".join(text_parts) if text_parts else plan.narrative_strategy

            if plan.conversational_response:
                combined_text = raw_guidance
            else:
                gen_prompt = (
                    f"User's question: {user_question}\n\n"
                    f"Conversation history:\n{conversation_history}\n\n"
                    f"Report guidance: {raw_guidance}\n\n"
                    "Write a clear, concise response that directly answers the user's question. "
                    "Use specific numbers from the conversation history or guidance if available. "
                    "Do not use markdown headers."
                )
                text_deps = AgentDeps(
                    dataset=deps.dataset,
                    cube_meta_context=deps.cube_meta_context,
                    valid_members=deps.valid_members,
                    system_prompt="You are a helpful analytics assistant.",
                )
                text_result = await get_text_gen_agent().run(gen_prompt, deps=text_deps)
                combined_text = text_result.output.strip()

            report = _make_early_exit_report(
                title=plan.summary_title,
                text=combined_text,
                thoughts=thought_log,
            )
            yield ("report", report)
            return

        # Data blocks exist — proceed to execution
        n_blocks = len(plan.blocks)
        planning_thought = f"Planning report: {plan.summary_title} ({n_blocks} blocks)"

        thought_log.extend([routing_thought, planning_thought])
        yield ("thought", routing_thought)
        yield ("thought", planning_thought)

        # -----------------------------------------------------------
        # BLOCK EXECUTOR PHASE
        # -----------------------------------------------------------
        for idx, block_plan in enumerate(plan.blocks):
            if isinstance(block_plan.spec, TextBlockSpec):
                # Generate text using LLM with context from previously executed blocks
                data_context_parts = []
                for eb in executed_blocks:
                    if eb.data:
                        data_context_parts.append(
                            f"Block '{eb.block_plan.purpose}' data preview: "
                            f"{json.dumps(eb.data[:5], default=str)}"
                        )

                data_context = "\n".join(data_context_parts) if data_context_parts else "No data available yet."

                text_prompt = (
                    f"User's question: {user_question}\n\n"
                    f"Conversation history:\n{conversation_history}\n\n"
                    f"Report context: {plan.narrative_strategy}\n\n"
                    f"This text block's purpose: {block_plan.purpose}\n"
                    f"Guidance: {block_plan.spec.text_guidance or 'Write a clear, concise paragraph.'}\n\n"
                    f"Available data from other blocks:\n{data_context}\n\n"
                    "Write a clear, concise paragraph that directly addresses the purpose above. "
                    "Use specific numbers from the data and conversation history if available. "
                    "Do not use markdown headers."
                )

                text_deps = AgentDeps(
                    dataset=deps.dataset,
                    cube_meta_context=deps.cube_meta_context,
                    valid_members=deps.valid_members,
                    system_prompt="You are a helpful analytics assistant writing report text.",
                )
                text_result = await get_text_gen_agent().run(text_prompt, deps=text_deps)
                text_content = text_result.output.strip()

                executed_block = ExecutedBlock(
                    block_id=block_plan.block_id,
                    block_plan=block_plan,
                    text_content=text_content,
                )
                thought = f"Executed block {idx + 1}/{len(plan.blocks)}: text"

            else:
                # Data block — build query, execute with retry
                spec = block_plan.spec
                cube_query = _build_cube_query(spec.query)
                if not cube_query:
                    executed_block = ExecutedBlock(
                        block_id=block_plan.block_id,
                        block_plan=block_plan,
                        error="Query validation failed",
                    )
                    block_errors.append(f"Block {block_plan.block_id}: query validation failed")
                    thought = f"Executed block {idx + 1}/{len(plan.blocks)}: {spec.type} (validation error)"
                else:
                    current_query = cube_query
                    last_error: str | None = None
                    data: list[dict] | None = None

                    for attempt in range(1 + MAX_BLOCK_RETRIES):
                        try:
                            logger.info(
                                "Executing block %s query (attempt %d):\n%s",
                                block_plan.block_id, attempt + 1, current_query.model_dump_json(indent=2),
                            )
                            result = await cube_client.execute_cube_query(current_query)
                            data = result.get("data", [])
                            last_error = None
                            break
                        except Exception as exc:
                            last_error = str(exc)
                            logger.warning(
                                "Block %s attempt %d failed: %s",
                                block_plan.block_id, attempt + 1, last_error,
                            )
                            if attempt >= MAX_BLOCK_RETRIES:
                                break
                            if _is_transient_error(exc):
                                await asyncio.sleep(TRANSIENT_RETRY_DELAY * (attempt + 1))
                            else:
                                corrected = await _llm_correct_query(
                                    block_plan, current_query, last_error, deps,
                                )
                                if corrected:
                                    new_query = _build_cube_query(corrected)
                                    if new_query:
                                        current_query = new_query
                                        continue
                                break

                    if last_error:
                        executed_block = ExecutedBlock(
                            block_id=block_plan.block_id,
                            block_plan=block_plan,
                            cube_query=current_query,
                            error=last_error,
                        )
                        block_errors.append(f"Block {block_plan.block_id}: {last_error}")
                        thought = f"Executed block {idx + 1}/{len(plan.blocks)}: {spec.type} (error)"
                    else:
                        executed_block = ExecutedBlock(
                            block_id=block_plan.block_id,
                            block_plan=block_plan,
                            cube_query=current_query,
                            data=data,
                        )
                        thought = f"Executed block {idx + 1}/{len(plan.blocks)}: {spec.type} ({len(data or [])} rows)"

            executed_blocks.append(executed_block)
            thought_log.append(thought)
            yield ("thought", thought)

        # -----------------------------------------------------------
        # REVIEWER PHASE
        # -----------------------------------------------------------
        block_summaries = []
        for eb in executed_blocks:
            parts = [f"- **{eb.block_id}** ({eb.block_plan.spec.type}) — Purpose: {eb.block_plan.purpose}"]
            if eb.error:
                parts.append(f"  ERROR: {eb.error}")
            elif eb.text_content:
                parts.append(f"  Text content: {eb.text_content}")
            elif eb.data is not None:
                parts.append(f"  Rows: {len(eb.data)}")
                if eb.data:
                    preview = json.dumps(eb.data[:5], default=str)
                    parts.append(f"  Data preview (first 5 rows): {preview}")
                if eb.cube_query:
                    parts.append(f"  Query: {eb.cube_query.model_dump_json()}")
            else:
                parts.append("  No data")
            block_summaries.append("\n".join(parts))

        narrative_strategy = plan.narrative_strategy

        review_prompt = (
            "You are a quality reviewer for analytics reports. Evaluate whether the "
            "executed report blocks adequately answer the user's question.\n\n"
            f"User's question: {user_question}\n\n"
            f"Narrative strategy: {narrative_strategy}\n\n"
            "Executed blocks:\n" + "\n".join(block_summaries) + "\n\n"
            "Evaluate on these criteria:\n"
            "1. Relevance: Do the blocks answer the user's question?\n"
            "2. Data accuracy: Are there execution errors?\n"
            "3. Visualization fit: Are the chart types appropriate?\n"
            "4. Completeness: Is anything missing?\n"
            "5. Text quality: Do text blocks provide meaningful insight with specific numbers?\n\n"
            "Reference specific data values from the previews in your assessment. "
            "Score from 1-5 (5 is best). Set approved=true if score >= 4. "
            "If not approved, provide specific revision_instructions for the planner."
        )

        review_deps = AgentDeps(
            dataset=deps.dataset,
            cube_meta_context=deps.cube_meta_context,
            valid_members=deps.valid_members,
            system_prompt="You are a quality reviewer for analytics reports.",
        )

        try:
            review_run = await get_reviewer_agent().run(review_prompt, deps=review_deps)
            review_result = review_run.output
        except Exception as exc:
            logger.warning("Reviewer structured output failed: %s", exc)
            review_result = ReviewResult(quality_score=4, approved=True)

        logger.info("ReviewResult:\n%s", review_result.model_dump_json(indent=2))

        review_thought = f"Review score: {review_result.quality_score}/5 — {'approved' if review_result.approved else 'revision needed'}"
        if not review_result.approved:
            revision_count += 1
        thought_log.append(review_thought)
        yield ("thought", review_thought)

        if review_result.approved or revision_count >= MAX_REVISIONS:
            break
        # else: loop continues for revision

    # -----------------------------------------------------------
    # ASSEMBLER PHASE
    # -----------------------------------------------------------
    blocks: list = []

    for thought in thought_log:
        blocks.append(ThoughtBlock(content=thought))

    # Sort executed blocks by block_id to restore planner's narrative order
    executed_sorted = sorted(executed_blocks, key=lambda eb: eb.block_id)

    for eb in executed_sorted:
        spec = eb.block_plan.spec

        if eb.error:
            continue

        if isinstance(spec, TextBlockSpec):
            if eb.text_content:
                blocks.append(TextBlock(content=eb.text_content))

        elif isinstance(spec, LineChartBlockSpec):
            if eb.data is not None and eb.cube_query:
                blocks.append(LineChartBlock(
                    title=spec.title,
                    x_axis_key=spec.x_axis_key,
                    y_axis_key=spec.y_axis_key,
                    cube_query=eb.cube_query,
                    data=eb.data,
                ))

        elif isinstance(spec, BarChartBlockSpec):
            if eb.data is not None and eb.cube_query:
                blocks.append(BarChartBlock(
                    title=spec.title,
                    category_key=spec.category_key,
                    value_key=spec.value_key,
                    cube_query=eb.cube_query,
                    data=eb.data,
                ))

        elif isinstance(spec, TableBlockSpec):
            if eb.data is not None and eb.cube_query:
                columns = spec.columns or (list(eb.data[0].keys()) if eb.data else [])
                blocks.append(TableBlock(
                    title=spec.title,
                    columns=columns,
                    cube_query=eb.cube_query,
                    data=eb.data,
                ))

    # If all blocks had errors, add an error text
    if not any(isinstance(b, (TextBlock, LineChartBlock, BarChartBlock, TableBlock)) for b in blocks):
        blocks.append(TextBlock(
            content=(
                "I encountered errors while executing the data queries. "
                f"Errors: {'; '.join(block_errors) if block_errors else 'Unknown errors'}\n\n"
                "Could you try rephrasing your question?"
            )
        ))

    report = AnalyticsReport(
        report_id=str(uuid.uuid4()),
        summary_title=plan.summary_title,
        blocks=blocks,
    )
    logger.info("AnalyticsReport:\n%s", report.model_dump_json(indent=2))

    yield ("report", report)


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


async def run_agent(
    question: str,
    conversation_history: str = "",
) -> AnalyticsReport:
    """Run the full analytics workflow and return the final report."""
    async for tag, value in run_analytics(question, conversation_history):
        if tag == "report":
            return value  # type: ignore[return-value]
    raise RuntimeError("run_analytics completed without yielding a report")
