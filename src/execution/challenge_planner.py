"""Demo-challenge trade planner (Task DEMO-CHALLENGE-001). DEMO ONLY.

The fixed-lot, momentum-profile counterpart of DemoTradePlanner, with the
SAME plan() signature so SupervisedDemoSession drives it unchanged. It NEVER
sends orders; the ExecutionGateway (kill switch + flags + its own governor
run) remains the only order pathway.

What it relaxes versus the institutional planner (owner-directed, demo only):
- NEWS_UNKNOWN does NOT block (no calendar = neutral); only an actual news
  RISK state blocks — the operator NEWS_BLOCK file or an active HIGH-impact
  calendar window.
- No tier dollar caps / adaptive budgets: the lot is the FIXED challenge lot
  chosen by the momentum pipeline (0.05 NORMAL / 0.10 STRONG, carried in
  decision.setup_type), demoted only by the survival cap, with 0.01 ONLY as
  a margin-refusal fallback.
- Add-ons require the open trades to be in FLOATING PROFIT (not yet
  break-even-protected) — momentum compounding, still never into losers.

What it KEEPS absolute:
- stop-loss mandatory,
- reconciliation must be clean (orphan positions block),
- same-direction add-ons only; an opposite-direction position blocks
  entirely (no hedging),
- every open trade must be in profit before any add-on; any losing or
  unknown-P&L position blocks add-ons (no averaging down, structurally),
- no add-on right after a losing trade (consecutive_losses > 0),
- max 3 open positions (the demo_challenge envelope),
- the RiskGovernor (challenge limits) has final authority.
"""

from __future__ import annotations

import re
from typing import List, Optional, Sequence

from src.broker.mt5_data_adapter import BrokerPosition
from src.data.enums import Direction
from src.data.schemas import BrokerState, TradeDecision
from src.execution.demo_planner import PlanCheck, TradePlan, confidence_tier
from src.execution.positions import ReconciliationReport
from src.risk.governor import RiskContext, RiskGovernor, RiskLimits
from src.risk.leverage_sizing import (
    AccountSnapshot,
    LeverageSizingResult,
    LeverageSizingStatus,
    SymbolSpec,
    TradingMode,
)
from src.risk.news_guard import NewsRiskState
from src.risk.pyramiding import PyramidAction, PyramidResult
from src.strategy.scoring import ConfidenceResult

# The only lots this planner will ever request.
CHALLENGE_LOTS = (0.05, 0.10)
MARGIN_FALLBACK_LOT = 0.01  # used ONLY when margin refuses the challenge lot

_LOT_PATTERN = re.compile(r"lot=(\d+\.\d+)")


class ChallengeTradePlanner:
    """Fixed-lot momentum plans for --profile demo_challenge. Never sends."""

    def __init__(
        self,
        limits: RiskLimits,
        *,
        spec: Optional[SymbolSpec] = None,
        governor: Optional[RiskGovernor] = None,
        mode: TradingMode = TradingMode.DEMO,
    ) -> None:
        if mode is not TradingMode.DEMO:
            raise ValueError(
                "ChallengeTradePlanner is DEMO-only; real mode is forbidden"
            )
        if limits.max_open_trades > 3:
            raise ValueError(
                "demo_challenge allows at most 3 open positions"
            )
        self._limits = limits
        self._spec = spec or SymbolSpec()
        self._governor = governor or RiskGovernor(limits)

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
        risk_budget: Optional[float] = None,
        risk_ceiling: Optional[float] = None,
    ) -> TradePlan:
        tier = confidence_tier(confidence)
        risk_inputs = risk_inputs or {}

        # Gate 1: orphan positions still block everything (fail closed).
        if not reconciliation.clean:
            return self._blocked(
                tier, PlanCheck.ORPHAN_POSITIONS,
                f"position reconciliation not clean: {reconciliation.detail}",
            )

        # Gate 2 (challenge carve-out): only an actual news RISK blocks —
        # the manual NEWS_BLOCK file or an active HIGH-impact window.
        # NEWS_UNKNOWN is NEUTRAL here (printed, never blocking).
        if news.known and news.risky:
            return self._blocked(
                tier, PlanCheck.NEWS_BLOCKED, f"news risk active: {news.detail}"
            )

        # Gate 3: the decision itself (stop-loss stays mandatory).
        if decision.direction not in (Direction.LONG, Direction.SHORT):
            return self._blocked(
                tier, PlanCheck.NOT_ACTIONABLE,
                f"direction {decision.direction.value} is not actionable",
            )
        if decision.stop_loss is None or decision.entry_price is None:
            return self._blocked(
                tier, PlanCheck.NO_STOP_LOSS,
                "tactical stop-loss is mandatory; no plan",
            )

        # Gate 4: same-direction pyramiding ONLY into floating profit.
        is_addon = len(open_positions) > 0
        pyramid: Optional[PyramidResult] = None
        if is_addon:
            pyramid = self._addon_gate(
                decision, open_positions,
                consecutive_losses=int(risk_inputs.get("consecutive_losses", 0)),
            )
            if not pyramid.allowed:
                check = (
                    PlanCheck.MAX_POSITIONS
                    if "max" in pyramid.reasons[0] else PlanCheck.PYRAMIDING_BLOCKED
                )
                return self._blocked(
                    tier, check,
                    "add-on refused: " + "; ".join(pyramid.reasons),
                    pyramid=pyramid,
                )

        # Gate 5: fixed challenge lot (from the momentum pipeline) with the
        # survival cap and the margin-refusal fallback chain.
        sizing = self._size_fixed_lot(decision, account, spread_price)
        if not sizing.approved:
            return self._blocked(
                tier, PlanCheck.SIZING_BLOCKED,
                f"sizing blocked: {sizing.reason}", sizing=sizing,
            )

        # Gate 6: Risk Governor — final authority (challenge limits).
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
            size_factor_hint=1.0,
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
                f"demo_challenge plan approved: {sizing.reason}; governor: "
                + "; ".join(verdict.reasons),
            ),
            sizing=sizing,
            pyramid=pyramid,
            risk=verdict,
        )

    # -- add-on gate ------------------------------------------------------------
    def _addon_gate(
        self,
        decision: TradeDecision,
        open_positions: Sequence[BrokerPosition],
        *,
        consecutive_losses: int,
    ) -> PyramidResult:
        reasons: List[str] = []
        if len(open_positions) >= self._limits.max_open_trades:
            reasons.append(
                f"{len(open_positions)} open >= max "
                f"{self._limits.max_open_trades} positions"
            )
        if any(
            p.direction != decision.direction.value for p in open_positions
        ):
            reasons.append(
                "an opposite-direction position is open; hedging is forbidden"
            )
        if any(p.stop_loss is None for p in open_positions):
            reasons.append(
                "an open position lacks a stop-loss; resolve before add-ons"
            )
        if any(p.profit is None for p in open_positions):
            reasons.append(
                "an open position's floating P&L is unknown (fail closed)"
            )
        elif any(p.profit <= 0 for p in open_positions):
            reasons.append(
                "existing position not in profit; add-ons require floating "
                "profit on every open trade (never average down)"
            )
        if consecutive_losses > 0:
            reasons.append(
                f"no add-on after a losing trade "
                f"(consecutive_losses={consecutive_losses})"
            )
        if reasons:
            return PyramidResult(
                action=PyramidAction.BLOCK, reasons=tuple(reasons)
            )
        return PyramidResult(
            action=PyramidAction.ALLOW,
            reasons=(
                "same-direction add-on permitted: all open trades in "
                "floating profit",
            ),
        )

    # -- sizing -------------------------------------------------------------------
    def _size_fixed_lot(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        spread_price: float,
    ) -> LeverageSizingResult:
        spec = self._spec
        requested = self._requested_lot(decision)
        effective_stop = (
            abs(decision.entry_price - decision.stop_loss)
            + max(spread_price, 0.0)
        )
        loss_per_lot = spec.loss_per_lot(effective_stop)
        cap = account.balance * self._limits.max_risk_per_trade

        # Survival-cap demotion chain (0.10 -> 0.05), then the explicit
        # margin-refusal fallback to the broker minimum (0.01) — the only
        # path to 0.01 in demo_challenge.
        chain = [lot for lot in (requested, *CHALLENGE_LOTS) if lot <= requested]
        chain = sorted(set(chain), reverse=True)
        for lot in chain:
            implied = lot * loss_per_lot
            if implied > cap + 1e-9:
                continue
            margin = (lot * spec.contract_size * decision.entry_price
                      / account.leverage)
            if margin > account.free_margin + 1e-9:
                continue
            return LeverageSizingResult(
                status=LeverageSizingStatus.OK,
                lot_size=lot,
                max_loss_cap=cap,
                loss_per_lot=loss_per_lot,
                implied_loss=implied,
                implied_risk_pct=implied / account.balance,
                margin_required=margin,
                effective_stop=effective_stop,
                reason=(
                    f"fixed challenge lot {lot:.2f} "
                    f"(requested {requested:.2f}); loss-at-stop "
                    f"${implied:.2f} within survival cap ${cap:.2f}"
                ),
            )
        # Margin-only fallback: 0.01 is allowed ONLY when the cap would
        # accept the challenge lot but free margin refuses it.
        smallest = min(chain) if chain else requested
        cap_ok = smallest * loss_per_lot <= cap + 1e-9
        if cap_ok:
            margin = (MARGIN_FALLBACK_LOT * spec.contract_size
                      * decision.entry_price / account.leverage)
            if margin <= account.free_margin + 1e-9:
                implied = MARGIN_FALLBACK_LOT * loss_per_lot
                return LeverageSizingResult(
                    status=LeverageSizingStatus.OK,
                    lot_size=MARGIN_FALLBACK_LOT,
                    max_loss_cap=cap,
                    loss_per_lot=loss_per_lot,
                    implied_loss=implied,
                    implied_risk_pct=implied / account.balance,
                    margin_required=margin,
                    effective_stop=effective_stop,
                    reason=(
                        f"free margin refused {smallest:.2f}; broker-minimum "
                        f"fallback {MARGIN_FALLBACK_LOT:.2f} (margin "
                        f"${margin:.2f})"
                    ),
                )
            return LeverageSizingResult(
                status=LeverageSizingStatus.INSUFFICIENT_MARGIN,
                lot_size=0.0, max_loss_cap=cap, loss_per_lot=loss_per_lot,
                implied_loss=0.0, implied_risk_pct=0.0, margin_required=0.0,
                effective_stop=effective_stop,
                reason="insufficient free margin even at the broker minimum",
            )
        return LeverageSizingResult(
            status=LeverageSizingStatus.STOP_TOO_WIDE,
            lot_size=0.0, max_loss_cap=cap, loss_per_lot=loss_per_lot,
            implied_loss=0.0, implied_risk_pct=0.0, margin_required=0.0,
            effective_stop=effective_stop,
            reason=(
                f"tactical stop {effective_stop:.2f} risks more than the "
                f"survival cap ${cap:.2f} even at "
                f"{min(CHALLENGE_LOTS):.2f}; skip and wait for a tighter "
                "local stop (demo_challenge never widens risk to fit)"
            ),
        )

    @staticmethod
    def _requested_lot(decision: TradeDecision) -> float:
        """The pipeline's lot choice, carried in setup_type (journaled)."""
        match = _LOT_PATTERN.search(decision.setup_type or "")
        if match:
            lot = float(match.group(1))
            if lot in CHALLENGE_LOTS:
                return lot
        return min(CHALLENGE_LOTS)  # conservative default, never 0.01

    @staticmethod
    def _blocked(
        tier,
        check: PlanCheck,
        reason: str,
        *,
        sizing: Optional[LeverageSizingResult] = None,
        pyramid: Optional[PyramidResult] = None,
        risk=None,
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
