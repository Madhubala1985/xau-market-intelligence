"""Position sizing (Task P7-002).

Calculates lot size from account balance, risk percentage, stop distance, broker
contract rules, and a spread/slippage buffer. References 03_RISK_POLICY.md
"Position Sizing Rule".

Hard rules:
- The stop distance is an INPUT and is never modified to grow size. A spread /
  slippage buffer only WIDENS the effective risk distance (more conservative
  sizing), it never shrinks the real stop.
- The lot is snapped DOWN to the broker lot step and clamped to [min_lot,
  max_lot], so realized risk never exceeds the target.
- If the logical stop is too wide to size even the minimum lot within the risk
  budget, the sizer does NOT shrink the stop -- it blocks (skip the trade).
- A requested risk above the per-trade limit is blocked (excessive risk).

The sizer never places orders; it produces a lot size and the resulting risk for
the Risk Governor (P7-001) to validate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.data.schemas import TradeDecision
from src.risk.governor import RiskLimits

_EPS = 1e-9


class SizingStatus(str, Enum):
    OK = "OK"
    RISK_TOO_HIGH = "RISK_TOO_HIGH"
    STOP_TOO_WIDE = "STOP_TOO_WIDE"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True)
class SizingResult:
    """Result of a position-sizing calculation."""

    status: SizingStatus
    lot_size: float
    risk_pct: float       # realized risk fraction at the chosen lot
    risk_amount: float    # realized risk in account currency
    effective_stop: float  # stop distance incl. spread/slippage buffer (price)
    reason: str

    @property
    def approved(self) -> bool:
        return self.status is SizingStatus.OK


class PositionSizer:
    """Computes a broker-valid lot size for a trade within the risk budget."""

    def __init__(
        self,
        limits: Optional[RiskLimits] = None,
        *,
        contract_size: float = 100.0,  # XAU/USD: 100 oz per 1.0 lot
    ) -> None:
        if contract_size <= 0:
            raise ValueError("contract_size must be > 0")
        self._limits = limits or RiskLimits()
        self._contract_size = contract_size

    def size(
        self,
        decision: TradeDecision,
        balance: float,
        requested_risk_pct: float,
        *,
        spread_price: float = 0.0,
        slippage_price: float = 0.0,
    ) -> SizingResult:
        limits = self._limits

        # 1) Input validation.
        if balance <= 0 or requested_risk_pct <= 0:
            return self._fail(SizingStatus.INVALID_INPUT, "balance and risk must be > 0")
        if decision.entry_price is None or decision.stop_loss is None:
            return self._fail(SizingStatus.INVALID_INPUT, "decision lacks entry/stop")
        if spread_price < 0 or slippage_price < 0:
            return self._fail(SizingStatus.INVALID_INPUT, "buffers must be >= 0")

        stop_distance = abs(decision.entry_price - decision.stop_loss)
        if stop_distance <= 0:
            return self._fail(SizingStatus.INVALID_INPUT, "stop distance is zero")

        # 2) Excessive requested risk is blocked (never silently capped).
        if requested_risk_pct > limits.max_risk_per_trade + _EPS:
            return self._fail(
                SizingStatus.RISK_TOO_HIGH,
                f"requested risk {requested_risk_pct} exceeds max "
                f"{limits.max_risk_per_trade}",
            )

        # 3) Buffer widens the effective risk distance (conservative); the real
        #    stop is never shrunk to grow size.
        effective_stop = stop_distance + spread_price + slippage_price
        risk_budget = balance * requested_risk_pct
        risk_per_lot = effective_stop * self._contract_size
        raw_lot = risk_budget / risk_per_lot

        # 4) Snap DOWN to the lot step and clamp to the max lot.
        lot = self._snap_down(raw_lot, limits.lot_step)
        if lot > limits.max_lot:
            lot = self._snap_down(limits.max_lot, limits.lot_step)

        # 5) Too wide to size even the minimum lot within budget -> skip.
        if lot < limits.min_lot - _EPS:
            return self._fail(
                SizingStatus.STOP_TOO_WIDE,
                "stop too wide to size minimum lot within risk budget; skip "
                "(stop is never shrunk to fit)",
                effective_stop=effective_stop,
            )

        risk_amount = lot * risk_per_lot
        risk_pct = risk_amount / balance
        return SizingResult(
            status=SizingStatus.OK,
            lot_size=round(lot, 8),
            risk_pct=risk_pct,
            risk_amount=risk_amount,
            effective_stop=effective_stop,
            reason=f"sized {round(lot, 8)} lots at {risk_pct:.4%} risk",
        )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _snap_down(value: float, step: float) -> float:
        if step <= 0:
            return value
        units = math.floor(value / step + _EPS)
        return round(units * step, 8)

    @staticmethod
    def _fail(
        status: SizingStatus, reason: str, *, effective_stop: float = 0.0
    ) -> SizingResult:
        return SizingResult(
            status=status,
            lot_size=0.0,
            risk_pct=0.0,
            risk_amount=0.0,
            effective_stop=effective_stop,
            reason=reason,
        )
