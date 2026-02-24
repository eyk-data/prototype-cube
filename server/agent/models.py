from __future__ import annotations

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
