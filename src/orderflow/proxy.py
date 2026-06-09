"""Order-flow proxy engine (Task P5-001).

Computes cautious order-flow PROXY metrics from MT5 candle data (tick volume,
spread behavior, candle aggression, delta/CVD proxy). References
16_ORDERFLOW_PROXY_POLICY.md and decision INIT-005.

Hard rule (policy "Trade Rule" + INIT-005): the order-flow proxy may only adjust
confidence / uncertainty (and downstream risk / trailing). It CANNOT directly
trigger trades and never emits a trade direction or signal. This engine therefore
exposes proxy metrics and a "pressure" descriptor (allowed language: "tick-volume
proxy supports bullish pressure"), but no LONG/SHORT decision. The result carries
is_trade_signal = False by construction.

MT5 volume/CVD/delta are broker-level proxies, not guaranteed institutional order
flow. No look-ahead: only the supplied window is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence

from src.data.schemas import Candle
from src.structure.market_structure import Bias


class ProxyPressure(str, Enum):
    """Directional PROXY pressure. NOT a trade signal."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class VolumeState(str, Enum):
    EXPANSION = "EXPANSION"
    EXHAUSTION = "EXHAUSTION"
    NORMAL = "NORMAL"


@dataclass(frozen=True)
class OrderFlowProxy:
    """Order-flow proxy assessment. Adjusts confidence/uncertainty only."""

    pressure: ProxyPressure
    volume_state: VolumeState
    volume_ratio: float
    spread_ratio: float
    spread_widening: bool
    aggression: float        # body / range of the latest candle
    delta_proxy: float       # signed volume of the latest candle
    cvd_proxy: float         # cumulative signed volume over the window
    divergence: bool         # price vs CVD-proxy disagree
    abnormal_activity: bool
    conflict_with_structure: bool
    confidence_adjustment: float
    uncertainty_adjustment: float
    note: str
    # Proxy can never trigger a trade (INIT-005 / policy Trade Rule).
    is_trade_signal: bool = False


class OrderFlowProxyEngine:
    """Computes order-flow proxy metrics. Never emits a trade direction."""

    def __init__(
        self,
        *,
        lookback: int = 20,
        expansion_factor: float = 1.5,
        spread_widen_factor: float = 1.5,
        abnormal_factor: float = 2.0,
        aggression_strong: float = 0.5,
        aggression_weak: float = 0.3,
        step: float = 0.1,
        max_adjustment: float = 0.2,
    ) -> None:
        self._lookback = lookback
        self._expansion_factor = expansion_factor
        self._spread_widen_factor = spread_widen_factor
        self._abnormal_factor = abnormal_factor
        self._aggression_strong = aggression_strong
        self._aggression_weak = aggression_weak
        self._step = step
        self._max = max_adjustment

    def analyze(
        self,
        candles: Sequence[Candle],
        structural_bias: Optional[Bias] = None,
    ) -> OrderFlowProxy:
        if len(candles) < 3:
            return self._inconclusive("insufficient data for order-flow proxy")

        last = candles[-1]
        window = list(candles[-(self._lookback + 1):])
        baseline = list(candles[max(0, len(candles) - 1 - self._lookback): -1])

        volume_ratio = self._ratio(last.tick_volume, [c.tick_volume for c in baseline])
        spread_ratio, spread_widening = self._spread(last, baseline)
        aggression = self._aggression(last)
        delta_proxy = self._signed_volume(last)
        cvd_proxy = sum(self._signed_volume(c) for c in window)
        total_volume = sum(c.tick_volume for c in window) or 1

        pressure = self._pressure(cvd_proxy, total_volume)
        volume_state = self._volume_state(volume_ratio, aggression)
        divergence = self._divergence(window, cvd_proxy)
        abnormal = volume_ratio >= self._abnormal_factor or spread_ratio >= self._abnormal_factor
        conflict = self._conflict(pressure, structural_bias)

        conf, unc = self._adjustments(
            volume_state, aggression, divergence, spread_widening, abnormal, conflict
        )

        return OrderFlowProxy(
            pressure=pressure,
            volume_state=volume_state,
            volume_ratio=volume_ratio,
            spread_ratio=spread_ratio,
            spread_widening=spread_widening,
            aggression=aggression,
            delta_proxy=delta_proxy,
            cvd_proxy=cvd_proxy,
            divergence=divergence,
            abnormal_activity=abnormal,
            conflict_with_structure=conflict,
            confidence_adjustment=conf,
            uncertainty_adjustment=unc,
            note=self._note(pressure, volume_state, divergence, spread_widening, conflict),
        )

    # -- metric helpers ----------------------------------------------------
    @staticmethod
    def _signed_volume(candle: Candle) -> float:
        if candle.close > candle.open:
            return float(candle.tick_volume)
        if candle.close < candle.open:
            return -float(candle.tick_volume)
        return 0.0

    @staticmethod
    def _aggression(candle: Candle) -> float:
        rng = candle.high - candle.low
        if rng <= 0:
            return 0.0
        return abs(candle.close - candle.open) / rng

    @staticmethod
    def _ratio(current: float, baseline: List[float]) -> float:
        if not baseline:
            return 1.0
        avg = sum(baseline) / len(baseline)
        return current / avg if avg > 0 else 1.0

    def _spread(self, last: Candle, baseline: List[Candle]) -> tuple[float, bool]:
        spreads = [c.spread for c in baseline if c.spread is not None]
        if last.spread is None or not spreads:
            return 1.0, False
        avg = sum(spreads) / len(spreads)
        ratio = last.spread / avg if avg > 0 else 1.0
        return ratio, ratio >= self._spread_widen_factor

    def _pressure(self, cvd_proxy: float, total_volume: float) -> ProxyPressure:
        # Deadzone: small net imbalance relative to traded volume is neutral.
        if abs(cvd_proxy) < 0.1 * total_volume:
            return ProxyPressure.NEUTRAL
        return ProxyPressure.BULLISH if cvd_proxy > 0 else ProxyPressure.BEARISH

    def _volume_state(self, volume_ratio: float, aggression: float) -> VolumeState:
        if volume_ratio >= self._expansion_factor:
            if aggression >= self._aggression_strong:
                return VolumeState.EXPANSION
            if aggression < self._aggression_weak:
                return VolumeState.EXHAUSTION  # high effort, little result
        return VolumeState.NORMAL

    @staticmethod
    def _divergence(window: List[Candle], cvd_proxy: float) -> bool:
        price_change = window[-1].close - window[0].close
        if price_change == 0 or cvd_proxy == 0:
            return False
        return (price_change > 0) != (cvd_proxy > 0)

    @staticmethod
    def _conflict(pressure: ProxyPressure, structural_bias: Optional[Bias]) -> bool:
        if structural_bias is None or structural_bias is Bias.NEUTRAL:
            return False
        if pressure is ProxyPressure.NEUTRAL:
            return False
        bias_is_bull = structural_bias is Bias.BULLISH
        pressure_is_bull = pressure is ProxyPressure.BULLISH
        return bias_is_bull != pressure_is_bull

    def _adjustments(
        self,
        volume_state: VolumeState,
        aggression: float,
        divergence: bool,
        spread_widening: bool,
        abnormal: bool,
        conflict: bool,
    ) -> tuple[float, float]:
        conf = 0.0
        unc = 0.0
        if volume_state is VolumeState.EXPANSION and aggression >= self._aggression_strong:
            conf += self._step
        if volume_state is VolumeState.EXHAUSTION:
            unc += self._step
        if divergence:
            conf -= self._step
            unc += self._step
        if spread_widening:
            conf -= self._step
            unc += self._step
        if abnormal:
            unc += self._step
        if conflict:
            conf -= self._step
            unc += self._step
        conf = max(-self._max, min(self._max, conf))
        unc = max(0.0, min(self._max, unc))
        return conf, unc

    @staticmethod
    def _note(
        pressure: ProxyPressure,
        volume_state: VolumeState,
        divergence: bool,
        spread_widening: bool,
        conflict: bool,
    ) -> str:
        parts = [f"order-flow proxy pressure {pressure.value.lower()}"]
        if volume_state is not VolumeState.NORMAL:
            parts.append(f"volume {volume_state.value.lower()}")
        if divergence:
            parts.append("CVD proxy divergence")
        if spread_widening:
            parts.append("spread widening")
        if conflict:
            parts.append("conflicts with structure (uncertainty increased)")
        return "; ".join(parts)

    def _inconclusive(self, note: str) -> OrderFlowProxy:
        return OrderFlowProxy(
            pressure=ProxyPressure.NEUTRAL,
            volume_state=VolumeState.NORMAL,
            volume_ratio=1.0,
            spread_ratio=1.0,
            spread_widening=False,
            aggression=0.0,
            delta_proxy=0.0,
            cvd_proxy=0.0,
            divergence=False,
            abnormal_activity=False,
            conflict_with_structure=False,
            confidence_adjustment=0.0,
            uncertainty_adjustment=0.0,
            note=note,
        )
