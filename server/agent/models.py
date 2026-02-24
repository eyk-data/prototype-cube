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


class BarChartBlock(BaseModel):
    type: Literal["chart_bar"] = "chart_bar"
    title: str
    category_key: str
    value_key: str
    cube_query: CubeQuery


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str
    columns: List[str]
    cube_query: CubeQuery


AnalyticsBlock = Annotated[
    Union[ThoughtBlock, TextBlock, LineChartBlock, BarChartBlock, TableBlock],
    Field(discriminator="type"),
]


class AnalyticsReport(BaseModel):
    report_id: str
    summary_title: str
    blocks: List[AnalyticsBlock] = Field(default_factory=list)


class FormatterDecision(BaseModel):
    """LLM output: how to present the query results."""
    summary_title: str
    narrative: str
    table_title: str
    table_columns: List[str]
    chart_type: Optional[Literal["line", "bar"]] = None
    chart_title: Optional[str] = None
    chart_x_or_category: Optional[str] = None
    chart_y_or_value: Optional[str] = None


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
