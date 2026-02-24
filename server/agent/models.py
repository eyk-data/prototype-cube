from __future__ import annotations

import json
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field


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
        if self.order is not None:
            payload["order"] = self.order
        if self.limit is not None:
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

class BlockQuerySpec(BaseModel):
    """Query parameters for a single data block. The planner fills these out using cube metadata."""
    measures: List[str]
    dimensions: List[str] = Field(default_factory=list)
    time_dimensions: Optional[List[dict]] = None
    filters: Optional[List[dict]] = None
    order: Optional[dict] = None
    limit: Optional[int] = None
    # Visualization config
    title: str
    x_or_category_key: Optional[str] = None  # For charts: the x-axis / category key
    y_or_value_key: Optional[str] = None      # For charts: the y-axis / value key
    columns: Optional[List[str]] = None       # For tables: which columns to display


class BlockPlan(BaseModel):
    """A single planned block in the report."""
    block_id: str  # e.g. "block_1"
    block_type: Literal["text", "chart_line", "chart_bar", "table"]
    purpose: str   # Why this block exists, what insight it conveys
    query_spec: Optional[BlockQuerySpec] = None  # None for text blocks
    text_guidance: Optional[str] = None          # For text blocks: what to write about


class ReportPlan(BaseModel):
    """The planner's structured output — the full report blueprint."""
    summary_title: str
    narrative_strategy: str  # How the blocks build on each other
    blocks: List[BlockPlan]
    conversational_response: bool = False  # True when answering from conversation history


class ExecutedBlock(BaseModel):
    """A block after execution — query ran, data attached."""
    block_id: str
    block_plan: BlockPlan
    cube_query: Optional[dict] = None
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
