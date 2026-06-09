"""Leverage-aware, confidence-tiered position sizing (Task RISK-001).

References 20_LEVERAGE_AND_PYRAMIDING_POLICY.md and 03_RISK_POLICY.md.

Core rules enforced here:
- Stop distance comes from STRUCTURE (the decision's entry/stop). It is an input
  and is never modified to grow size.
- Lot size is derived from the allowed MAX LOSS (a dollar cap) and the structural
  stop distance -- never from available leverage or free margin.
- Leverage only changes the MARGIN REQUIRED, never the loss at stop. So leverage /
  margin availability can never bypass the max-loss rule: margin is a feasibility
  check that can only BLOCK a trade, never enlarge the lot.
- Demo uses confidence tiers with higher dollar caps (NORMAL $40 /
  HIGH_CONFLUENCE $80 / ELITE $100). Real mode does NOT inherit demo tiers; its
  cap stays conservative (balance * real_risk_pct).
- Fixed lots (0.01 / 0.05 / 0.10) are assessed against the same cap: a fixed lot
  is allowed only if its implied loss at the structural stop is within the cap.

The sizer never places orders. Its output (lot, implied loss, implied risk %,
margin required) feeds the Risk Governor (P7-001), which keeps final authority.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.data.schemas import TradeDecision

_EPS = 1e-9


class TradingMode(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"


class ConfidenceTier(str, Enum):
    """Confidence-tiered demo risk tiers (20_LEVERAGE_AND_PYRAMIDING_POLICY.md)."""

    NO_TRADE = "NO_TRADE"
    NORMAL_SETUP = "NORMAL_SETUP"
    HIGH_CONFLUENCE_SETUP = "HIGH_CONFLUENCE_SETUP"
    ELITE_A_PLUS_SETUP = "ELITE_A_PLUS_SETUP"


class LeverageSizingStatus(str, Enum):
    OK = "OK"
    NO_TRADE_TIER = "NO_TRADE_TIER"
    INVALID_INPUT = "INVALID_INPUT"
    STOP_TOO_WIDE = "STOP_TOO_WIDE"          # min lot loss already exceeds cap
    FIXED_LOT_EXCEEDS_CAP = "FIXED_LOT_EXCEEDS_CAP"
    INVALID_LOT = "INVALID_LOT"              # not aligned / outside broker lot bounds
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"


@dataclass(frozen=True)
class SymbolSpec:
    """Broker contract specification for XAU/USD.

    Defaults match a typical XAU/USD CFD: 100 oz per 1.0 lot, 0.01 tick worth
    $1.00 per 1.0 lot. Confirm against MT5 symbol_info at runtime (WINMT5-001).
    """

    symbol: str = "XAUUSD"
    contract_size: float = 100.0   # oz per 1.0 lot
    tick_size: float = 0.01        # minimum price increment
    tick_value: float = 1.0        # account currency per tick per 1.0 lot
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0

    def __post_init__(self) -> None:
        for name in ("contract_size", "tick_size", "tick_value", "min_lot", "lot_step", "max_lot"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be > 0")
        if self.max_lot < self.min_lot:
            raise ValueError("max_lot must be >= min_lot")

    def loss_per_lot(self, stop_distance_price: float) -> float:
        """Loss (account currency) for 1.0 lot if the structural stop is hit."""
        return (stop_distance_price / self.tick_size) * self.tick_value


@dataclass(frozen=True)
class DemoTierTable:
    """Demo max-loss caps per confidence tier (20_LEVERAGE_AND_PYRAMIDING_POLICY.md)."""

    normal_setup: float = 40.0
    high_confluence_setup: float = 80.0
    elite_a_plus_setup: float = 100.0

    def cap_for(self, tier: ConfidenceTier) -> float:
        if tier is ConfidenceTier.NO_TRADE:
            return 0.0
        if tier is ConfidenceTier.NORMAL_SETUP:
            return self.normal_setup
        if tier is ConfidenceTier.HIGH_CONFLUENCE_SETUP:
            return self.high_confluence_setup
        if tier is ConfidenceTier.ELITE_A_PLUS_SETUP:
            return self.elite_a_plus_setup
        raise ValueError(f"unknown tier {tier!r}")


@dataclass(frozen=True)
class AccountSnapshot:
    """Live account inputs needed for leverage-aware sizing."""

    balance: float
    free_margin: float
    leverage: int = 100

    def __post_init__(self) -> None:
        if self.balance <= 0:
            raise ValueError("balance must be > 0")
        if self.free_margin < 0:
            raise ValueError("free_margin must be >= 0")
        if self.leverage <= 0:
            raise ValueError("leverage must be > 0")


@dataclass(frozen=True)
class LeverageSizingResult:
    """Result of a leverage-aware sizing or fixed-lot assessment."""

    status: LeverageSizingStatus
    lot_size: float
    max_loss_cap: float       # the dollar cap that governed this trade
    loss_per_lot: float       # loss at structural stop for 1.0 lot
    implied_loss: float       # loss at structural stop for the chosen lot
    implied_risk_pct: float   # implied_loss / balance
    margin_required: float    # margin needed at the chosen lot/leverage
    effective_stop: float     # structural stop distance incl. buffers (price)
    reason: str

    @property
    def approved(self) -> bool:
        return self.status is LeverageSizingStatus.OK


class LeverageAwareSizer:
    """Sizes XAU/USD positions from the max-loss cap and the structural stop."""

    def __init__(
        self,
        symbol_spec: Optional[SymbolSpec] = None,
        *,
        demo_tiers: Optional[DemoTierTable] = None,
        real_risk_pct: float = 0.005,
    ) -> None:
        if real_risk_pct <= 0:
            raise ValueError("real_risk_pct must be > 0")
        self._spec = symbol_spec or SymbolSpec()
        self._tiers = demo_tiers or DemoTierTable()
        self._real_risk_pct = real_risk_pct

    # -- cap resolution ----------------------------------------------------
    def max_loss_cap(
        self, mode: TradingMode, tier: ConfidenceTier, balance: float
    ) -> float:
        """Resolve the governing dollar max-loss cap.

        Demo uses the confidence tier dollar cap. Real mode never inherits demo
        tiers: its cap stays conservative at balance * real_risk_pct.
        """
        if tier is ConfidenceTier.NO_TRADE:
            return 0.0
        if mode is TradingMode.DEMO:
            return self._tiers.cap_for(tier)
        # Real mode: conservative, balance-relative, tier-independent.
        return balance * self._real_risk_pct

    # -- structural-stop sizing -------------------------------------------
    def size(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        tier: ConfidenceTier,
        *,
        mode: TradingMode = TradingMode.DEMO,
        spread_price: float = 0.0,
        slippage_price: float = 0.0,
        hard_cap: Optional[float] = None,
    ) -> LeverageSizingResult:
        """Compute the largest broker-valid lot whose loss stays within the cap.

        `hard_cap` (optional) is an additional dollar cap that can only TIGHTEN
        the tier cap (the governing cap becomes min(tier cap, hard_cap)). It can
        never enlarge the lot; passing a hard_cap above the tier cap is a no-op.
        Used to keep tier sizing inside the Risk Governor's per-trade budget
        when both policies apply (tightest rule wins).
        """
        if tier is ConfidenceTier.NO_TRADE:
            return self._fail(
                LeverageSizingStatus.NO_TRADE_TIER, "NO_TRADE tier -> risk 0", cap=0.0
            )
        if hard_cap is not None and hard_cap <= 0:
            return self._fail(
                LeverageSizingStatus.INVALID_INPUT, "hard_cap must be > 0 when given"
            )

        validated = self._validate(decision, spread_price, slippage_price)
        if isinstance(validated, LeverageSizingResult):
            return validated
        entry, effective_stop = validated

        cap = self.max_loss_cap(mode, tier, account.balance)
        if hard_cap is not None:
            cap = min(cap, hard_cap)
        spec = self._spec
        loss_per_lot = spec.loss_per_lot(effective_stop)

        raw_lot = cap / loss_per_lot
        lot = self._snap_down(raw_lot, spec.lot_step)
        if lot > spec.max_lot:
            lot = self._snap_down(spec.max_lot, spec.lot_step)

        # Minimum broker lot already loses more than the cap -> never shrink the
        # stop to fit; block (20_LEVERAGE_AND_PYRAMIDING_POLICY.md Fixed Lot Rule).
        if lot < spec.min_lot - _EPS:
            return self._fail(
                LeverageSizingStatus.STOP_TOO_WIDE,
                "minimum lot loss exceeds the max-loss cap; block (stop is never "
                "shrunk to fit)",
                cap=cap,
                loss_per_lot=loss_per_lot,
                effective_stop=effective_stop,
            )

        return self._finalize(
            lot, entry, effective_stop, cap, loss_per_lot, account
        )

    # -- fixed-lot assessment ---------------------------------------------
    def assess_fixed_lot(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        tier: ConfidenceTier,
        requested_lot: float,
        *,
        mode: TradingMode = TradingMode.DEMO,
        spread_price: float = 0.0,
        slippage_price: float = 0.0,
    ) -> LeverageSizingResult:
        """Allow a fixed lot only if its implied loss is within the cap.

        0.01 / 0.05 / 0.10 are considered in demo ONLY after computing the implied
        loss at the structural stop. A fixed lot can never bypass the cap; if it
        would over-risk, it is blocked (reduce or block per policy).
        """
        if tier is ConfidenceTier.NO_TRADE:
            return self._fail(
                LeverageSizingStatus.NO_TRADE_TIER, "NO_TRADE tier -> risk 0", cap=0.0
            )

        validated = self._validate(decision, spread_price, slippage_price)
        if isinstance(validated, LeverageSizingResult):
            return validated
        entry, effective_stop = validated

        spec = self._spec
        cap = self.max_loss_cap(mode, tier, account.balance)
        loss_per_lot = spec.loss_per_lot(effective_stop)

        # Broker lot validity (aligned to step, within [min, max]).
        if (
            requested_lot < spec.min_lot - _EPS
            or requested_lot > spec.max_lot + _EPS
            or not self._aligned(requested_lot, spec.lot_step)
        ):
            return self._fail(
                LeverageSizingStatus.INVALID_LOT,
                f"requested lot {requested_lot} is not a valid broker lot",
                cap=cap,
                loss_per_lot=loss_per_lot,
                effective_stop=effective_stop,
            )

        implied_loss = requested_lot * loss_per_lot
        if implied_loss > cap + _EPS:
            max_lot = self._snap_down(cap / loss_per_lot, spec.lot_step)
            return self._fail(
                LeverageSizingStatus.FIXED_LOT_EXCEEDS_CAP,
                f"fixed lot {requested_lot} implies ${implied_loss:.2f} loss, over "
                f"cap ${cap:.2f}; max compliant lot {max_lot}",
                cap=cap,
                loss_per_lot=loss_per_lot,
                effective_stop=effective_stop,
            )

        return self._finalize(
            requested_lot, entry, effective_stop, cap, loss_per_lot, account
        )

    # -- helpers -----------------------------------------------------------
    def _validate(
        self, decision: TradeDecision, spread_price: float, slippage_price: float
    ):
        if decision.entry_price is None or decision.stop_loss is None:
            return self._fail(
                LeverageSizingStatus.INVALID_INPUT, "decision lacks entry/stop"
            )
        if spread_price < 0 or slippage_price < 0:
            return self._fail(
                LeverageSizingStatus.INVALID_INPUT, "buffers must be >= 0"
            )
        stop_distance = abs(decision.entry_price - decision.stop_loss)
        if stop_distance <= 0:
            return self._fail(
                LeverageSizingStatus.INVALID_INPUT, "stop distance is zero"
            )
        effective_stop = stop_distance + spread_price + slippage_price
        return decision.entry_price, effective_stop

    def _finalize(
        self,
        lot: float,
        entry: float,
        effective_stop: float,
        cap: float,
        loss_per_lot: float,
        account: AccountSnapshot,
    ) -> LeverageSizingResult:
        spec = self._spec
        implied_loss = lot * loss_per_lot
        implied_risk_pct = implied_loss / account.balance
        # Leverage changes ONLY the margin required, never the loss at stop.
        margin_required = (lot * spec.contract_size * entry) / account.leverage

        if margin_required > account.free_margin + _EPS:
            return self._fail(
                LeverageSizingStatus.INSUFFICIENT_MARGIN,
                f"margin required ${margin_required:.2f} exceeds free margin "
                f"${account.free_margin:.2f}",
                cap=cap,
                loss_per_lot=loss_per_lot,
                effective_stop=effective_stop,
            )

        return LeverageSizingResult(
            status=LeverageSizingStatus.OK,
            lot_size=round(lot, 8),
            max_loss_cap=cap,
            loss_per_lot=loss_per_lot,
            implied_loss=implied_loss,
            implied_risk_pct=implied_risk_pct,
            margin_required=margin_required,
            effective_stop=effective_stop,
            reason=(
                f"sized {round(lot, 8)} lots; implied loss ${implied_loss:.2f} "
                f"within cap ${cap:.2f}"
            ),
        )

    @staticmethod
    def _snap_down(value: float, step: float) -> float:
        if step <= 0:
            return value
        units = math.floor(value / step + _EPS)
        return round(units * step, 8)

    @staticmethod
    def _aligned(value: float, step: float) -> bool:
        if step <= 0:
            return True
        units = value / step
        return abs(units - round(units)) <= 1e-9

    @staticmethod
    def _fail(
        status: LeverageSizingStatus,
        reason: str,
        *,
        cap: float = 0.0,
        loss_per_lot: float = 0.0,
        effective_stop: float = 0.0,
    ) -> LeverageSizingResult:
        return LeverageSizingResult(
            status=status,
            lot_size=0.0,
            max_loss_cap=cap,
            loss_per_lot=loss_per_lot,
            implied_loss=0.0,
            implied_risk_pct=0.0,
            margin_required=0.0,
            effective_stop=effective_stop,
            reason=reason,
        )
