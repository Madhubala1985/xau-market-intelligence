"""News-risk guard (Audit F-5; NEWS-001; 14_SESSION_KILLZONE_POLICY.md).

There is NO live economic-calendar HTTP feed in this system, and this module
does not pretend one exists. It provides a provider ARCHITECTURE with two
honest sources today:

1. A manual block file (control/NEWS_BLOCK): the supervising operator engages
   it before a known news window (touch the file) and releases it after
   (delete the file). Works from any terminal, like the kill switch.
2. A static calendar provider (configs/news_windows.json): a local,
   user-maintained list of UTC windows:
       {"windows": [{"start_utc": "...", "end_utc": "...", "label": "...",
                     "impact": "HIGH|MEDIUM", "category": "CPI|NFP|FOMC|..."}]}
   Maintaining this file — even with an empty list — is an explicit operator
   assertion that news windows for the period have been reviewed.
   `impact` defaults to HIGH when omitted (fail-safe); gold-relevant
   categories are listed in GOLD_NEWS_CATEGORIES.

A future REAL feed implements NewsProvider.fetch_windows() (task NEWS-001
remains open until a reliable source + key exists; nothing is faked until
then).

Status model (NEWS-001):
- NEWS_BLOCK             manual operator block            -> entries blocked
- NEWS_ACTIVE            inside a HIGH-impact window      -> entries blocked
- NEWS_HIGH_IMPACT_SOON  HIGH-impact window starts within
                         the lead time (default 30 min)   -> risk reduced
- (MEDIUM-impact active windows also reduce instead of block)
- NEWS_CLEAR             calendar reviewed, nothing near  -> normal
- NEWS_UNKNOWN           no usable source                 -> entries blocked
                                                             (fail closed)
Open positions are ALWAYS still managed regardless of news state — the
session's stop-management path does not consult this guard.

This module performs no trading and holds no credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Tuple, Union

DEFAULT_NEWS_BLOCK_PATH = "control/NEWS_BLOCK"
DEFAULT_CALENDAR_PATH = "configs/news_windows.json"

# Gold-relevant USD high-impact categories (documentation + provider hint).
GOLD_NEWS_CATEGORIES = (
    "CPI", "PPI", "NFP", "UNEMPLOYMENT", "FOMC", "FED_RATE_DECISION",
    "FED_SPEECH", "GDP", "RETAIL_SALES", "ISM_PMI", "JOBLESS_CLAIMS",
    "USD_HIGH_IMPACT",
)


class NewsStatus:
    CLEAR = "NEWS_CLEAR"
    BLOCK = "NEWS_BLOCK"
    UNKNOWN = "NEWS_UNKNOWN"
    HIGH_IMPACT_SOON = "NEWS_HIGH_IMPACT_SOON"
    ACTIVE = "NEWS_ACTIVE"


@dataclass(frozen=True)
class NewsWindow:
    start_utc: datetime
    end_utc: datetime
    label: str = ""
    impact: str = "HIGH"      # HIGH blocks; MEDIUM reduces (fail-safe default)
    category: str = ""        # e.g. CPI / NFP / FOMC (GOLD_NEWS_CATEGORIES)

    def contains(self, now: datetime) -> bool:
        return self.start_utc <= now <= self.end_utc


class NewsProvider(Protocol):
    """A calendar source. A future real feed implements this (NEWS-001)."""

    def fetch_windows(self, now: datetime) -> Optional[List[NewsWindow]]:
        """Windows around `now`, or None when the source is unusable."""
        ...


@dataclass(frozen=True)
class NewsRiskState:
    """News-risk assessment at one moment (credential-free)."""

    known: bool          # False == no usable source; order paths must fail closed
    risky: bool          # True == manual block or HIGH-impact window active
    source: str          # "manual" | "calendar" | "provider" | "none"
    detail: str
    status: str = ""     # one of NewsStatus.* (terminal display)
    caution: bool = False  # HIGH impact soon / MEDIUM active: reduce risk

    @property
    def blocks_orders(self) -> bool:
        """Order planning must block when risky OR when the state is unknown."""
        return self.risky or not self.known


class StaticCalendarProvider:
    """The operator-maintained JSON calendar (the only truthful source today)."""

    def __init__(self, calendar_path: Union[str, Path] = DEFAULT_CALENDAR_PATH):
        self._path = Path(calendar_path)

    def fetch_windows(self, now: datetime) -> Optional[List[NewsWindow]]:
        path = self._path
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data["windows"]
            windows: List[NewsWindow] = []
            for item in raw:
                start, end = _parse_pair(item["start_utc"], item["end_utc"])
                impact = str(item.get("impact", "HIGH")).strip().upper()
                if impact not in ("HIGH", "MEDIUM", "LOW"):
                    impact = "HIGH"  # unknown impact is treated as HIGH
                windows.append(NewsWindow(
                    start_utc=start, end_utc=end,
                    label=str(item.get("label", "")),
                    impact=impact,
                    category=str(item.get("category", "")).strip().upper(),
                ))
            return windows
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            # Malformed calendar must read as "no usable source", never as
            # "no news risk".
            return None


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


class NewsRiskGuard:
    """Assesses news risk from the manual block file and a calendar provider."""

    def __init__(
        self,
        *,
        block_path: Union[str, Path] = DEFAULT_NEWS_BLOCK_PATH,
        calendar_path: Union[str, Path] = DEFAULT_CALENDAR_PATH,
        provider: Optional[NewsProvider] = None,
        high_impact_lead: timedelta = timedelta(minutes=30),
    ) -> None:
        self._block_path = Path(block_path)
        self._calendar_path = Path(calendar_path)
        self._provider = provider or StaticCalendarProvider(calendar_path)
        self._lead = high_impact_lead

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
                status=NewsStatus.BLOCK,
            )

        # 2) Calendar provider (static file today; real feed = NEWS-001).
        windows = self._provider.fetch_windows(now)
        if windows is None:
            return NewsRiskState(
                known=False, risky=False, source="none",
                detail="no news source available (no manual block, no "
                       "calendar); order planning must treat this as blocked",
                status=NewsStatus.UNKNOWN,
            )

        active = [w for w in windows if w.contains(now)]
        high_active = [w for w in active if w.impact == "HIGH"]
        if high_active:
            hit = high_active[0]
            return NewsRiskState(
                known=True, risky=True, source="calendar",
                detail=(
                    f"inside HIGH-impact window "
                    f"{hit.category or hit.label or 'unlabeled'} "
                    f"({hit.start_utc.isoformat()} .. {hit.end_utc.isoformat()})"
                ),
                status=NewsStatus.ACTIVE,
            )
        medium_active = [w for w in active if w.impact == "MEDIUM"]
        if medium_active:
            hit = medium_active[0]
            return NewsRiskState(
                known=True, risky=False, source="calendar",
                detail=(
                    f"inside MEDIUM-impact window "
                    f"{hit.category or hit.label or 'unlabeled'}; risk reduced"
                ),
                status=NewsStatus.ACTIVE, caution=True,
            )
        upcoming_high = [
            w for w in windows
            if w.impact == "HIGH" and now < w.start_utc <= now + self._lead
        ]
        if upcoming_high:
            hit = min(upcoming_high, key=lambda w: w.start_utc)
            minutes = int((hit.start_utc - now).total_seconds() // 60)
            return NewsRiskState(
                known=True, risky=False, source="calendar",
                detail=(
                    f"HIGH-impact {hit.category or hit.label or 'event'} in "
                    f"~{minutes} min; risk reduced"
                ),
                status=NewsStatus.HIGH_IMPACT_SOON, caution=True,
            )
        return NewsRiskState(
            known=True, risky=False, source="calendar",
            detail=f"no active window among {len(windows)} calendar entries",
            status=NewsStatus.CLEAR,
        )
