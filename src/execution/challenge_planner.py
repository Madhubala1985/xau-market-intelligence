"""Demo-challenge trade planner (Task DEMO-CHALLENGE-001). DEMO ONLY.

The challenge-profile counterpart of DemoTradePlanner, with the SAME plan()
signature so SupervisedDemoSession drives it unchanged. It NEVER sends
orders; the ExecutionGateway (kill switch + flags + its own governor run)
remains the only order pathway.

What it relaxes versus the institutional planner (owner-directed, demo only):
- NEWS_UNKNOWN does NOT block (no calendar = neutral); only an actual news
  RISK state blocks — the operator NEWS_BLOCK file or an active HIGH-impact
  calendar window.
- No tier dollar caps / adaptive budgets: the pipeline's tier lot
  (0.05 NORMAL / 0.10 STRONG in decision.setup_type) selects the EQUITY
  RISK TIER (1.0% / 1.5% of balance, decision 2026-06-11-06); the broker
  lot is derived from the tactical stop so size compounds with equity,
  bounded by the 3%/trade survival cap and broker min/max/step.
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

# The pipeline's tier lots (parsed from setup_type). Since decision
# 2026-06-11-06 they select the EQUITY RISK TIER instead of being sent to
# the broker verbatim: 0.10 (STRONG, undemoted) => 1.5% of balance risked
# to the tactical stop, 0.05 (NORMAL or demoted STRONG) => 1.0%. Lots are
# derived from the stop distance so position size compounds with equity.
CHALLENGE_LOTS = (0.05, 0.10)
RISK_PCT_NORMAL = 0.010
RISK_PCT_STRONG = 0.015

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

        # Gate 4: same-direction pyramiding ONLY into protected winners
        # (SMC-EXECUTION-001: +0.21 floating is noise, not a winner).
        is_addon = len(open_positions) > 0
        pyramid: Optional[PyramidResult] = None
        if is_addon:
            pyramid = self._addon_gate(
                decision, open_positions,
                consecutive_losses=int(risk_inputs.get("consecutive_losses", 0)),
                seconds_since_last_entry=risk_inputs.get(
                    "seconds_since_last_entry"
                ),
                fresh_setup=fresh_setup,
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
    # SMC-EXECUTION-001: an add-on requires every open trade to be a
    # PROTECTED winner — stop at/beyond break-even OR floating profit of at
    # least MIN_PROTECTION_R of its current stop risk. A few cents of
    # floating profit (the live +0.21 case) is spread noise, not protection.
    MIN_PROTECTION_R = 0.5
    # H7 (decision 2026-06-12-04): base + ONE add-on; never a third leg.
    MAX_PYRAMID_LEGS = 2
    MIN_ADDON_SPACING_SECONDS = 300.0  # never inside the same M5 candle

    def _addon_gate(
        self,
        decision: TradeDecision,
        open_positions: Sequence[BrokerPosition],
        *,
        consecutive_losses: int,
        seconds_since_last_entry: Optional[float] = None,
        fresh_setup: bool = False,
    ) -> PyramidResult:
        reasons: List[str] = []
        if len(open_positions) >= self._limits.max_open_trades:
            reasons.append(
                f"{len(open_positions)} open >= max "
                f"{self._limits.max_open_trades} positions"
            )
        # H7 (decision 2026-06-12-04): pyramids cap at TWO legs — live
        # evidence: both times a third leg was added late into an extended
        # move it was clipped by a routine pullback (pyramid 2 net -33.86
        # entirely from legs 2+3 while the base leg was protected).
        elif len(open_positions) >= self.MAX_PYRAMID_LEGS:
            reasons.append(
                f"ADDON_BLOCKED_MAX_PYRAMID_LEGS: {len(open_positions)} "
                f"legs open; pyramids cap at {self.MAX_PYRAMID_LEGS} "
                "(late third legs get clipped by routine pullbacks)"
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
        else:
            for p in open_positions:
                if p.profit <= 0:
                    reasons.append(
                        f"ADDON_BLOCKED_NOT_PROTECTED: position {p.ticket} "
                        f"floating {p.profit:+.2f} (never average down)"
                    )
                    continue
                if p.stop_loss is None:
                    continue  # already reported above
                if self._at_breakeven(p):
                    continue  # protected by the stop itself
                risk = abs(p.entry_price - p.stop_loss) * p.lot_size * 100.0
                needed = self.MIN_PROTECTION_R * risk
                if risk <= 0 or p.profit < needed:
                    reasons.append(
                        f"ADDON_BLOCKED_PROFIT_TOO_SMALL: position "
                        f"{p.ticket} floating {p.profit:+.2f} < "
                        f"{self.MIN_PROTECTION_R}R (${needed:.2f}) and stop "
                        "not at break-even — noise is not protection"
                    )
        if (
            seconds_since_last_entry is not None
            and seconds_since_last_entry < self.MIN_ADDON_SPACING_SECONDS
        ):
            reasons.append(
                f"ADDON_BLOCKED_SAME_CANDLE: last entry "
                f"{seconds_since_last_entry:.0f}s ago < "
                f"{self.MIN_ADDON_SPACING_SECONDS:.0f}s (one M5 candle)"
            )
        if not fresh_setup:
            reasons.append(
                "ADDON_BLOCKED_SMC_CONTEXT_WEAKENED: no fresh fully-"
                "qualified SMC setup behind this add-on candidate"
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
                "same-direction add-on permitted: every open trade is a "
                "protected winner (break-even stop or >= "
                f"{self.MIN_PROTECTION_R}R floating) and the SMC thesis "
                "re-qualified",
            ),
        )

    @staticmethod
    def _at_breakeven(p: BrokerPosition) -> bool:
        if p.stop_loss is None:
            return False
        if p.direction == "LONG":
            return p.stop_loss >= p.entry_price - 1e-9
        return p.stop_loss <= p.entry_price + 1e-9

    # -- sizing -------------------------------------------------------------------
    def _size_fixed_lot(
        self,
        decision: TradeDecision,
        account: AccountSnapshot,
        spread_price: float,
    ) -> LeverageSizingResult:
        """Equity-scaled risk sizing (decision 2026-06-11-06).

        The tier lot in setup_type selects the risk percentage (0.10 =>
        1.5%, 0.05 => 1.0% — strategy demotions arrive as 0.05 and stay
        demoted); the LOT is derived from balance and the tactical stop:

            lot = floor((balance * risk_pct) / loss_per_lot, lot_step)

        so position size compounds with equity. The 3%/trade survival cap
        and the broker min/max/step bounds stay absolute; below the broker
        minimum the trade is promoted to min_lot only when its worst case
        still fits the cap; an unaffordable margin shrinks the lot, never
        the stop.
        """
        spec = self._spec
        requested = self._requested_lot(decision)
        risk_pct = (
            RISK_PCT_STRONG if requested >= max(CHALLENGE_LOTS) - 1e-9
            else RISK_PCT_NORMAL
        )
        effective_stop = (
            abs(decision.entry_price - decision.stop_loss)
            + max(spread_price, 0.0)
        )
        loss_per_lot = spec.loss_per_lot(effective_stop)
        cap = account.balance * self._limits.max_risk_per_trade
        budget = account.balance * risk_pct

        def floor_step(lot: float) -> float:
            steps = int((lot + 1e-9) / spec.lot_step)
            return round(steps * spec.lot_step, 2)

        lot = floor_step(min(budget / loss_per_lot, spec.max_lot))
        promoted = False
        if lot < spec.min_lot:
            # Broker-minimum promotion: allowed only inside the survival cap.
            if spec.min_lot * loss_per_lot > cap + 1e-9:
                return LeverageSizingResult(
                    status=LeverageSizingStatus.STOP_TOO_WIDE,
                    lot_size=0.0, max_loss_cap=cap, loss_per_lot=loss_per_lot,
                    implied_loss=0.0, implied_risk_pct=0.0,
                    margin_required=0.0, effective_stop=effective_stop,
                    reason=(
                        f"tactical stop {effective_stop:.2f} risks more than "
                        f"the survival cap ${cap:.2f} even at the broker "
                        f"minimum {spec.min_lot:.2f}; skip and wait for a "
                        "tighter local stop (risk is never widened to fit)"
                    ),
                )
            lot = spec.min_lot
            promoted = True

        # Margin: shrink the lot (never the stop) until affordable.
        def margin_for(l: float) -> float:
            return l * spec.contract_size * decision.entry_price / account.leverage

        while lot >= spec.min_lot - 1e-9 and margin_for(lot) > account.free_margin + 1e-9:
            lot = floor_step(lot - spec.lot_step)
        if lot < spec.min_lot - 1e-9:
            return LeverageSizingResult(
                status=LeverageSizingStatus.INSUFFICIENT_MARGIN,
                lot_size=0.0, max_loss_cap=cap, loss_per_lot=loss_per_lot,
                implied_loss=0.0, implied_risk_pct=0.0, margin_required=0.0,
                effective_stop=effective_stop,
                reason="insufficient free margin even at the broker minimum",
            )

        implied = lot * loss_per_lot
        if implied > cap + 1e-9:  # unreachable by construction; absolute guard
            return LeverageSizingResult(
                status=LeverageSizingStatus.STOP_TOO_WIDE,
                lot_size=0.0, max_loss_cap=cap, loss_per_lot=loss_per_lot,
                implied_loss=0.0, implied_risk_pct=0.0, margin_required=0.0,
                effective_stop=effective_stop,
                reason=f"sized loss ${implied:.2f} exceeds survival cap ${cap:.2f}",
            )
        margin = margin_for(lot)
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
                f"equity-risk sizing: {risk_pct:.1%} of ${account.balance:.2f} "
                f"= ${budget:.2f} budget at stop {effective_stop:.2f} -> lot "
                f"{lot:.2f}{' (broker-minimum promotion)' if promoted else ''} "
                f"(loss-at-stop ${implied:.2f}, survival cap ${cap:.2f})"
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
