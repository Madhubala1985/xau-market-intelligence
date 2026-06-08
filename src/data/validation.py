"""Data validation engine (Task P1-003).

Validates a series of already-constructed Candle objects for the quality issues
listed in 06_DATA_POLICY.md that the schema layer cannot catch on its own:

- missing candles (gaps relative to the timeframe interval),
- duplicate candles (repeated timestamps),
- timestamp issues (out-of-order / non-monotonic),
- stale data (latest candle too old relative to a reference time),
- look-ahead leakage (candle dated in the future),
- spread anomalies (broker spread above a configured maximum),
- mismatched / mixed symbols,
- zero-volume anomalies,
- bad OHLC (defensive re-check; the Candle schema already rejects these).

Impossible OHLC and inconsistent bid/ask are rejected at construction by the
schema layer, so a valid Candle cannot carry them — the OHLC re-check here is
defense-in-depth.

Per 06_DATA_POLICY.md the final rule is: bad data must never produce a trade.
Any BLOCKING issue makes the report status NO_TRADE.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Sequence

from src.data.enums import Timeframe
from src.data.schemas import Candle


class ValidationStatus(str, Enum):
    """Overall data-quality status."""

    VALID = "VALID"
    NO_TRADE = "NO_TRADE"


class IssueSeverity(str, Enum):
    """Severity of a single validation issue."""

    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class ValidationCode(str, Enum):
    """Stable codes for each detectable data-quality problem."""

    EMPTY_INPUT = "EMPTY_INPUT"
    MIXED_SYMBOLS = "MIXED_SYMBOLS"
    SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
    MIXED_TIMEFRAMES = "MIXED_TIMEFRAMES"
    DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
    NON_MONOTONIC = "NON_MONOTONIC"
    MISSING_CANDLES = "MISSING_CANDLES"
    BAD_OHLC = "BAD_OHLC"
    SPREAD_TOO_HIGH = "SPREAD_TOO_HIGH"
    ZERO_VOLUME = "ZERO_VOLUME"
    STALE_DATA = "STALE_DATA"
    LOOK_AHEAD = "LOOK_AHEAD"


# Timeframe -> bar interval in seconds. TICK has no fixed interval.
_INTERVAL_SECONDS = {
    Timeframe.M1: 60,
    Timeframe.M5: 5 * 60,
    Timeframe.M15: 15 * 60,
    Timeframe.H1: 60 * 60,
    Timeframe.H4: 4 * 60 * 60,
    Timeframe.D1: 24 * 60 * 60,
}


@dataclass(frozen=True)
class ValidationIssue:
    """A single detected data-quality issue."""

    code: ValidationCode
    severity: IssueSeverity
    message: str
    index: Optional[int] = None

    @property
    def is_blocking(self) -> bool:
        return self.severity is IssueSeverity.BLOCKING


@dataclass(frozen=True)
class ValidationReport:
    """Result of validating a candle series."""

    status: ValidationStatus
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.status is ValidationStatus.VALID

    @property
    def blocking_issues(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.is_blocking]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if not i.is_blocking]

    def has_code(self, code: ValidationCode) -> bool:
        return any(i.code is code for i in self.issues)


@dataclass(frozen=True)
class ValidationConfig:
    """Tunable thresholds for the data validator.

    Notes:
    - max_spread is in the same unit as Candle.spread (broker points).
    - max_staleness/now drive stale-data and look-ahead checks; if either is
      absent those time-relative checks are skipped.
    - Weekend/session gaps for XAU/USD are out of scope here and are handled by
      the session engine (P2); set detect_gaps=False to disable gap detection.
    """

    expected_symbol: Optional[str] = None
    max_spread: Optional[float] = None
    max_staleness: Optional[timedelta] = None
    detect_gaps: bool = True
    block_on_zero_volume: bool = False
    allow_lookahead: bool = False


class DataValidator:
    """Validates candle series and returns a NO_TRADE status on bad data."""

    def __init__(self, config: Optional[ValidationConfig] = None) -> None:
        self._config = config or ValidationConfig()

    def validate_candles(
        self,
        candles: Sequence[Candle],
        now: Optional[datetime] = None,
    ) -> ValidationReport:
        """Validate a candle series.

        Args:
            candles: candles in chronological (oldest-first) order.
            now: reference time (UTC, tz-aware) for stale-data and look-ahead
                checks. If None, those checks are skipped.
        """
        issues: List[ValidationIssue] = []

        if not candles:
            issues.append(
                ValidationIssue(
                    ValidationCode.EMPTY_INPUT,
                    IssueSeverity.BLOCKING,
                    "no candles provided",
                )
            )
            return self._build_report(issues)

        self._check_symbols(candles, issues)
        self._check_timeframes(candles, issues)
        self._check_ohlc(candles, issues)
        self._check_spread_and_volume(candles, issues)
        self._check_sequence(candles, issues)
        self._check_freshness(candles, issues, now)

        return self._build_report(issues)

    # -- individual checks -------------------------------------------------
    def _check_symbols(self, candles: Sequence[Candle], issues: List[ValidationIssue]) -> None:
        symbols = {c.symbol for c in candles}
        if len(symbols) > 1:
            issues.append(
                ValidationIssue(
                    ValidationCode.MIXED_SYMBOLS,
                    IssueSeverity.BLOCKING,
                    f"series mixes multiple symbols: {sorted(symbols)}",
                )
            )
        expected = self._config.expected_symbol
        if expected is not None:
            expected_norm = expected.strip().upper()
            for idx, candle in enumerate(candles):
                if candle.symbol != expected_norm:
                    issues.append(
                        ValidationIssue(
                            ValidationCode.SYMBOL_MISMATCH,
                            IssueSeverity.BLOCKING,
                            f"symbol {candle.symbol!r} does not match expected "
                            f"{expected_norm!r}",
                            index=idx,
                        )
                    )
                    break

    def _check_timeframes(self, candles: Sequence[Candle], issues: List[ValidationIssue]) -> None:
        timeframes = {c.timeframe for c in candles}
        if len(timeframes) > 1:
            issues.append(
                ValidationIssue(
                    ValidationCode.MIXED_TIMEFRAMES,
                    IssueSeverity.BLOCKING,
                    f"series mixes multiple timeframes: {sorted(timeframes)}",
                )
            )

    def _check_ohlc(self, candles: Sequence[Candle], issues: List[ValidationIssue]) -> None:
        # Defensive: the Candle schema already enforces this on construction.
        for idx, c in enumerate(candles):
            if c.high < c.low or c.high < max(c.open, c.close) or c.low > min(c.open, c.close):
                issues.append(
                    ValidationIssue(
                        ValidationCode.BAD_OHLC,
                        IssueSeverity.BLOCKING,
                        "OHLC values are internally inconsistent",
                        index=idx,
                    )
                )

    def _check_spread_and_volume(
        self, candles: Sequence[Candle], issues: List[ValidationIssue]
    ) -> None:
        cfg = self._config
        for idx, c in enumerate(candles):
            if (
                cfg.max_spread is not None
                and c.spread is not None
                and c.spread > cfg.max_spread
            ):
                issues.append(
                    ValidationIssue(
                        ValidationCode.SPREAD_TOO_HIGH,
                        IssueSeverity.BLOCKING,
                        f"spread {c.spread} exceeds max {cfg.max_spread}",
                        index=idx,
                    )
                )
            if c.tick_volume == 0:
                issues.append(
                    ValidationIssue(
                        ValidationCode.ZERO_VOLUME,
                        IssueSeverity.BLOCKING
                        if cfg.block_on_zero_volume
                        else IssueSeverity.WARNING,
                        "zero tick volume",
                        index=idx,
                    )
                )

    def _check_sequence(self, candles: Sequence[Candle], issues: List[ValidationIssue]) -> None:
        cfg = self._config
        interval = self._interval_seconds(candles[0].timeframe)

        for idx in range(1, len(candles)):
            prev = candles[idx - 1].time_utc
            cur = candles[idx].time_utc
            delta = (cur - prev).total_seconds()

            if delta == 0:
                issues.append(
                    ValidationIssue(
                        ValidationCode.DUPLICATE_TIMESTAMP,
                        IssueSeverity.BLOCKING,
                        f"duplicate timestamp at {cur.isoformat()}",
                        index=idx,
                    )
                )
                continue
            if delta < 0:
                issues.append(
                    ValidationIssue(
                        ValidationCode.NON_MONOTONIC,
                        IssueSeverity.BLOCKING,
                        "candles are not in chronological order",
                        index=idx,
                    )
                )
                continue

            if cfg.detect_gaps and interval is not None:
                if delta % interval != 0:
                    # Step not aligned to the timeframe grid -> timestamp issue.
                    issues.append(
                        ValidationIssue(
                            ValidationCode.NON_MONOTONIC,
                            IssueSeverity.BLOCKING,
                            f"interval {delta:.0f}s is not a multiple of "
                            f"{interval}s",
                            index=idx,
                        )
                    )
                elif delta > interval:
                    missing = int(delta // interval) - 1
                    issues.append(
                        ValidationIssue(
                            ValidationCode.MISSING_CANDLES,
                            IssueSeverity.BLOCKING,
                            f"{missing} missing candle(s) before {cur.isoformat()}",
                            index=idx,
                        )
                    )

    def _check_freshness(
        self,
        candles: Sequence[Candle],
        issues: List[ValidationIssue],
        now: Optional[datetime],
    ) -> None:
        if now is None:
            return
        cfg = self._config

        if not cfg.allow_lookahead:
            for idx, c in enumerate(candles):
                if c.time_utc > now:
                    issues.append(
                        ValidationIssue(
                            ValidationCode.LOOK_AHEAD,
                            IssueSeverity.BLOCKING,
                            f"candle timestamp {c.time_utc.isoformat()} is in the "
                            f"future relative to {now.isoformat()}",
                            index=idx,
                        )
                    )
                    break

        if cfg.max_staleness is not None:
            last = candles[-1].time_utc
            age = now - last
            if age > cfg.max_staleness:
                issues.append(
                    ValidationIssue(
                        ValidationCode.STALE_DATA,
                        IssueSeverity.BLOCKING,
                        f"latest candle is stale by {age} (max {cfg.max_staleness})",
                        index=len(candles) - 1,
                    )
                )

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _interval_seconds(timeframe: str) -> Optional[int]:
        try:
            return _INTERVAL_SECONDS.get(Timeframe(timeframe))
        except ValueError:
            return None

    @staticmethod
    def _build_report(issues: List[ValidationIssue]) -> ValidationReport:
        blocking = any(i.is_blocking for i in issues)
        status = ValidationStatus.NO_TRADE if blocking else ValidationStatus.VALID
        return ValidationReport(status=status, issues=tuple(issues))
