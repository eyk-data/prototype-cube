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
        "You are a Marketing Analytics specialist. Your expertise covers "
        "advertising performance, attribution, email campaigns, and marketing ROI. "
        "You know which cube members are relevant for marketing questions and how "
        "to construct meaningful queries that reveal marketing insights. "
        "Use exact cube member names from the metadata. "
        "Pay close attention to the Query Construction Rules for when to include or omit granularity in time dimensions."
    ),
)


SALES_SPECIALIST = SpecialistConfig(
    domain="sales",
    system_instructions=(
        "You are a Sales Analytics specialist. Your expertise covers "
        "sales performance, product metrics, customer data, and profitability. "
        "You know which cube members are relevant for sales questions and how "
        "to construct meaningful queries that reveal sales insights. "
        "Use exact cube member names from the metadata. "
        "Pay close attention to the Query Construction Rules for when to include or omit granularity in time dimensions."
    ),
)


SPECIALISTS = {
    "marketing": MARKETING_SPECIALIST,
    "sales": SALES_SPECIALIST,
}
