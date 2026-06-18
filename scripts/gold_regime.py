#!/usr/bin/env python3
"""Print the current gold macro regime + suggested exposure (advisory risk dial).

Reads cached FRED real-yield (DFII10) and broad-dollar (DTWEXBGS) series. This is
ADVISORY ONLY — it does not trade. It is a risk dial for a gold position you would
otherwise hold: lower exposure in tightening regimes to cut drawdown. It is NOT a
return edge (see 30_RESEARCH_FINDINGS.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from research.macro_data import load_series  # noqa: E402
from research.regime import gold_macro_regime  # noqa: E402


def main() -> int:
    ry_map = load_series("real_yield_10y")
    dx_map = load_series("broad_dollar")
    if not ry_map or not dx_map:
        print("No cached macro data. Fetch first (FRED keyless CSV is in research/macro_data).")
        return 2
    ry = [ry_map[d] for d in sorted(ry_map)]
    dx = [dx_map[d] for d in sorted(dx_map)]
    reading = gold_macro_regime(ry, dx)

    print("=" * 64)
    print("GOLD MACRO REGIME — advisory risk dial (NOT a return edge)")
    print("=" * 64)
    print(f"  {reading.summary()}")
    print()
    if reading.label == "TIGHTENING":
        print("  Real yields AND the dollar are rising. Historically gold's drift")
        print("  is ~0% at full risk here -> consider REDUCED exposure to cut drawdown.")
    elif reading.label == "EASING":
        print("  Real yields AND the dollar falling -> the supportive regime for gold.")
    else:
        print("  Mixed drivers -> no strong regime signal; hold normal exposure.")
    print()
    print("  Reminder: this lowers drawdown, it does NOT add return. No daily")
    print("  tradeable alpha was found (30_RESEARCH_FINDINGS.md). Do not auto-trade it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
