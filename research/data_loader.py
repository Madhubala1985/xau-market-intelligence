"""Historical candle loader for the research lab.

The research lab runs OFFLINE on stored history (the live MetaTrader5 module is
Windows-only and never available in this environment). Candles are exported
once on the Windows MT5 terminal by ``scripts/export_mt5_history.py`` and land
as CSV files under ``data/raw/``:

    data/raw/XAUUSD_5M.csv
    data/raw/XAUUSD_15M.csv
    data/raw/XAUUSD_1H.csv
    ...

Standard columns (written by the exporter, read here):
    time_utc, open, high, low, close, tick_volume, spread, real_volume

``time_utc`` is an ISO-8601 UTC timestamp. If only the M1 file is present, the
loader aggregates higher timeframes with the existing TimeframeAggregator so
results stay internally consistent (06_DATA_POLICY.md: one internal timezone).

This module reads data only. It performs causal-safe validation (monotonic,
de-duplicated, OHLC-sane) and reports gaps; bad data must never silently
produce a backtest result.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.data.aggregation import TimeframeAggregator
from src.data.enums import Timeframe
from src.data.schemas import Candle

# Repo-root/data/raw by default.
DEFAULT_RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
SYMBOL = "XAUUSD"

# Map our Timeframe enum to the filename token used by the exporter.
_TF_TOKEN = {
    Timeframe.M1: "1M",
    Timeframe.M5: "5M",
    Timeframe.M15: "15M",
    Timeframe.H1: "1H",
    Timeframe.H4: "4H",
    Timeframe.D1: "1D",
}

# Timeframes that can be aggregated up from M1 when a native file is absent.
_AGGREGATABLE = (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1)

_TF_SECONDS = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}


class DataLoadError(Exception):
    """Raised when stored history is missing or fails causal-safe validation."""


@dataclass
class LoadReport:
    """What was loaded and what was wrong with it (never hidden)."""

    timeframe: Timeframe
    source: str  # "native:<path>" or "aggregated_from_M1"
    count: int
    first: Optional[datetime] = None
    last: Optional[datetime] = None
    duplicates_dropped: int = 0
    out_of_order_dropped: int = 0
    ohlc_violations: int = 0
    gaps: List[str] = field(default_factory=list)

    def summary(self) -> str:
        span = (
            f"{self.first.isoformat()} -> {self.last.isoformat()}"
            if self.first and self.last
            else "empty"
        )
        return (
            f"[{self.timeframe.value}] {self.count} candles via {self.source} "
            f"({span}); dupes={self.duplicates_dropped} "
            f"reorder={self.out_of_order_dropped} ohlc_bad={self.ohlc_violations} "
            f"gaps={len(self.gaps)}"
        )


def _parse_time(raw: str) -> datetime:
    """Parse an ISO-8601 or epoch-seconds timestamp into a UTC-aware datetime."""
    raw = raw.strip()
    if not raw:
        raise DataLoadError("empty time_utc value")
    # Epoch seconds (the exporter may write these for compactness).
    try:
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (ValueError, OverflowError):
        pass
    text = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _row_to_candle(row: Dict[str, str], tf: Timeframe) -> Candle:
    spread = row.get("spread", "").strip()
    real_volume = row.get("real_volume", "").strip()
    return Candle(
        symbol=SYMBOL,
        timeframe=tf.value,
        broker_time=_parse_time(row["time_utc"]),
        time_utc=_parse_time(row["time_utc"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        tick_volume=int(float(row.get("tick_volume", "0") or 0)),
        real_volume=int(float(real_volume)) if real_volume else None,
        spread=float(spread) if spread else None,
    )


def _validate(candles: Sequence[Candle], tf: Timeframe, report: LoadReport) -> List[Candle]:
    """Drop duplicates / out-of-order rows, count OHLC violations, flag gaps.

    Causal-safe: only de-duplication and ordering — no value smoothing, no fill.
    """
    clean: List[Candle] = []
    last_time: Optional[datetime] = None
    step = _TF_SECONDS.get(tf)
    for c in candles:
        # OHLC sanity (impossible bars are counted but kept out).
        if not (c.high >= c.open and c.high >= c.close and c.high >= c.low
                and c.low <= c.open and c.low <= c.close):
            report.ohlc_violations += 1
            continue
        if last_time is not None:
            if c.time_utc == last_time:
                report.duplicates_dropped += 1
                continue
            if c.time_utc < last_time:
                report.out_of_order_dropped += 1
                continue
            # Flag a gap larger than 2 steps during the trading week. Weekend
            # gaps (Fri->Sun) are expected and not reported.
            if step is not None:
                delta = (c.time_utc - last_time).total_seconds()
                if delta > step * 2 and last_time.weekday() not in (4, 5):
                    report.gaps.append(
                        f"{last_time.isoformat()} -> {c.time_utc.isoformat()} "
                        f"({int(delta // step)} bars)"
                    )
        clean.append(c)
        last_time = c.time_utc
    return clean


def _read_csv(path: Path, tf: Timeframe) -> List[Candle]:
    candles: List[Candle] = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        required = {"time_utc", "open", "high", "low", "close"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise DataLoadError(
                f"{path.name} missing required columns: {sorted(missing)}"
            )
        for row in reader:
            candles.append(_row_to_candle(row, tf))
    return candles


def load_timeframe(
    tf: Timeframe,
    *,
    raw_dir: Path = DEFAULT_RAW_DIR,
) -> tuple[List[Candle], LoadReport]:
    """Load one timeframe, preferring a native CSV, else aggregating from M1.

    Returns (candles, LoadReport). Raises DataLoadError if neither a native file
    nor an M1 file exists.
    """
    raw_dir = Path(raw_dir)
    native = raw_dir / f"{SYMBOL}_{_TF_TOKEN[tf]}.csv"
    if native.exists():
        raw = _read_csv(native, tf)
        raw.sort(key=lambda c: c.time_utc)
        report = LoadReport(timeframe=tf, source=f"native:{native.name}", count=0)
        clean = _validate(raw, tf, report)
        report.count = len(clean)
        if clean:
            report.first, report.last = clean[0].time_utc, clean[-1].time_utc
        return clean, report

    if tf in _AGGREGATABLE:
        m1, _ = load_timeframe(Timeframe.M1, raw_dir=raw_dir)
        agg = TimeframeAggregator().aggregate(m1, tf)
        report = LoadReport(
            timeframe=tf, source="aggregated_from_M1", count=len(agg)
        )
        if agg:
            report.first, report.last = agg[0].time_utc, agg[-1].time_utc
        return list(agg), report

    raise DataLoadError(
        f"no data for {tf.value}: expected {native} or an M1 file to aggregate "
        f"from. Run scripts/export_mt5_history.py on the Windows MT5 terminal."
    )


def load_dataset(
    timeframes: Sequence[Timeframe] = (Timeframe.M5, Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1),
    *,
    raw_dir: Path = DEFAULT_RAW_DIR,
) -> tuple[Dict[Timeframe, List[Candle]], List[LoadReport]]:
    """Load several timeframes at once. Returns (data, reports)."""
    data: Dict[Timeframe, List[Candle]] = {}
    reports: List[LoadReport] = []
    for tf in timeframes:
        candles, report = load_timeframe(tf, raw_dir=raw_dir)
        data[tf] = candles
        reports.append(report)
    return data, reports


def has_data(raw_dir: Path = DEFAULT_RAW_DIR) -> bool:
    """True if any usable candle file exists under raw_dir."""
    raw_dir = Path(raw_dir)
    return any((raw_dir / f"{SYMBOL}_{tok}.csv").exists() for tok in _TF_TOKEN.values())
