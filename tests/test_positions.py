"""Tests for position reconciliation and protection (Audit F-4).

Proves:
- broker/journal matches by ticket and by attributes,
- broker orphans (manual/unknown positions) make the report not clean,
- journal orphans (open record with no broker position) make it not clean,
- fail-closed: not-clean blocks demo planning (covered in test_demo_planner),
- protection proposals never widen a stop, hold when premature, propose
  break-even when earned, and flag a missing stop-loss as a violation,
- the adapter reads positions read-only with the exact broker symbol case.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.broker.mt5_data_adapter import BrokerPosition, MT5DataAdapter
from src.broker.mt5_settings import load_mt5_settings
from src.data.enums import Direction, TradeOutcome
from src.data.schemas import TradeRecord
from src.execution import PositionReconciler
from src.trade_management import PositionProtectionManager

UTC = timezone.utc
NOW = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)


def broker_pos(ticket=101, *, direction="LONG", lot=0.01, entry=2300.0,
               sl=2295.0, price=2310.0, symbol="XAUUSDm") -> BrokerPosition:
    return BrokerPosition(
        ticket=ticket, symbol=symbol, direction=direction, lot_size=lot,
        entry_price=entry, stop_loss=sl, take_profit=2330.0,
        current_price=price, profit=(price - entry) * lot * 100,
    )


def open_record(rid="R1", *, direction=Direction.LONG, lot=0.01, entry=2300.0,
                notes=None) -> TradeRecord:
    return TradeRecord(
        record_id=rid, created_at_utc=NOW, symbol="XAUUSDM",
        direction=direction, outcome=TradeOutcome.OPEN,
        opened_at_utc=NOW, entry_price=entry, lot_size=lot,
        stop_loss=2295.0, notes=notes,
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

def test_ticket_match_is_clean():
    report = PositionReconciler().reconcile(
        [broker_pos(ticket=555)], [open_record(notes="ticket=555")]
    )
    assert report.clean
    assert report.matched == ((555, "R1"),)


def test_attribute_match_without_ticket_is_clean():
    report = PositionReconciler().reconcile([broker_pos()], [open_record()])
    assert report.clean


def test_unknown_broker_position_is_an_orphan():
    # e.g. a manual trade opened in the terminal: journal knows nothing.
    report = PositionReconciler().reconcile([broker_pos(ticket=777)], [])
    assert not report.clean
    assert report.orphan_broker == (777,)


def test_open_journal_record_missing_at_broker_is_an_orphan():
    # e.g. stopped out while the system was down.
    report = PositionReconciler().reconcile([], [open_record("R9")])
    assert not report.clean
    assert report.orphan_journal == ("R9",)


def test_direction_mismatch_does_not_match():
    report = PositionReconciler().reconcile(
        [broker_pos(direction="SHORT")], [open_record(direction=Direction.LONG)]
    )
    assert not report.clean


def test_entry_price_far_off_does_not_match():
    report = PositionReconciler().reconcile(
        [broker_pos(entry=2310.0)], [open_record(entry=2300.0)]
    )
    assert not report.clean


def test_closed_records_are_ignored():
    closed = TradeRecord(
        record_id="C1", created_at_utc=NOW, symbol="XAUUSDM",
        direction=Direction.LONG, outcome=TradeOutcome.WIN,
        opened_at_utc=NOW, closed_at_utc=NOW, pnl=10.0,
    )
    report = PositionReconciler().reconcile([], [closed])
    assert report.clean


# ---------------------------------------------------------------------------
# Protection proposals
# ---------------------------------------------------------------------------

def test_position_without_stop_is_a_violation():
    pos = BrokerPosition(
        ticket=1, symbol="XAUUSDm", direction="LONG", lot_size=0.01,
        entry_price=2300.0, stop_loss=None, take_profit=None,
        current_price=2310.0, profit=1.0,
    )
    proposal = PositionProtectionManager().propose(pos)
    assert proposal.violation is True
    assert proposal.should_update is False
    assert "no stop-loss" in proposal.reason


def test_premature_position_holds_stop():
    # Profit 2.0 on a 5.0 risk = 0.4R < 1R trigger -> never trail early.
    proposal = PositionProtectionManager().propose(
        broker_pos(entry=2300.0, sl=2295.0, price=2302.0)
    )
    assert proposal.should_update is False
    assert proposal.violation is False


def test_earned_break_even_is_proposed():
    # Profit 10.0 on 5.0 risk = 2R -> break-even protection proposed.
    proposal = PositionProtectionManager().propose(
        broker_pos(entry=2300.0, sl=2295.0, price=2310.0)
    )
    assert proposal.should_update is True
    assert proposal.method == "BREAK_EVEN"
    assert proposal.proposed_stop == pytest.approx(2300.0)
    # Never widened: the proposal moves the stop toward price only.
    assert proposal.proposed_stop > proposal.current_stop


def test_stop_is_never_widened():
    # Stop already at break-even; BE candidate (entry) would not improve it,
    # and no swing/ATR is supplied -> hold, never widen.
    proposal = PositionProtectionManager().propose(
        broker_pos(entry=2300.0, sl=2300.0, price=2310.0)
    )
    assert proposal.should_update is False


def test_structure_trail_uses_swing_when_past_break_even():
    # Once the stop is at BE, R math needs the journaled ORIGINAL stop:
    # initial risk 5.0, profit 10.0 = 2R -> structure trail allowed.
    proposal = PositionProtectionManager().propose(
        broker_pos(entry=2300.0, sl=2300.0, price=2310.0),
        last_swing=2306.0,
        initial_stop=2295.0,
    )
    assert proposal.should_update is True
    assert proposal.method == "STRUCTURE"
    assert proposal.proposed_stop > 2300.0


def test_at_break_even_without_original_stop_holds_safely():
    # Without the journal's original stop, R is unknown (0) -> hold, never
    # guess and never widen.
    proposal = PositionProtectionManager().propose(
        broker_pos(entry=2300.0, sl=2300.0, price=2310.0),
        last_swing=2306.0,
    )
    assert proposal.should_update is False
    assert proposal.violation is False


# ---------------------------------------------------------------------------
# Adapter: read-only positions fetch
# ---------------------------------------------------------------------------

class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _adapter_with_positions(raw):
    from tests.test_live_shadow import FakeMT5, demo_env

    client = FakeMT5()
    client.POSITION_TYPE_BUY = 0
    client.POSITION_TYPE_SELL = 1
    client.positions_get = MagicMock(return_value=raw)
    adapter = MT5DataAdapter(load_mt5_settings(demo_env()), client=client)
    adapter.connect()
    return adapter, client


def test_fetch_positions_maps_fields_and_preserves_symbol_case():
    raw = [_Obj(ticket=42, symbol="XAUUSDm", type=1, volume=0.02,
                price_open=2300.0, sl=2305.0, tp=2280.0,
                price_current=2298.0, profit=4.0)]
    adapter, client = _adapter_with_positions(raw)
    positions = adapter.fetch_positions()
    assert client.positions_get.call_args.kwargs["symbol"] == "XAUUSDm"
    p = positions[0]
    assert p.ticket == 42
    assert p.direction == "SHORT"
    assert p.lot_size == pytest.approx(0.02)
    assert p.stop_loss == pytest.approx(2305.0)
    client.assert_no_trades()


def test_fetch_positions_empty_and_unset_stops():
    raw = [_Obj(ticket=1, symbol="XAUUSDm", type=0, volume=0.01,
                price_open=2300.0, sl=0.0, tp=0.0,
                price_current=2301.0, profit=1.0)]
    adapter, _ = _adapter_with_positions(raw)
    p = adapter.fetch_positions()[0]
    assert p.stop_loss is None  # MT5 reports 0.0 for "no stop"
    assert p.take_profit is None

    adapter2, _ = _adapter_with_positions(None)
    assert adapter2.fetch_positions() == []
