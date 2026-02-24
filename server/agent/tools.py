from __future__ import annotations

import logging
from typing import List, Optional

from langchain_core.tools import tool

from .models import CubeFilter, CubeQuery, CubeTimeDimension

logger = logging.getLogger(__name__)


@tool
def cube_builder_tool(
    measures: List[str],
    dimensions: Optional[List[str]] = None,
    time_dimensions: Optional[List[dict]] = None,
    filters: Optional[List[dict]] = None,
    order: Optional[dict] = None,
    limit: Optional[int] = None,
) -> dict:
    """Build and validate a CubeJS query.

    Args:
        measures: List of measure member names, e.g. ["fact_daily_ads.impressions"].
        dimensions: List of dimension member names, e.g. ["fact_daily_ads.source"].
        time_dimensions: List of time dimension dicts. Required key: dimension. Optional keys: granularity, dateRange.
            Omit granularity for date filtering without time grouping (totals/rankings within a period).
            Include granularity for trend-over-time queries.
            Example (trend): [{"dimension": "fact_daily_ads.date", "granularity": "month", "dateRange": "Last 6 months"}]
            Example (filter only): [{"dimension": "fact_sales_items.line_timestamp", "dateRange": "Last 30 days"}]
        filters: List of filter dicts with keys: member, operator, values.
            Example: [{"member": "fact_daily_ads.source", "operator": "equals", "values": ["google_ads"]}]
        order: Dict mapping member names to sort direction.
            Example: {"fact_daily_ads.impressions": "desc"}
        limit: Maximum number of rows to return.

    Returns:
        A dict with "status" and "query" on success, or "status" and "message" on error.
    """
    try:
        td_models = (
            [CubeTimeDimension(**td) for td in time_dimensions]
            if time_dimensions
            else []
        )
        filter_models = (
            [CubeFilter(**f) for f in filters]
            if filters
            else []
        )
        query = CubeQuery(
            measures=measures,
            dimensions=dimensions or [],
            timeDimensions=td_models,
            filters=filter_models,
            order=order,
            limit=limit,
        )
        logger.info("CubeQuery built by tool:\n%s", query.model_dump_json(indent=2))
        return {"status": "ok", "query": query.to_cube_api_payload()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
