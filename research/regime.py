"""Gold macro regime — the one defensible artifact from the research arc.

NOT alpha. The research (30_RESEARCH_FINDINGS.md) showed no daily tradeable edge
beats holding gold. The ONE robust, economically-grounded effect is: when the 10y
real yield AND the broad dollar are both RISING ("tightening"), gold's forward
drift collapses to ~0% at full risk. Avoiding/derisking those periods cuts
drawdown (it does NOT add return — it is a risk dial, not a return edge).

To avoid the single-lookback fragility found in testing, the regime is an
ENSEMBLE vote across several lookbacks. Output is a suggested exposure in [0,1],
meant to scale a gold position you would otherwise hold — advisory only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


def _trend_sign(values: Sequence[float], n: int) -> int:
    """+1 if the series rose over the last n observations, -1 if fell, else 0."""
    if len(values) <= n:
        return 0
    d = values[-1] - values[-1 - n]
    return 1 if d > 0 else (-1 if d < 0 else 0)


@dataclass(frozen=True)
class RegimeReading:
    label: str            # EASING | MIXED | TIGHTENING
    exposure: float       # suggested gold exposure in [0, 1] (risk dial)
    tightening_votes: int
    easing_votes: int
    lookbacks: tuple
    detail: str

    def summary(self) -> str:
        return (f"regime={self.label}  suggested_exposure={self.exposure:.0%}  "
                f"(tighten {self.tightening_votes}/{len(self.lookbacks)}, "
                f"ease {self.easing_votes}/{len(self.lookbacks)})  {self.detail}")


def gold_macro_regime(
    real_yield: Sequence[float],
    dollar: Sequence[float],
    *,
    lookbacks: Sequence[int] = (20, 40, 60),
) -> RegimeReading:
    """Ensemble regime from real-yield and dollar trends across lookbacks.

    Exposure = 1 - (tightening_votes / n_lookbacks): full gold exposure when no
    lookback says tightening, scaled down as more agree we're tightening.
    """
    tighten = sum(1 for n in lookbacks
                  if _trend_sign(real_yield, n) > 0 and _trend_sign(dollar, n) > 0)
    ease = sum(1 for n in lookbacks
               if _trend_sign(real_yield, n) < 0 and _trend_sign(dollar, n) < 0)
    exposure = max(0.0, 1.0 - tighten / len(lookbacks))
    if tighten >= max(2, len(lookbacks) - 1):
        label = "TIGHTENING"
    elif ease >= max(2, len(lookbacks) - 1):
        label = "EASING"
    else:
        label = "MIXED"
    detail = (f"real_yield {real_yield[-1]:.2f} (Δ20={real_yield[-1]-real_yield[-21]:+.2f}); "
              f"dollar {dollar[-1]:.1f} (Δ20={dollar[-1]-dollar[-21]:+.1f})"
              if len(real_yield) > 21 and len(dollar) > 21 else "insufficient history")
    return RegimeReading(label, exposure, tighten, ease, tuple(lookbacks), detail)
