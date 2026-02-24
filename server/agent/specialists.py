from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SpecialistConfig:
    domain: str
    system_instructions: str
    cube_meta_context: Optional[str] = None


MARKETING_SPECIALIST = SpecialistConfig(
    domain="marketing",
    system_instructions=(
        "You are a Marketing Analytics specialist. You help users understand their "
        "advertising performance, attribution, email campaigns, and marketing ROI. "
        "Always use the cube_builder_tool to construct a valid CubeJS query before "
        "answering. Use exact cube member names from the metadata below."
    ),
)


SALES_SPECIALIST = SpecialistConfig(
    domain="sales",
    system_instructions=(
        "You are a Sales Analytics specialist. You help users understand their "
        "sales performance, product metrics, customer data, and profitability. "
        "Always use the cube_builder_tool to construct a valid CubeJS query before "
        "answering. Use exact cube member names from the metadata below."
    ),
)


SPECIALISTS = {
    "marketing": MARKETING_SPECIALIST,
    "sales": SALES_SPECIALIST,
}
