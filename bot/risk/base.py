"""
Shared vocabulary for the risk layer. RiskDecision is the only thing a check
returns -- allow or block, with a reason. There is deliberately no third
state: a check that cannot determine an answer must raise, and RiskGate
turns any raised exception into a block (see gate.py), never into an
implicit allow.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    blocked: bool
    reason: str = ""

    @staticmethod
    def allow() -> "RiskDecision":
        return RiskDecision(blocked=False)

    @staticmethod
    def block(reason: str) -> "RiskDecision":
        return RiskDecision(blocked=True, reason=reason)


@dataclass(frozen=True)
class RiskLimits:
    """
    All limits configurable, conservative defaults only -- concrete values
    are a risk-tolerance decision, not an engineering one. See PROGRESS.md
    for the numbers currently in use.
    """
    max_position_size: float = 1.0
    max_daily_drawdown_pct: float = 0.05
    max_orders_per_period: int = 10
    order_period_seconds: int = 3600
