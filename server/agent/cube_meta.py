"""Dynamic Cube model metadata with TTL cache for agent prompts."""
from __future__ import annotations

import logging
import time

from . import cube_client

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_CACHE_TTL = 300  # 5 minutes

_cached_text: str | None = None
_cached_at: float = 0.0

QUERY_FORMAT_INSTRUCTIONS = """\
## Join Relationships
- fact_sales_items → dim_product_variants, dim_customers
- fact_attributions → dim_product_variants, dim_customers, dim_attribution_models, fact_daily_ads
- email_performance has no joins (standalone)

## Query Format
- Time dimensions use: {"dimension": "cube.field", "granularity": "day|week|month|quarter|year", "dateRange": "Last 30 days"}
- Filters use: {"member": "cube.field", "operator": "equals|notEquals|contains|gt|lt|gte|lte|set|notSet|inDateRange", "values": ["..."]}
- Order uses: {"cube.field": "asc|desc"}
- When querying across joined cubes, use measures from the fact table with dimensions from the joined dimension table
- Always prefix member names with the cube name (e.g. fact_sales_items.gross_sales, NOT just gross_sales)
"""

FALLBACK_TEXT = (
    "## Available Cubes & Members\n\n"
    "(Cube metadata is temporarily unavailable. Use your best judgement "
    "based on the user's question.)\n\n"
    + QUERY_FORMAT_INSTRUCTIONS
)

# Map Cube meta API aggType values to the labels used in prompts.
# aggType "number" means a derived/calculated metric (no direct aggregation).
_AGG_TYPE_MAP = {
    "number": "calculated",
    "countDistinct": "count_distinct",
    "runningTotal": "running_total",
}


def _is_visible(member: dict) -> bool:
    return member.get("isVisible", True) and member.get("public", True)


def _format_measure(m: dict) -> str:
    agg = m.get("aggType", m.get("type", ""))
    display_type = _AGG_TYPE_MAP.get(agg, agg)
    return f"{m['name']} ({display_type})"


def _format_dimension(d: dict) -> str:
    return f"{d['name']} ({d.get('type', 'string')})"


def format_cube_meta(meta: dict) -> str:
    """Transform the /meta JSON response into prompt-friendly text."""
    lines = ["## Available Cubes & Members\n"]
    cubes = meta.get("cubes", [])

    for cube in cubes:
        name = cube.get("name", "")
        title = cube.get("title", name)
        lines.append(f"### {name} ({title})")

        measures = [m for m in cube.get("measures", []) if _is_visible(m)]
        if measures:
            formatted = ", ".join(_format_measure(m) for m in measures)
            lines.append(f"Measures: {formatted}")

        dimensions = [d for d in cube.get("dimensions", []) if _is_visible(d)]
        if dimensions:
            formatted = ", ".join(_format_dimension(d) for d in dimensions)
            lines.append(f"Dimensions: {formatted}")

        lines.append("")  # blank line between cubes

    return "\n".join(lines)


async def get_cube_meta_context() -> str:
    """Return formatted cube metadata, using a 5-minute TTL cache.

    On fetch failure, returns stale cache if available, otherwise a fallback string.
    """
    global _cached_text, _cached_at

    now = time.monotonic()
    if _cached_text is not None and (now - _cached_at) < _CACHE_TTL:
        return _cached_text

    try:
        meta = await cube_client.fetch_cube_meta()
        _cached_text = format_cube_meta(meta) + "\n" + QUERY_FORMAT_INSTRUCTIONS
        _cached_at = now
        logger.info("Cube meta cache refreshed")
        return _cached_text
    except Exception:
        logger.warning("Failed to fetch Cube metadata", exc_info=True)
        if _cached_text is not None:
            logger.info("Serving stale Cube meta cache")
            return _cached_text
        return FALLBACK_TEXT
