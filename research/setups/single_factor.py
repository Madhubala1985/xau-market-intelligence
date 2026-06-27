"""Single-factor isolation setups — close the "never isolated" gap.

Each factor gets ONE minimal mechanical rule: when the factor appears, enter
MARKET next bar in the factor's implied direction, with a fixed ATR stop and a
fixed R-multiple target. NO other confluence, NO composites. The question is
narrow and identical for every factor: *does this factor alone beat a random
entry with the same stop/target?*

Implied direction:
  FVG / order block / supply-demand zone -> the zone's bias (bullish=long).
  displacement -> continuation (bullish candle = long).
  CHOCH -> the break direction.
  liquidity sweep -> the rejection bias (swept a low & rejected up = long).

All signals use the existing engines unchanged; indices are the engines' own
"known at" indices (causal). A cooldown prevents stacking the same cluster.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Sequence, Tuple

from research.setups._common import (
    baseline_range,
    day_midnight,
    is_bear_displacement,
    is_bull_displacement,
    utc_day,
)
from research.setups.base import EntryIntent, MarketData
from research.setups.donchian_breakout_trend import _atr
from src.data.enums import Direction, Timeframe
from src.data.schemas import Candle
from src.liquidity.liquidity_map import LiquidityMapEngine
from src.liquidity.sweep import SweepEngine
from src.structure.market_structure import (
    Bias,
    MarketStructureEngine,
    StructureEventType,
)
from src.structure.zones import ZoneEngine

Signal = Tuple[int, Direction]  # (arm_index, direction)


def _dir(bias: Bias) -> Direction:
    return Direction.LONG if bias is Bias.BULLISH else Direction.SHORT


# --- one signal generator per factor (reusing the project engines) ----------

def fvg_signals(candles: Sequence[Candle]) -> List[Signal]:
    return [(z.created_index, _dir(z.bias)) for z in ZoneEngine().find_fvgs(candles)
            if z.bias is not Bias.NEUTRAL]


def order_block_signals(candles: Sequence[Candle]) -> List[Signal]:
    return [(z.created_index, _dir(z.bias))
            for z in ZoneEngine().find_order_blocks(candles) if z.bias is not Bias.NEUTRAL]


def supply_demand_signals(candles: Sequence[Candle]) -> List[Signal]:
    return [(z.created_index, _dir(z.bias))
            for z in ZoneEngine().find_supply_demand(candles) if z.bias is not Bias.NEUTRAL]


def displacement_signals(candles: Sequence[Candle], *, factor: float = 1.5,
                         lookback: int = 20) -> List[Signal]:
    out: List[Signal] = []
    for i in range(lookback, len(candles)):
        base = baseline_range(candles, i, lookback)
        if base is None:
            continue
        if is_bull_displacement(candles[i], base, factor):
            out.append((i, Direction.LONG))
        elif is_bear_displacement(candles[i], base, factor):
            out.append((i, Direction.SHORT))
    return out


def choch_signals(candles: Sequence[Candle], *, swing_strength: int = 2) -> List[Signal]:
    events = MarketStructureEngine(strength=swing_strength).analyze(candles).events
    return [(e.index, _dir(e.bias)) for e in events
            if e.event_type is StructureEventType.CHOCH and e.bias is not Bias.NEUTRAL]


def sweep_signals(candles: Sequence[Candle], *, swing_strength: int = 2) -> List[Signal]:
    levels = LiquidityMapEngine().build(candles)
    # Isolate the raw sweep: no displacement/structure confirmation bundled in.
    engine = SweepEngine(swing_strength=swing_strength,
                         require_displacement=False, require_structure=False)
    out: List[Signal] = []
    for ev in engine.detect(candles, levels):
        idx = ev.confirmed_index if ev.confirmed_index is not None else ev.sweep_index
        if ev.rejection_bias is not Bias.NEUTRAL:
            out.append((idx, _dir(ev.rejection_bias)))
    return out


FACTORS: Dict[str, Callable[[Sequence[Candle]], List[Signal]]] = {
    "fvg": fvg_signals,
    "liquidity_sweep": sweep_signals,
    "displacement": displacement_signals,
    "choch": choch_signals,
    "order_block": order_block_signals,
    "supply_demand": supply_demand_signals,
}


class SingleFactorSetup:
    """Generic minimal-rule wrapper: factor signal -> MARKET entry, ATR stop, RR target."""

    version = "v1"

    def __init__(self, factor: str, *, exec_timeframe: Timeframe = Timeframe.H1,
                 atr_len: int = 14, stop_atr: float = 1.5, rr: float = 2.0,
                 cooldown: int = 6) -> None:
        if factor not in FACTORS:
            raise ValueError(f"unknown factor {factor!r}")
        self.factor = factor
        self.name = f"factor_{factor}"
        self._signal_fn = FACTORS[factor]
        self.exec_timeframe = exec_timeframe
        self.atr_len = atr_len
        self.stop_atr = stop_atr
        self.rr = rr
        self.cooldown = cooldown

    def rules(self) -> Dict[str, object]:
        return {"name": self.name, "version": self.version, "factor": self.factor,
                "exec_timeframe": self.exec_timeframe.value, "atr_len": self.atr_len,
                "stop_atr": self.stop_atr, "rr": self.rr, "cooldown": self.cooldown,
                "entry": "MARKET next bar in factor's implied direction",
                "confluence": "NONE (single factor only)", "session": "ANY"}

    def scan(self, data: MarketData) -> List[EntryIntent]:
        candles = data.tf(self.exec_timeframe)
        intents: List[EntryIntent] = []
        last = -10 ** 9
        for i, direction in sorted(self._signal_fn(candles)):
            if i < self.atr_len or i + 1 >= len(candles) or i - last < self.cooldown:
                continue
            atr = _atr(candles, i, self.atr_len)
            if atr is None or atr <= 0:
                continue
            ref = candles[i + 1].open
            if direction is Direction.LONG:
                stop, target = ref - self.stop_atr * atr, ref + self.rr * self.stop_atr * atr
            else:
                stop, target = ref + self.stop_atr * atr, ref - self.rr * self.stop_atr * atr
            risk = abs(ref - stop)
            if risk <= 0:
                continue
            intents.append(EntryIntent(
                setup=self.name, version=self.version,
                day=day_midnight(utc_day(candles[i + 1])), direction=direction,
                session="ANY", arm_index=i, arm_time=candles[i].time_utc,
                entry_price=ref, stop=stop, target=target, invalidation_price=stop,
                expiry_index=i + 1, entry_type="MARKET",
                note=f"{self.factor} only; ATR {atr:.2f} stop {self.stop_atr}x rr {self.rr}",
                context={"atr": atr, "risk_usd": risk}))
            last = i
        return intents
