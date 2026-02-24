from __future__ import annotations

from typing import List, Optional

from langchain_core.tools import tool

from .models import CubeFilter, CubeQuery, CubeTimeDimension


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
        time_dimensions: List of time dimension dicts with keys: dimension, granularity, dateRange.
            Example: [{"dimension": "fact_daily_ads.date", "granularity": "month", "dateRange": "Last 6 months"}]
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
        return {"status": "ok", "query": query.to_cube_api_payload()}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
