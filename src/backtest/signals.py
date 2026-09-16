"""
Signal Generation and Market State Analysis for Backtesting.
Precomputes Larsson Line SMMA ribbons, ATR volatility, rolling S/R levels,
and evaluates zero-bias trade setups strictly using closed candle data.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.engine.smma import compute_larsson_series, LarssonState
from src.engine.sr_levels import analyze_sr_levels, compute_atr


@dataclass
class BacktestSignal:
    date: str
    symbol: str
    action: str        # 'BUY_LONG', 'EXIT_LONG', 'SELL_SHORT', 'EXIT_SHORT', 'HOLD'
    setup_type: str    # 'PULLBACK_VALUE_BUY', 'BREAKOUT_BUY', 'STRUCTURAL_EXIT', 'HEDGE_SHORT', 'STOP_LOSS', 'TAKE_PROFIT'
    entry_price: float
    stop_loss: Optional[float]
    tp1: Optional[float]
    tp2: Optional[float]
    rr_ratio: float
    score: int
    tier: str          # 'A+', 'A', 'B', 'NONE'
    state: str         # 'GOLD', 'BLUE', 'NEUTRAL'
    atr: float


class BacktestSignalGenerator:
    def __init__(self, min_warmup: int = 150, rolling_sr_window: int = 120):
        self.min_warmup = min_warmup
        self.rolling_sr_window = rolling_sr_window

    def prepare_asset_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Precomputes all vectorized features (SMMA ribbon, states, ATR) for the asset.
        """
        df = df.copy()
        highs = df["high"].to_numpy(dtype=np.float64)
        lows = df["low"].to_numpy(dtype=np.float64)
        closes = df["close"].to_numpy(dtype=np.float64)

        v1, m1, m2, v2, states = compute_larsson_series(highs, lows)
        atr = compute_atr(highs, lows, closes, period=14)

        df["v1"] = v1
        df["m1"] = m1
        df["m2"] = m2
        df["v2"] = v2
        df["state"] = [s.value for s in states]
        df["atr"] = atr

        return df

    def evaluate_bar_signal(
        self,
        symbol: str,
        df: pd.DataFrame,
        idx: int,
        allow_short: bool = False,
    ) -> Optional[BacktestSignal]:
        """
        Evaluates trading setup at bar `idx` (strictly using historical data up to `idx`).
        Orders will be executed on bar `idx + 1` Open.
        """
        if idx < self.min_warmup:
            return None

        row = df.iloc[idx]
        current_price = float(row["close"])
        state = row["state"]
        v1 = float(row["v1"])
        m1 = float(row["m1"])
        m2 = float(row["m2"])
        v2 = float(row["v2"])
        atr = float(row["atr"])
        date_str = str(row["date"])

        # Use rolling window up to idx for S/R to prevent lookahead and keep calculation fast
        w_start = max(0, idx - self.rolling_sr_window)
        sub_highs = df["high"].iloc[w_start : idx + 1].to_numpy(dtype=np.float64)
        sub_lows = df["low"].iloc[w_start : idx + 1].to_numpy(dtype=np.float64)
        sub_closes = df["close"].iloc[w_start : idx + 1].to_numpy(dtype=np.float64)

        sr_analysis = analyze_sr_levels(sub_highs, sub_lows, sub_closes, current_price=current_price)
        s1 = sr_analysis.s1
        s2 = sr_analysis.s2
        r1 = sr_analysis.r1
        r2 = sr_analysis.r2
        context_flag = sr_analysis.context_flag

        v2_val = v2 if v2 > 0 else 1e-6
        spread_pct = ((v1 - v2_val) / v2_val) * 100.0
        spread_expanding = spread_pct > 0.25

        # ---------------------------------------------------------------------
        # 1. PULLBACK VALUE BUY (Core Institutional Long Setup)
        # ---------------------------------------------------------------------
        is_pullback = (
            context_flag == "NEAR_SUPPORT"
            or (s1 is not None and (current_price - s1) <= 1.2 * atr)
            or (current_price <= v1 and current_price >= (v2 - 0.2 * atr))
        )

        if state == "GOLD" and is_pullback:
            s1_floor = s1 if s1 is not None else v2
            structural_floor = min(s1_floor, v2)
            sl = round(structural_floor - (0.5 * atr), 4)
            risk = current_price - sl

            if risk > 0:
                if r1 is not None and r1 > current_price:
                    tp1 = round(r1, 4)
                    reward = tp1 - current_price
                    rr = round(reward / risk, 2)
                    tp2 = round(r2 if r2 is not None else (current_price + (2.5 * risk)), 4)
                else:
                    tp1 = round(current_price + (2.0 * risk), 4)
                    tp2 = round(current_price + (3.5 * risk), 4)
                    rr = 2.0

                if rr >= 1.8:
                    score = 65
                    if sr_analysis.s1_touches >= 2:
                        score += 10
                    if spread_expanding:
                        score += 10
                    if rr >= 2.5:
                        score += 10

                    tier = "A+" if score >= 85 else ("A" if score >= 70 else "B")

                    return BacktestSignal(
                        date=date_str,
                        symbol=symbol,
                        action="BUY_LONG",
                        setup_type="PULLBACK_VALUE_BUY",
                        entry_price=current_price,
                        stop_loss=sl,
                        tp1=tp1,
                        tp2=tp2,
                        rr_ratio=rr,
                        score=score,
                        tier=tier,
                        state=state,
                        atr=atr,
                    )

        # ---------------------------------------------------------------------
        # 2. BREAKOUT BUY (Trend Discovery Long Setup)
        # ---------------------------------------------------------------------
        if state == "GOLD" and (context_flag == "BREAKOUT_ABOVE" or r1 is None):
            sl_base = s1 if s1 is not None else v2
            sl = round(sl_base - (0.5 * atr), 4)
            risk = current_price - sl

            if risk > 0:
                tp1 = round(current_price + (1.8 * risk), 4)
                tp2 = round(current_price + (3.5 * risk), 4)
                rr = round((tp1 - current_price) / risk, 2)

                score = 60
                if spread_expanding:
                    score += 15
                tier = "A" if score >= 70 else "B"

                return BacktestSignal(
                    date=date_str,
                    symbol=symbol,
                    action="BUY_LONG",
                    setup_type="BREAKOUT_BUY",
                    entry_price=current_price,
                    stop_loss=sl,
                    tp1=tp1,
                    tp2=tp2,
                    rr_ratio=rr,
                    score=score,
                    tier=tier,
                    state=state,
                    atr=atr,
                )

        # ---------------------------------------------------------------------
        # 3. HEDGE SHORT 2X (Bear Market Short Setup)
        # ---------------------------------------------------------------------
        if allow_short and state == "BLUE":
            overhead_res = r1 if (r1 is not None and r1 > current_price) else v2
            if current_price < overhead_res:
                # In BLUE ribbon, v1 (15) is lower boundary, v2 (29) is upper boundary
                retesting_overhead = (
                    (current_price >= (v1 - 0.2 * atr) and current_price <= (v2 + 0.3 * atr))
                    or (r1 is not None and abs(current_price - r1) <= 0.8 * atr)
                )

                if retesting_overhead:
                    sl = round(max(overhead_res, v2) + (0.5 * atr), 4)
                    risk = sl - current_price

                    if risk > 0:
                        tp1 = round(s1 if (s1 is not None and s1 < current_price) else (current_price - 1.8 * risk), 4)
                        tp2 = round(s2 if (s2 is not None and s2 < current_price) else (current_price - 3.0 * risk), 4)
                        reward = current_price - tp1
                        rr = round(reward / risk, 2)

                        if rr >= 1.8 and current_price > tp1:
                            score = 70
                            if spread_pct < -0.2:
                                score += 10
                            tier = "A+" if score >= 80 else "A"

                            return BacktestSignal(
                                date=date_str,
                                symbol=symbol,
                                action="SELL_SHORT",
                                setup_type="HEDGE_SHORT_2X",
                                entry_price=current_price,
                                stop_loss=sl,
                                tp1=tp1,
                                tp2=tp2,
                                rr_ratio=rr,
                                score=score,
                                tier=tier,
                                state=state,
                                atr=atr,
                            )

        # ---------------------------------------------------------------------
        # 4. STRUCTURAL EXIT FOR LONGS
        # ---------------------------------------------------------------------
        if state == "BLUE" or context_flag == "BREAKDOWN_BELOW":
            return BacktestSignal(
                date=date_str,
                symbol=symbol,
                action="EXIT_LONG",
                setup_type="STRUCTURAL_EXIT",
                entry_price=current_price,
                stop_loss=None,
                tp1=None,
                tp2=None,
                rr_ratio=0.0,
                score=80,
                tier="A",
                state=state,
                atr=atr,
            )

        # ---------------------------------------------------------------------
        # 5. STRUCTURAL EXIT FOR SHORTS
        # ---------------------------------------------------------------------
        if allow_short and (state == "GOLD" or context_flag == "BREAKOUT_ABOVE"):
            return BacktestSignal(
                date=date_str,
                symbol=symbol,
                action="EXIT_SHORT",
                setup_type="STRUCTURAL_EXIT",
                entry_price=current_price,
                stop_loss=None,
                tp1=None,
                tp2=None,
                rr_ratio=0.0,
                score=80,
                tier="A",
                state=state,
                atr=atr,
            )

        return None
