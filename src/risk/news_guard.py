"""News-risk guard (Audit F-5; 14_SESSION_KILLZONE_POLICY.md).

There is NO real economic-calendar feed in this system yet, and this module
does not pretend one exists. It provides two honest sources:

1. A manual block file (control/NEWS_BLOCK): the supervising operator engages
   it before a known news window (touch the file) and releases it after
   (delete the file). Works from any terminal, like the kill switch.
2. An optional static calendar file (configs/news_windows.json): a local,
   user-maintained list of UTC windows:
       {"windows": [{"start_utc": "...", "end_utc": "...", "label": "..."}]}
   Maintaining this file — even with an empty list — is an explicit operator
   assertion that news windows for the period have been reviewed.

Fail-closed contract:
- assess() reports `known=False` when NEITHER source is available (no manual
  block and no parseable calendar). Order-planning code (DemoTradePlanner)
  must treat unknown news state as a BLOCK. Shadow mode may continue analyzing
  (it never sends orders) but the risk flag is only raised when known.
- A manual block always wins, regardless of the calendar.
- A malformed calendar file is treated as missing (unknown), never as "no news".

This module performs no trading and holds no credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Union

DEFAULT_NEWS_BLOCK_PATH = "control/NEWS_BLOCK"
DEFAULT_CALENDAR_PATH = "configs/news_windows.json"


@dataclass(frozen=True)
class NewsWindow:
    start_utc: datetime
    end_utc: datetime
    label: str = ""

    def contains(self, now: datetime) -> bool:
        return self.start_utc <= now <= self.end_utc


@dataclass(frozen=True)
class NewsRiskState:
    """News-risk assessment at one moment (credential-free)."""

    known: bool          # False == no usable source; order paths must fail closed
    risky: bool          # True == inside a news window or manually blocked
    source: str          # "manual" | "calendar" | "none"
    detail: str

    @property
    def blocks_orders(self) -> bool:
        """Order planning must block when risky OR when the state is unknown."""
        return self.risky or not self.known


class NewsRiskGuard:
    """Assesses news risk from the manual block file and the static calendar."""

    def __init__(
        self,
        *,
        block_path: Union[str, Path] = DEFAULT_NEWS_BLOCK_PATH,
        calendar_path: Union[str, Path] = DEFAULT_CALENDAR_PATH,
    ) -> None:
        self._block_path = Path(block_path)
        self._calendar_path = Path(calendar_path)

    # -- manual block --------------------------------------------------------
    @property
    def manually_blocked(self) -> bool:
        return self._block_path.exists()

    def engage_manual_block(self, reason: str = "") -> None:
        self._block_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).isoformat()
        self._block_path.write_text(
            f"engaged_at_utc={stamp}\nreason={reason}\n", encoding="utf-8"
        )

    def release_manual_block(self) -> None:
        self._block_path.unlink(missing_ok=True)

    # -- assessment ------------------------------------------------------------
    def assess(self, now: datetime) -> NewsRiskState:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware (UTC)")
        now = now.astimezone(timezone.utc)

        # 1) Manual block always wins.
        if self.manually_blocked:
            return NewsRiskState(
                known=True, risky=True, source="manual",
                detail="manual news block engaged (control file present)",
            )

        # 2) Static calendar, if present and parseable.
        windows = self._load_calendar()
        if windows is not None:
            hit = next((w for w in windows if w.contains(now)), None)
            if hit is not None:
                return NewsRiskState(
                    known=True, risky=True, source="calendar",
                    detail=f"inside news window {hit.label or 'unlabeled'} "
                           f"({hit.start_utc.isoformat()} .. {hit.end_utc.isoformat()})",
                )
            return NewsRiskState(
                known=True, risky=False, source="calendar",
                detail=f"no active window among {len(windows)} calendar entries",
            )

        # 3) No source: honestly unknown. Order paths must fail closed.
        return NewsRiskState(
            known=False, risky=False, source="none",
            detail="no news source available (no manual block, no calendar); "
                   "order planning must treat this as blocked",
        )

    # -- calendar parsing --------------------------------------------------------
    def _load_calendar(self) -> Optional[List[NewsWindow]]:
        """Parse the calendar file; None when absent or malformed (fail-closed)."""
        path = self._calendar_path
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data["windows"]
            windows: List[NewsWindow] = []
            for item in raw:
                start, end = self._parse_pair(item["start_utc"], item["end_utc"])
                windows.append(
                    NewsWindow(start_utc=start, end_utc=end,
                               label=str(item.get("label", "")))
                )
            return windows
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            # Malformed calendar must read as "no usable source", never as
            # "no news risk".
            return None

    @staticmethod
    def _parse_pair(start_raw: str, end_raw: str) -> Tuple[datetime, datetime]:
        start = datetime.fromisoformat(str(start_raw))
        end = datetime.fromisoformat(str(end_raw))
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("calendar timestamps must be timezone-aware")
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        if end < start:
            raise ValueError("window end before start")
        return start, end
