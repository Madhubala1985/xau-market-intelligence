"""Trade journal (Task P9-001).

Logs every trade and no-trade decision durably and is restart-safe: a new journal
instance pointed at the same file reloads all prior entries. References
06_DATA_POLICY.md (data storage) and 05_EXECUTION_POLICY.md (TRADE_LOGGED).

Storage is append-only JSON Lines; each line wraps a TradeDecision or TradeRecord
(reusing their pydantic serialization) with a logged_at_utc timestamp. The journal
only ever writes those credential-free schemas, so credentials are never logged.

The default path lives under the gitignored runtime area (logs/); tests use a
temporary path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from src.data.schemas import TradeDecision, TradeRecord

DEFAULT_JOURNAL_PATH = "logs/trade_journal.jsonl"


class EntryKind(str, Enum):
    DECISION = "decision"
    RECORD = "record"


@dataclass(frozen=True)
class JournalEntry:
    """One persisted journal entry."""

    kind: EntryKind
    logged_at_utc: datetime
    decision: Optional[TradeDecision] = None
    record: Optional[TradeRecord] = None

    @property
    def payload(self) -> Union[TradeDecision, TradeRecord]:
        return self.decision if self.kind is EntryKind.DECISION else self.record


class TradeJournal:
    """Append-only, restart-safe journal of decisions and trade records."""

    def __init__(self, path: Union[str, Path] = DEFAULT_JOURNAL_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    # -- logging -----------------------------------------------------------
    def log_decision(self, decision: TradeDecision) -> JournalEntry:
        """Persist a trade or no-trade decision."""
        logged_at = self._append(EntryKind.DECISION, decision.model_dump(mode="json"))
        return JournalEntry(EntryKind.DECISION, logged_at, decision=decision)

    def log_record(self, record: TradeRecord) -> JournalEntry:
        """Persist a trade outcome record."""
        logged_at = self._append(EntryKind.RECORD, record.model_dump(mode="json"))
        return JournalEntry(EntryKind.RECORD, logged_at, record=record)

    def _append(self, kind: EntryKind, data: dict) -> datetime:
        logged_at = datetime.now(timezone.utc)
        line = {
            "kind": kind.value,
            "logged_at_utc": logged_at.isoformat(),
            "data": data,
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        return logged_at

    # -- reading (restart-safe reload) ------------------------------------
    def entries(self) -> List[JournalEntry]:
        """Reload all entries from disk (empty list if the file is absent)."""
        if not self._path.exists():
            return []
        out: List[JournalEntry] = []
        for raw in self._path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            obj = json.loads(raw)
            kind = EntryKind(obj["kind"])
            logged_at = datetime.fromisoformat(obj["logged_at_utc"])
            data = obj["data"]
            if kind is EntryKind.DECISION:
                out.append(
                    JournalEntry(
                        kind, logged_at, decision=TradeDecision.model_validate(data)
                    )
                )
            else:
                out.append(
                    JournalEntry(
                        kind, logged_at, record=TradeRecord.model_validate(data)
                    )
                )
        return out

    def decisions(self) -> List[TradeDecision]:
        return [e.decision for e in self.entries() if e.kind is EntryKind.DECISION]

    def records(self) -> List[TradeRecord]:
        return [e.record for e in self.entries() if e.kind is EntryKind.RECORD]

    def __len__(self) -> int:
        return len(self.entries())
