"""Demo trade planner (Audit F-3): the sized, guarded, governed order plan.

Wires the RISK-001 engines into ONE demo execution path, in fail-closed order:

    reconciliation clean?  (F-4: orphan positions block planning)
      -> news risk known and not risky?  (F-5: unknown news state blocks)
      -> decision actionable with mandatory stop-loss?
      -> confidence tier  (ConfidenceResult -> NORMAL/HIGH_CONFLUENCE/ELITE)
      -> LeverageAwareSizer  (tier dollar cap, TIGHTENED by the governor's
         per-trade budget: cap = min(tier cap, balance * max_risk_per_trade);
         margin affects feasibility only, never the loss cap)
      -> PyramidingGuard  (any position already open => this must qualify as a
         protected add-on; one base position + at most ONE protected add-on)
      -> RiskGovernor  (FINAL AUTHORITY; the protected_addon flag is set only
         after the guard explicitly ALLOWED)

The planner NEVER sends orders and holds no MT5 client. Its output is a
TradePlan that the supervised demo session (DEMO-002) may hand to the
ExecutionGateway — which re-runs its own checks and remains the only order
pathway. Real mode is refused at construction.

Policy notes (recorded in 11_DECISION_LOG.md):
- 03_RISK_POLICY's demo profile (0.50%/trade, max 1 open trade) and
  20_LEVERAGE_AND_PYRAMIDING_POLICY's tier caps / protected add-ons coexist by
  applying the TIGHTEST rule: tier sizing is clamped to the governor's
  per-trade budget, and a second position exists ONLY as a guard-approved
  protected add-on within max_open_trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from src.broker.mt5_data_adapter import BrokerPosition
from src.data.enums import Direction
from src.data.schemas import BrokerState, TradeDecision
from src.execution.positions import ReconciliationReport
from src.risk.governor import RiskContext, RiskDecision, RiskGovernor, RiskLimits
from src.risk.leverage_sizing import (
    AccountSnapshot,
    ConfidenceTier,
    LeverageAwareSizer,
    LeverageSizingResult,
    TradingMode,
)
from src.risk.news_guard import NewsRiskState
from src.risk.pyramiding import OpenTrade, PyramidResult, PyramidingGuard
from src.strategy.scoring import ConfidenceResult, ScoreRecommendation


class PlanCheck(str, Enum):
    """Stable codes for each planner gate that can block a plan."""

    ORPHAN_POSITIONS = "ORPHAN_POSITIONS"
    NEWS_UNKNOWN = "NEWS_UNKNOWN"
    NEWS_BLOCKED = "NEWS_BLOCKED"
    NOT_ACTIONABLE = "NOT_ACTIONABLE"
    NO_STOP_LOSS = "NO_STOP_LOSS"
    NO_TRADE_TIER = "NO_TRADE_TIER"
    SIZING_BLOCKED = "SIZING_BLOCKED"
    POSITION_WITHOUT_STOP = "POSITION_WITHOUT_STOP"
    MAX_POSITIONS = "MAX_POSITIONS"
    PYRAMIDING_BLOCKED = "PYRAMIDING_BLOCKED"
    RISK_BLOCKED = "RISK_BLOCKED"


@dataclass(frozen=True)
class TradePlan:
    """A fully evaluated demo order plan (NOT an order; nothing is sent)."""

    approved: bool
    is_addon: bool
    lot_size: float
    tier: ConfidenceTier
    failed_checks: Tuple[PlanCheck, ...] = ()
    reasons: Tuple[str, ...] = ()
    sizing: Optional[LeverageSizingResult] = None
    pyramid: Optional[PyramidResult] = None
    risk: Optional[RiskDecision] = None

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "is_addon": self.is_addon,
            "lot_size": self.lot_size,
            "tier": self.tier.value,
            "failed_checks": [c.value for c in self.failed_checks],
            "reasons": list(self.reasons),
        }


def confidence_tier(confidence: ConfidenceResult) -> ConfidenceTier:
    """Map the scoring result to a demo confidence tier (policy 20).

    BLOCK recommendation -> NO_TRADE. REDUCE -> NORMAL (never escalated).
    ALLOW escalates only with high confidence AND low uncertainty:
    ELITE requires >= 0.85 confidence and <= 0.15 uncertainty;
    HIGH_CONFLUENCE requires >= 0.70 confidence and <= 0.25 uncertainty.
    """
    if confidence.recommendation is ScoreRecommendation.BLOCK:
        return ConfidenceTier.NO_TRADE
    if confidence.recommendation is ScoreRecommendation.REDUCE:
        return ConfidenceTier.NORMAL_SETUP
    if confidence.confidence >= 0.85 and confidence.uncertainty <= 0.15:
        return ConfidenceTier.ELITE_A_PLUS_SETUP
    if confidence.confidence >= 0.70 and confidence.uncertainty <= 0.25:
        return ConfidenceTier.HIGH_CONFLUENCE_SETUP
    return ConfidenceTier.NORMAL_SETUP


class DemoTradePlanner:
    """Builds sized, guarded, governor-approved demo trade plans. Never sends."""

    def __init__(
        self,
        *,
        sizer: Optional[LeverageAwareSizer] = None,
        guard: Optional[PyramidingGuard] = None,
        governor: Optional[RiskGovernor] = None,
        limits: Optional[RiskLimits] = None,
        mode: TradingMode = TradingMode.DEMO,
    ) -> None:
        if mode is not TradingMode.DEMO:
            raise ValueError("DemoTradePlanner is DEMO-only; real mode is forbidden")
        # max_open_trades=2 permits exactly one guard-approved protected
        # add-on on top of one base position; the governor's duplicate check
        # still blocks any same-symbol second entry that is NOT a protected
        # add-on, and a third position is blocked by the count check.
        self._limits = limits or RiskLimits(expected_symbol="XAUUSDM", max_open_trades=2)
        self._sizer = sizer or LeverageAwareSizer()
        self._guard = guard or PyramidingGuard()
        self._governor = governor or RiskGovernor(self._limits)

    def plan(
        self,
        decision: TradeDecision,
        confidence: ConfidenceResult,
        *,
        broker: BrokerState,
        account: AccountSnapshot,
        spread_price: float,
        open_positions: Sequence[BrokerPosition],
        reconciliation: ReconciliationReport,
        news: NewsRiskState,
        risk_inputs: Optional[dict] = None,
        fresh_setup: bool = False,
        continuation_supported: bool = False,
    ) -> TradePlan:
        tier = confidence_tier(confidence)
        risk_inputs = risk_inputs or {}

        # Gate 1 (F-4): orphan positions block all planning. Fail closed.
        if not reconciliation.clean:
            return self._blocked(
                tier, PlanCheck.ORPHAN_POSITIONS,
                f"position reconciliation not clean: {reconciliation.detail}",
            )

        # Gate 2 (F-5): news risk. Unknown state blocks (fail closed).
        if not news.known:
            return self._blocked(
                tier, PlanCheck.NEWS_UNKNOWN,
                "news risk state unknown (no manual block, no calendar); "
                "order planning is blocked until a news source exists",
            )
        if news.risky:
            return self._blocked(
                tier, PlanCheck.NEWS_BLOCKED, f"news risk active: {news.detail}"
            )

        # Gate 3: the decision itself.
        if decision.direction not in (Direction.LONG, Direction.SHORT):
            return self._blocked(
                tier, PlanCheck.NOT_ACTIONABLE,
                f"direction {decision.direction.value} is not actionable",
            )
        if decision.stop_loss is None:
            return self._blocked(
                tier, PlanCheck.NO_STOP_LOSS, "stop-loss is mandatory; no plan"
            )
        if tier is ConfidenceTier.NO_TRADE:
            return self._blocked(
                tier, PlanCheck.NO_TRADE_TIER,
                f"confidence tier NO_TRADE ({confidence.reason})",
            )

        # Gate 4 (F-3): leverage-aware sizing, tier cap TIGHTENED by the
        # governor's per-trade budget (tightest rule wins; never loosened).
        governor_budget = account.balance * self._limits.max_risk_per_trade
        sizing = self._sizer.size(
            decision, account, tier,
            mode=TradingMode.DEMO,
            spread_price=spread_price,
            hard_cap=governor_budget,
        )
        if not sizing.approved:
            return self._blocked(
                tier, PlanCheck.SIZING_BLOCKED, f"sizing blocked: {sizing.reason}",
                sizing=sizing,
            )

        # Gate 5 (F-3/F-4): one active thesis unless protected pyramiding.
        is_addon = len(open_positions) > 0
        pyramid: Optional[PyramidResult] = None
        if is_addon:
            if len(open_positions) >= self._limits.max_open_trades:
                return self._blocked(
                    tier, PlanCheck.MAX_POSITIONS,
                    f"{len(open_positions)} position(s) open >= max "
                    f"{self._limits.max_open_trades}; no further add-ons",
                    sizing=sizing,
                )
            open_trades = self._to_open_trades(open_positions)
            if open_trades is None:
                return self._blocked(
                    tier, PlanCheck.POSITION_WITHOUT_STOP,
                    "an open position lacks stop-loss/price data; resolve before "
                    "any add-on (stop-loss is mandatory)",
                    sizing=sizing,
                )
            pyramid = self._guard.evaluate(
                decision,
                sizing.lot_size,
                sizing.implied_loss,
                open_trades,
                fresh_setup=fresh_setup,
                continuation_supported=continuation_supported,
            )
            if not pyramid.allowed:
                return self._blocked(
                    tier, PlanCheck.PYRAMIDING_BLOCKED,
                    "protected pyramiding refused: " + "; ".join(pyramid.reasons),
                    sizing=sizing, pyramid=pyramid,
                )

        # Gate 6: Risk Governor — final authority.
        context = RiskContext(
            broker=broker,
            current_spread=spread_price,
            lot_size=sizing.lot_size,
            intended_risk_pct=sizing.implied_risk_pct,
            daily_loss_pct=float(risk_inputs.get("daily_loss_pct", 0.0)),
            weekly_loss_pct=float(risk_inputs.get("weekly_loss_pct", 0.0)),
            trades_today=int(risk_inputs.get("trades_today", 0)),
            consecutive_losses=int(risk_inputs.get("consecutive_losses", 0)),
            open_symbols=frozenset(risk_inputs.get("open_symbols", frozenset())),
            size_factor_hint=confidence.size_factor,
            protected_addon=bool(is_addon and pyramid is not None and pyramid.allowed),
        )
        verdict = self._governor.evaluate(decision, context)
        if verdict.is_blocked:
            return self._blocked(
                tier, PlanCheck.RISK_BLOCKED,
                "risk governor blocked: " + "; ".join(verdict.reasons),
                sizing=sizing, pyramid=pyramid, risk=verdict,
            )

        return TradePlan(
            approved=True,
            is_addon=is_addon,
            lot_size=sizing.lot_size,
            tier=tier,
            reasons=(
                f"plan approved: {sizing.reason}; governor: "
                + "; ".join(verdict.reasons),
            ),
            sizing=sizing,
            pyramid=pyramid,
            risk=verdict,
        )

    # -- helpers ---------------------------------------------------------------
    @staticmethod
    def _to_open_trades(
        positions: Sequence[BrokerPosition],
    ) -> Optional[List[OpenTrade]]:
        """Map broker positions to OpenTrade; None if any lacks stop/price."""
        trades: List[OpenTrade] = []
        for p in positions:
            if p.stop_loss is None or p.current_price is None:
                return None
            trades.append(
                OpenTrade(
                    symbol=p.symbol,
                    direction=Direction(p.direction),
                    entry_price=p.entry_price,
                    stop_loss=p.stop_loss,
                    current_price=p.current_price,
                    lot_size=p.lot_size,
                )
            )
        return trades

    @staticmethod
    def _blocked(
        tier: ConfidenceTier,
        check: PlanCheck,
        reason: str,
        *,
        sizing: Optional[LeverageSizingResult] = None,
        pyramid: Optional[PyramidResult] = None,
        risk: Optional[RiskDecision] = None,
    ) -> TradePlan:
        return TradePlan(
            approved=False,
            is_addon=False,
            lot_size=0.0,
            tier=tier,
            failed_checks=(check,),
            reasons=(reason,),
            sizing=sizing,
            pyramid=pyramid,
            risk=risk,
        )
