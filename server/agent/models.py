from __future__ import annotations

import json
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class CubeTimeDimension(BaseModel):
    dimension: str
    granularity: Optional[str] = None
    dateRange: Optional[Union[str, List[str]]] = None  # noqa: N815


class CubeFilter(BaseModel):
    member: str
    operator: str
    values: Optional[List[str]] = None


class CubeQuery(BaseModel):
    measures: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    timeDimensions: List[CubeTimeDimension] = Field(default_factory=list)  # noqa: N815
    filters: List[CubeFilter] = Field(default_factory=list)
    order: Optional[dict] = None
    limit: Optional[int] = None

    def to_cube_api_payload(self) -> dict:
        payload: dict = {}
        if self.measures:
            payload["measures"] = self.measures
        if self.dimensions:
            payload["dimensions"] = self.dimensions
        if self.timeDimensions:
            payload["timeDimensions"] = [td.model_dump(exclude_none=True) for td in self.timeDimensions]
        if self.filters:
            payload["filters"] = [f.model_dump(exclude_none=True) for f in self.filters]
        if self.order:
            payload["order"] = self.order
        if self.limit:
            payload["limit"] = self.limit
        return payload


# ---------------------------------------------------------------------------
# Report block types (discriminated union)
# ---------------------------------------------------------------------------

class ThoughtBlock(BaseModel):
    type: Literal["thought"] = "thought"
    content: str


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    content: str


class LineChartBlock(BaseModel):
    type: Literal["chart_line"] = "chart_line"
    title: str
    x_axis_key: str
    y_axis_key: str
    cube_query: CubeQuery
    data: Optional[List[dict]] = None


class BarChartBlock(BaseModel):
    type: Literal["chart_bar"] = "chart_bar"
    title: str
    category_key: str
    value_key: str
    cube_query: CubeQuery
    data: Optional[List[dict]] = None


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str
    columns: List[str]
    cube_query: CubeQuery
    data: Optional[List[dict]] = None


AnalyticsBlock = Annotated[
    Union[ThoughtBlock, TextBlock, LineChartBlock, BarChartBlock, TableBlock],
    Field(discriminator="type"),
]


class AnalyticsReport(BaseModel):
    report_id: str
    summary_title: str
    blocks: List[AnalyticsBlock] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Planner models (plan-execute-review architecture)
# ---------------------------------------------------------------------------

class QuerySpec(BaseModel):
    """Pure query parameters for a Cube.js request."""
    measures: List[str]
    dimensions: List[str] = Field(default_factory=list)
    time_dimensions: Optional[List[CubeTimeDimension]] = None
    filters: Optional[List[CubeFilter]] = None
    order: Optional[dict[str, str]] = None
    limit: Optional[int] = None

    @field_validator("limit", mode="before")
    @classmethod
    def coerce_zero_limit(cls, v):
        return v if v else None

    @field_validator("filters", mode="before")
    @classmethod
    def coerce_empty_filters(cls, v):
        return v if v else None

    @field_validator("order", mode="before")
    @classmethod
    def coerce_empty_order(cls, v):
        return v if v else None


# ---------------------------------------------------------------------------
# Typed block specs (discriminated union for planner output)
# ---------------------------------------------------------------------------

class TextBlockSpec(BaseModel):
    type: Literal["text"] = "text"
    text_guidance: Optional[str] = None


class LineChartBlockSpec(BaseModel):
    type: Literal["chart_line"] = "chart_line"
    title: str
    x_axis_key: str
    y_axis_key: str
    query: QuerySpec


class BarChartBlockSpec(BaseModel):
    type: Literal["chart_bar"] = "chart_bar"
    title: str
    category_key: str
    value_key: str
    query: QuerySpec


class TableBlockSpec(BaseModel):
    type: Literal["table"] = "table"
    title: str
    columns: List[str]
    query: QuerySpec


BlockSpec = Annotated[
    Union[TextBlockSpec, LineChartBlockSpec, BarChartBlockSpec, TableBlockSpec],
    Field(discriminator="type"),
]


class BlockPlan(BaseModel):
    """A single planned block in the report."""
    block_id: str  # e.g. "block_1"
    purpose: str   # Why this block exists, what insight it conveys
    spec: BlockSpec


class ReportPlan(BaseModel):
    """The planner's structured output — the full report blueprint."""
    domain: Literal["marketing", "sales"]
    summary_title: str
    narrative_strategy: str  # How the blocks build on each other
    blocks: List[BlockPlan]
    conversational_response: bool = False  # True when answering from conversation history


# ---------------------------------------------------------------------------
# LLM-facing plan models (extend BlockSpec, adding planning metadata)
# ---------------------------------------------------------------------------

class LLMTextBlockPlan(TextBlockSpec):
    """LLM plan output for a text block."""
    type: Literal["text"]  # no default → required in schema
    block_id: str
    purpose: str

    def to_block_plan(self) -> BlockPlan:
        return BlockPlan(
            block_id=self.block_id,
            purpose=self.purpose,
            spec=TextBlockSpec(text_guidance=self.text_guidance),
        )


class LLMLineChartBlockPlan(LineChartBlockSpec):
    """LLM plan output for a line chart block."""
    type: Literal["chart_line"]  # no default → required in schema
    block_id: str
    purpose: str

    def to_block_plan(self) -> BlockPlan:
        return BlockPlan(
            block_id=self.block_id,
            purpose=self.purpose,
            spec=LineChartBlockSpec(
                title=self.title, x_axis_key=self.x_axis_key,
                y_axis_key=self.y_axis_key, query=self.query,
            ),
        )


class LLMBarChartBlockPlan(BarChartBlockSpec):
    """LLM plan output for a bar chart block."""
    type: Literal["chart_bar"]  # no default → required in schema
    block_id: str
    purpose: str

    def to_block_plan(self) -> BlockPlan:
        return BlockPlan(
            block_id=self.block_id,
            purpose=self.purpose,
            spec=BarChartBlockSpec(
                title=self.title, category_key=self.category_key,
                value_key=self.value_key, query=self.query,
            ),
        )


class LLMTableBlockPlan(TableBlockSpec):
    """LLM plan output for a table block."""
    type: Literal["table"]  # no default → required in schema
    block_id: str
    purpose: str

    def to_block_plan(self) -> BlockPlan:
        return BlockPlan(
            block_id=self.block_id,
            purpose=self.purpose,
            spec=TableBlockSpec(
                title=self.title, columns=self.columns, query=self.query,
            ),
        )


LLMBlockPlan = Annotated[
    Union[LLMTextBlockPlan, LLMLineChartBlockPlan, LLMBarChartBlockPlan, LLMTableBlockPlan],
    Field(discriminator="type"),
]


class LLMReportPlan(BaseModel):
    """Report plan for LLM structured output. Converted to typed ReportPlan after parsing."""
    domain: Literal["marketing", "sales"]
    summary_title: str
    narrative_strategy: str
    blocks: List[LLMBlockPlan]
    conversational_response: bool = False


def llm_plan_to_report_plan(raw: LLMReportPlan) -> ReportPlan:
    """Convert LLM output to typed ReportPlan with discriminated BlockSpecs."""
    return ReportPlan(
        domain=raw.domain,
        summary_title=raw.summary_title,
        narrative_strategy=raw.narrative_strategy,
        blocks=[b.to_block_plan() for b in raw.blocks],
        conversational_response=raw.conversational_response,
    )


class ExecutedBlock(BaseModel):
    """A block after execution — query ran, data attached."""
    block_id: str
    block_plan: BlockPlan
    cube_query: Optional[CubeQuery] = None
    data: Optional[List[dict]] = None
    error: Optional[str] = None
    text_content: Optional[str] = None  # For text blocks


class ReviewResult(BaseModel):
    """The reviewer's quality assessment."""
    quality_score: int = Field(ge=1, le=5)
    issues: List[str] = Field(default_factory=list)
    revision_instructions: Optional[str] = None
    approved: bool


def render_report_as_text(report: AnalyticsReport) -> str:
    """Convert an AnalyticsReport into a plain-text (markdown) representation."""
    parts: List[str] = []

    parts.append(f"# {report.summary_title}\n")

    for block in report.blocks:
        if isinstance(block, ThoughtBlock):
            parts.append(f"> **Thought:** {block.content}\n")
        elif isinstance(block, TextBlock):
            parts.append(f"{block.content}\n")
        elif isinstance(block, LineChartBlock):
            query_json = json.dumps(block.cube_query.to_cube_api_payload())
            parts.append(
                "---\n\n"
                f"LineChartBlock(\n"
                f"  title: \"{block.title}\"\n"
                f"  x_axis_key: \"{block.x_axis_key}\"\n"
                f"  y_axis_key: \"{block.y_axis_key}\"\n"
                f"  cube_query: {query_json}\n"
                f")\n"
            )
        elif isinstance(block, BarChartBlock):
            query_json = json.dumps(block.cube_query.to_cube_api_payload())
            parts.append(
                "---\n\n"
                f"BarChartBlock(\n"
                f"  title: \"{block.title}\"\n"
                f"  category_key: \"{block.category_key}\"\n"
                f"  value_key: \"{block.value_key}\"\n"
                f"  cube_query: {query_json}\n"
                f")\n"
            )
        elif isinstance(block, TableBlock):
            query_json = json.dumps(block.cube_query.to_cube_api_payload())
            parts.append(
                "---\n\n"
                f"TableBlock(\n"
                f"  title: \"{block.title}\"\n"
                f"  columns: {json.dumps(block.columns)}\n"
                f"  cube_query: {query_json}\n"
                f")\n"
            )

    return "\n".join(parts)
