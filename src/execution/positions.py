"""Open-position reconciliation (Audit F-4; 05_EXECUTION_POLICY.md).

Compares the broker's open positions (read-only via MT5DataAdapter) with the
journal's OPEN TradeRecords and classifies:

- matched:        broker position with a corresponding journal record,
- orphan_broker:  position open at the broker that the journal does not know
                  (e.g. manual trade, lost state, crashed session),
- orphan_journal: journal says a trade is open but the broker has no matching
                  position (e.g. stopped out while the system was down).

FAIL-CLOSED contract: any orphan on either side makes the report not clean,
and the demo planner refuses to plan new orders until the operator resolves
the mismatch (close the manual position, or journal the missing close).

Matching strategy:
1. Ticket match: when a journal record's notes carry "ticket=<n>" (DEMO-002
   order placement records tickets this way), match on the ticket.
2. Attribute match (fallback): same canonical symbol + direction + lot size
   (exact step) + entry price within a small tolerance.

Read-only: this module never places, modifies, or closes anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from src.broker.mt5_data_adapter import BrokerPosition
from src.data.enums import TradeOutcome
from src.data.schemas import TradeRecord

_TICKET_RE = re.compile(r"\bticket=(\d+)\b")
_LOT_TOL = 1e-9
_ENTRY_TOL = 0.05  # price tolerance for attribute matching (XAU ~ 5 cents)


def _record_ticket(record: TradeRecord) -> int | None:
    if not record.notes:
        return None
    m = _TICKET_RE.search(record.notes)
    return int(m.group(1)) if m else None


@dataclass(frozen=True)
class ReconciliationReport:
    """Outcome of one broker-vs-journal reconciliation (credential-free)."""

    matched: Tuple[Tuple[int, str], ...]      # (broker ticket, journal record_id)
    orphan_broker: Tuple[int, ...]            # broker tickets unknown to the journal
    orphan_journal: Tuple[str, ...]           # journal record_ids missing at broker
    detail: str = ""

    @property
    def clean(self) -> bool:
        return not self.orphan_broker and not self.orphan_journal

    def to_dict(self) -> dict:
        return {
            "clean": self.clean,
            "matched": [list(m) for m in self.matched],
            "orphan_broker_tickets": list(self.orphan_broker),
            "orphan_journal_records": list(self.orphan_journal),
            "detail": self.detail,
        }


class PositionReconciler:
    """Reconciles broker positions with journaled OPEN trade records."""

    def reconcile(
        self,
        broker_positions: Sequence[BrokerPosition],
        journal_records: Sequence[TradeRecord],
    ) -> ReconciliationReport:
        open_records: List[TradeRecord] = [
            r for r in journal_records if r.outcome is TradeOutcome.OPEN
        ]
        unmatched_positions = list(broker_positions)
        unmatched_records = list(open_records)
        matched: List[Tuple[int, str]] = []

        # Pass 1: ticket-based matches.
        for record in list(unmatched_records):
            ticket = _record_ticket(record)
            if ticket is None:
                continue
            pos = next((p for p in unmatched_positions if p.ticket == ticket), None)
            if pos is not None:
                matched.append((pos.ticket, record.record_id))
                unmatched_positions.remove(pos)
                unmatched_records.remove(record)

        # Pass 2: attribute-based matches for records without tickets.
        for record in list(unmatched_records):
            pos = next(
                (p for p in unmatched_positions if self._attributes_match(p, record)),
                None,
            )
            if pos is not None:
                matched.append((pos.ticket, record.record_id))
                unmatched_positions.remove(pos)
                unmatched_records.remove(record)

        report = ReconciliationReport(
            matched=tuple(matched),
            orphan_broker=tuple(p.ticket for p in unmatched_positions),
            orphan_journal=tuple(r.record_id for r in unmatched_records),
            detail=(
                f"{len(matched)} matched, {len(unmatched_positions)} broker "
                f"orphan(s), {len(unmatched_records)} journal orphan(s)"
            ),
        )
        return report

    @staticmethod
    def _attributes_match(pos: BrokerPosition, record: TradeRecord) -> bool:
        if pos.symbol.strip().upper() != record.symbol.strip().upper():
            return False
        if pos.direction != record.direction.value:
            return False
        if record.lot_size is None or abs(pos.lot_size - record.lot_size) > _LOT_TOL:
            return False
        if record.entry_price is None:
            return False
        return abs(pos.entry_price - record.entry_price) <= _ENTRY_TOL
