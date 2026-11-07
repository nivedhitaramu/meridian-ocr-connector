"""Subscription plans and their monthly document limits. None means no limit.

Billing isn't built yet, so a plan is set on the organization by staff. Every new organization starts on "trial".
"""
from __future__ import annotations

PLANS: dict[str, int | None] = {
    "trial": 100,
    "team": 2_000,
    "business": 20_000,
    "enterprise": None,
}
DEFAULT_PLAN = "trial"


def monthly_limit(plan: str | None) -> int | None:
    """An unknown plan gets the trial limit, so a typo can't remove a limit."""
    return PLANS.get(plan or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])
