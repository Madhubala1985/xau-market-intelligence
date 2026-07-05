#!/usr/bin/env python3
"""ALPHA-HUNT-001 Phase B: systematic conditional-return map of intraday XAUUSD.

Runs on the Dukascopy M1 yearly files (data/raw/dukascopy/XAUUSD_M1_*.csv).
The 2026 holdout is EXCLUDED from every scan (reserved for Phase D).

Scans (each cell reports mean forward return in bps, sem, z, N):
  1. hour-of-day drift (24 cells) — return of each UTC hour
  2. day-of-week x hour grid (120 cells)
  3. momentum/reversal spectrum on M5 and H1 — sign(past k-bar ret) ->
     future m-bar ret, non-overlapping sampling (grid of k x m)
  4. session blocks — Asia/London/NY block returns
  5. vol conditioning — past-24h realized vol tercile x past-24h ret sign ->
     next-4h return (H1)

Honesty rules: all cells counted for a single Bonferroni correction; z uses
non-overlapping samples; results are a MAP for hypothesis formation — nothing
here is an edge until it survives Phase C/D (cost-stressed sim + random
baseline + 2026 holdout).

Output: reports/research/intraday_scan.md (ranked by |z|).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DUKA = ROOT / "data" / "raw" / "dukascopy"
OUT = ROOT / "reports" / "research" / "intraday_scan.md"
HOLDOUT_START = pd.Timestamp("2026-01-01", tz="UTC")

BPS = 1e4


def load_m1() -> pd.DataFrame:
    files = sorted(DUKA.glob("XAUUSD_M1_*.csv"))
    if not files:
        sys.exit("no XAUUSD M1 files; run scripts/fetch_dukascopy.py first")
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates("time").sort_values("time").set_index("time")
    # drop Dukascopy's flat zero-volume filler bars on closed market hours
    df = df[df["volume"] > 0]
    n_all = len(df)
    df = df[df.index < HOLDOUT_START]
    print(f"loaded {n_all} M1 bars; {len(df)} after excluding 2026 holdout "
          f"({df.index[0]} .. {df.index[-1]})")
    return df


def resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    o = df["open"].resample(rule).first()
    h = df["high"].resample(rule).max()
    lo = df["low"].resample(rule).min()
    c = df["close"].resample(rule).last()
    out = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}).dropna()
    return out


def cell(rets: np.ndarray, name: str, group: str) -> dict:
    rets = rets[np.isfinite(rets)]
    n = len(rets)
    if n < 30:
        return {"group": group, "cell": name, "n": n, "mean_bps": np.nan,
                "sem_bps": np.nan, "z": np.nan}
    m = rets.mean() * BPS
    sem = rets.std(ddof=1) / np.sqrt(n) * BPS
    return {"group": group, "cell": name, "n": n, "mean_bps": m,
            "sem_bps": sem, "z": m / sem if sem > 0 else np.nan}


def scan_hour_of_day(h1: pd.DataFrame) -> list[dict]:
    r = np.log(h1["close"] / h1["open"])
    return [cell(r[r.index.hour == h].to_numpy(), f"hour={h:02d}", "hour_of_day")
            for h in range(24)]


def scan_dow_hour(h1: pd.DataFrame) -> list[dict]:
    r = np.log(h1["close"] / h1["open"])
    out = []
    for dow in range(5):
        for h in range(24):
            mask = (r.index.dayofweek == dow) & (r.index.hour == h)
            out.append(cell(r[mask].to_numpy(), f"dow={dow},hour={h:02d}", "dow_hour"))
    return out


def scan_momentum(bars: pd.DataFrame, tf: str) -> list[dict]:
    c = np.log(bars["close"].to_numpy())
    out = []
    for k in (1, 3, 6, 12, 24, 48):
        past = c[k:] - c[:-k]  # past k-bar return ending at bar i (index i = k..)
        for m in (1, 3, 6, 12, 24):
            # future m-bar return starting at bar i
            fut = c[k + m:] - c[k:-m]
            p = past[: len(fut)]
            # non-overlapping future windows
            idx = np.arange(0, len(fut), m)
            p_s, f_s = p[idx], fut[idx]
            up = f_s[p_s > 0]
            dn = f_s[p_s < 0]
            # momentum spread: future ret after up-move minus after down-move
            n = min(len(up), len(dn))
            if n < 30:
                continue
            spread = np.concatenate([up, -dn])  # >0 => momentum, <0 => reversal
            out.append(cell(spread, f"{tf} k={k} m={m}", f"momentum_{tf}"))
    return out


def scan_sessions(m1: pd.DataFrame) -> list[dict]:
    c = m1["close"]
    daily = []
    blocks = {"asia_00_07": (0, 7), "london_07_12": (7, 12),
              "ny_12_17": (12, 17), "late_17_21": (17, 21)}
    out = []
    for name, (a, b) in blocks.items():
        h = c[(c.index.hour >= a) & (c.index.hour < b)]
        g = h.groupby(h.index.date)
        r = np.log(g.last() / g.first()).to_numpy()
        out.append(cell(r, name, "session_block"))
    return out


def scan_vol_conditioning(h1: pd.DataFrame) -> list[dict]:
    c = np.log(h1["close"])
    ret1 = c.diff()
    vol24 = ret1.rolling(24).std()
    past24 = c.diff(24)
    fut4 = c.shift(-4) - c
    df = pd.DataFrame({"vol": vol24, "past": past24, "fut": fut4}).dropna()
    # non-overlapping 4h windows
    df = df.iloc[::4]
    terciles = df["vol"].quantile([1 / 3, 2 / 3]).to_numpy()
    out = []
    for vname, vmask in (
        ("lowvol", df["vol"] <= terciles[0]),
        ("midvol", (df["vol"] > terciles[0]) & (df["vol"] <= terciles[1])),
        ("highvol", df["vol"] > terciles[1]),
    ):
        for sname, smask in (("after_up", df["past"] > 0), ("after_dn", df["past"] < 0)):
            sub = df.loc[vmask & smask, "fut"].to_numpy()
            out.append(cell(sub, f"{vname},{sname}", "vol_conditioning"))
    return out


def main() -> None:
    m1 = load_m1()
    m5 = resample(m1, "5min")
    h1 = resample(m1, "1h")
    print(f"M5 bars: {len(m5)}; H1 bars: {len(h1)}")

    cells: list[dict] = []
    cells += scan_hour_of_day(h1)
    cells += scan_dow_hour(h1)
    cells += scan_momentum(m5, "M5")
    cells += scan_momentum(h1, "H1")
    cells += scan_sessions(m1)
    cells += scan_vol_conditioning(h1)

    res = pd.DataFrame([c for c in cells if np.isfinite(c.get("z", np.nan))])
    n_tests = len(res)
    # Bonferroni: two-sided alpha 0.05 across all cells
    from scipy.stats import norm
    z_bonf = float(norm.ppf(1 - 0.025 / n_tests))
    res["significant"] = res["z"].abs() >= z_bonf
    res = res.sort_values("z", key=lambda s: s.abs(), ascending=False)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        f.write("# Intraday conditional-return map (Phase B, ALPHA-HUNT-001)\n\n")
        f.write(f"Sample: Dukascopy M1 2019-01..2025-12 (2026 = untouched holdout).\n")
        f.write(f"Cells tested: {n_tests}; Bonferroni z threshold (alpha=0.05, "
                f"two-sided): **{z_bonf:.2f}**.\n")
        f.write("Return unit: bps (1bp = 0.01%). MAP ONLY — survivors go to "
                "Phase C/D (costs, random baseline, holdout).\n\n")
        f.write("## All cells ranked by |z|\n\n")
        f.write("| group | cell | n | mean bps | sem | z | sig |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for _, r in res.iterrows():
            f.write(f"| {r['group']} | {r['cell']} | {r['n']} | {r['mean_bps']:+.2f} "
                    f"| {r['sem_bps']:.2f} | {r['z']:+.2f} "
                    f"| {'**YES**' if r['significant'] else ''} |\n")
    sig = res[res["significant"]]
    print(f"\n{n_tests} cells, Bonferroni z>={z_bonf:.2f}, significant: {len(sig)}")
    print(sig.head(25).to_string(index=False))
    print(f"\nreport: {OUT}")


if __name__ == "__main__":
    main()
