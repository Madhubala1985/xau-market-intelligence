"""Setup 5 (v1): post-spike chop avoidance — a NO-TRADE FILTER, not a setup.

After a violent spike (a candle far larger than baseline), price often chops in
an overlapping range where stops get picked off in both directions. This filter
suppresses entries while that condition holds. It is measured as the EXPECTANCY
UPLIFT it gives another setup (run the setup with and without the filter and
compare), not as a standalone edge.

MECHANICAL DEFINITION (v1 — frozen): index `i` is "post-spike chop" if, within
the last `chop_window` bars before i, there was a spike candle (range >=
spike_factor x the baseline range), AND the bars since the spike are overlapping
and non-progressing: the close-to-close net move since the spike is small
relative to the spike's range (<= drift_ratio), while the bars stay inside an
overlapping band.
"""

from __future__ import annotations

from typing import Callable, Sequence, Tuple

from research.metrics import Metrics, compute_metrics
from research.setups._common import baseline_range
from src.data.schemas import Candle


def post_spike_chop_block(
    candles: Sequence[Candle],
    i: int,
    *,
    baseline_lookback: int = 20,
    spike_factor: float = 3.0,
    chop_window: int = 4,
    drift_ratio: float = 0.5,
) -> bool:
    """True if entries at index i should be suppressed (post-spike chop)."""
    if i < chop_window + 2:
        return False
    for s in range(i - chop_window, i):
        baseline = baseline_range(candles, s, baseline_lookback)
        if baseline is None:
            continue
        spike = candles[s]
        if (spike.high - spike.low) < spike_factor * baseline:
            continue
        # Bars after the spike up to i: small net drift => chop.
        after = candles[s + 1:i + 1]
        if not after:
            continue
        net = abs(after[-1].close - spike.close)
        if net <= drift_ratio * (spike.high - spike.low):
            return True
    return False


def make_filter(**kwargs) -> Callable[[Sequence[Candle], int], bool]:
    """Return a filter callable bound for the harness's `entry_filter`."""
    return lambda candles, i: post_spike_chop_block(candles, i, **kwargs)


def measure_uplift(
    setup,
    data,
    *,
    filter_kwargs: dict | None = None,
) -> Tuple[Metrics, Metrics]:
    """Return (without_filter, with_filter) metrics for `setup` over `data`.

    Imported lazily to avoid a circular import with the harness.
    """
    from research.harness import run_setup

    base = run_setup(setup, data)
    filtered = run_setup(setup, data, entry_filter=make_filter(**(filter_kwargs or {})))
    return base.metrics, filtered.metrics
