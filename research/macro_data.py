"""Macro feature store for the research lab (free, keyless FRED).

Gold (XAUUSD) is a macro instrument; its primary drivers are real interest rates
and the US dollar. This module pulls those series from FRED's keyless CSV
endpoint and provides an as-of join onto gold trading days.

Point-in-time discipline: the series here (10y TIPS real yield DFII10, broad
dollar DTWEXBGS) are MARKET rates — effectively not revised, unlike GDP/CPI — so
revision lookahead is negligible. We still apply a publication LAG (use macro
known strictly before the gold bar) so no value is used before it existed.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from bisect import bisect_right
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "macro"

# FRED series we use for the gold macro model.
SERIES = {
    "real_yield_10y": "DFII10",      # 10y TIPS real yield (the key gold driver)
    "broad_dollar": "DTWEXBGS",      # nominal broad US dollar index
    "breakeven_10y": "T10YIE",       # 10y breakeven inflation expectations
    "nominal_10y": "DGS10",          # 10y nominal Treasury yield
}


def _fred_csv(series_id: str) -> Dict[date, float]:
    """Fetch one FRED series via the keyless CSV endpoint -> {date: value}."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{series_id}.csv"
    if cache.exists():
        text = cache.read_text()
    else:
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode()
        cache.write_text(text)
    out: Dict[date, float] = {}
    reader = csv.reader(io.StringIO(text))
    next(reader, None)  # header
    for row in reader:
        if len(row) < 2 or row[1].strip() in ("", "."):
            continue            # FRED marks missing values with "."
        out[datetime.fromisoformat(row[0]).date()] = float(row[1])
    return out


def load_series(name: str) -> Dict[date, float]:
    return _fred_csv(SERIES[name])


def asof_join(
    target_dates: Sequence[date],
    series: Dict[date, float],
    *,
    lag_days: int = 1,
) -> List[Optional[float]]:
    """For each target date t, return the latest series value dated <= t - lag.

    `lag_days` is a calendar-day publication lag (default 1) so a value is never
    used before it was available. Missing (pre-history) -> None.
    """
    keys = sorted(series.keys())
    out: List[Optional[float]] = []
    for t in target_dates:
        cutoff = t.toordinal() - lag_days
        idx = bisect_right([k.toordinal() for k in keys], cutoff) - 1
        out.append(series[keys[idx]] if idx >= 0 else None)
    return out


def load_cot_net_spec() -> Dict[date, float]:
    """Gold COMEX speculator net position as a fraction of open interest.

    Keyed by the COT report_date (the Tuesday). Callers must as-of join with a
    publication lag (>= 4 days: the report is released the following Friday) so
    the value is never used before it was public.
    """
    path = CACHE_DIR / "COT_gold.csv"
    out: Dict[date, float] = {}
    if not path.exists():
        return out
    reader = csv.reader(io.StringIO(path.read_text()))
    next(reader, None)
    for row in reader:
        try:
            d = datetime.fromisoformat(row[0].replace("Z", "")).date()
            longs, shorts, oi = float(row[1]), float(row[2]), float(row[3])
        except (ValueError, IndexError):
            continue
        if oi > 0:
            out[d] = (longs - shorts) / oi
    return out


def build_panel(gold_dates: Sequence[date], *, lag_days: int = 1
                ) -> Tuple[Dict[str, List[Optional[float]]], List[str]]:
    """Return {feature_name: values aligned to gold_dates} for all SERIES."""
    panel: Dict[str, List[Optional[float]]] = {}
    for name in SERIES:
        panel[name] = asof_join(gold_dates, load_series(name), lag_days=lag_days)
    return panel, list(SERIES)
