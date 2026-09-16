"""
Institutional Performance and Risk Analytics for Backtesting.
Calculates CAGR, Max Drawdown, Sharpe, Sortino, Calmar, Profit Factor,
R-multiples expectancy, and Market Regime breakdowns.
"""

from datetime import datetime
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


class BacktestMetricsCalculator:
    def __init__(self, risk_free_rate: float = 0.03):
        self.risk_free_rate = risk_free_rate

    def calculate_all_metrics(
        self,
        equity_curve: List[Dict],
        closed_trades: List[Dict],
        benchmarks: Optional[Dict[str, List[Dict]]] = None,
    ) -> Dict:
        """
        Computes complete quantitative analytics package.
        """
        if not equity_curve:
            return {}

        df_eq = pd.DataFrame(equity_curve)
        df_eq["date"] = pd.to_datetime(df_eq["date"])
        df_eq = df_eq.sort_values("date").reset_index(drop=True)

        initial_val = float(df_eq["equity"].iloc[0])
        final_val = float(df_eq["equity"].iloc[-1])
        total_days = max(1, (df_eq["date"].iloc[-1] - df_eq["date"].iloc[0]).days)
        years = total_days / 365.25

        # Returns and CAGR
        total_return_pct = ((final_val - initial_val) / initial_val) * 100.0
        cagr = ((final_val / initial_val) ** (1.0 / max(years, 0.1)) - 1.0) * 100.0

        # Daily returns
        df_eq["daily_return"] = df_eq["equity"].pct_change().fillna(0.0)
        daily_returns = df_eq["daily_return"].to_numpy()

        # Drawdown calculations
        df_eq["peak"] = df_eq["equity"].cummax()
        df_eq["drawdown"] = (df_eq["equity"] - df_eq["peak"]) / df_eq["peak"]
        max_drawdown_pct = float(df_eq["drawdown"].min()) * 100.0

        # Max Drawdown duration in days
        dd_series = df_eq["drawdown"]
        is_underwater = dd_series < 0
        dd_durations = []
        cur_dur = 0
        for uw in is_underwater:
            if uw:
                cur_dur += 1
            else:
                if cur_dur > 0:
                    dd_durations.append(cur_dur)
                cur_dur = 0
        if cur_dur > 0:
            dd_durations.append(cur_dur)
        max_dd_duration = max(dd_durations) if dd_durations else 0

        # Volatility & Risk-Adjusted Ratios
        ann_volatility = float(np.std(daily_returns) * np.sqrt(365.25)) * 100.0
        excess_cagr = cagr - (self.risk_free_rate * 100.0)
        sharpe_ratio = round(excess_cagr / ann_volatility, 2) if ann_volatility > 0 else 0.0

        downside_returns = daily_returns[daily_returns < 0]
        downside_vol = float(np.std(downside_returns) * np.sqrt(365.25)) * 100.0 if len(downside_returns) > 0 else 1e-6
        sortino_ratio = round(excess_cagr / downside_vol, 2) if downside_vol > 0 else 0.0

        calmar_ratio = round(cagr / abs(max_drawdown_pct), 2) if abs(max_drawdown_pct) > 0 else 0.0

        # Trade statistics
        trade_stats = self._calculate_trade_statistics(closed_trades)

        # Market Regime Breakdown
        regime_stats = self._calculate_regimes(df_eq, closed_trades)

        # Benchmark Comparisons
        benchmark_summary = {}
        if benchmarks:
            for b_sym, b_curve in benchmarks.items():
                if b_curve:
                    b_init = b_curve[0]["equity"]
                    b_final = b_curve[-1]["equity"]
                    b_ret = ((b_final - b_init) / b_init) * 100.0
                    b_cagr = ((b_final / b_init) ** (1.0 / max(years, 0.1)) - 1.0) * 100.0
                    b_eq = [x["equity"] for x in b_curve]
                    b_peak = np.maximum.accumulate(b_eq)
                    b_dd = (np.array(b_eq) - b_peak) / b_peak
                    b_mdd = float(np.min(b_dd)) * 100.0
                    benchmark_summary[b_sym] = {
                        "total_return_pct": round(b_ret, 2),
                        "cagr": round(b_cagr, 2),
                        "max_drawdown_pct": round(b_mdd, 2),
                    }

        return {
            "initial_capital": initial_val,
            "final_equity": final_val,
            "total_days": total_days,
            "years": round(years, 2),
            "total_return_pct": round(total_return_pct, 2),
            "cagr": round(cagr, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "max_drawdown_duration_days": max_dd_duration,
            "annualized_volatility_pct": round(ann_volatility, 2),
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "calmar_ratio": calmar_ratio,
            "trade_stats": trade_stats,
            "regimes": regime_stats,
            "benchmarks": benchmark_summary,
        }

    def _calculate_trade_statistics(self, trades: List[Dict]) -> Dict:
        if not trades:
            return {
                "total_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "win_loss_ratio": 0.0,
                "expectancy_r": 0.0,
                "long_trades": 0,
                "short_trades": 0,
            }

        pnls = [t["pnl"] for t in trades]
        r_mults = [t.get("r_multiple", 0.0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        total_trades = len(trades)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0

        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        avg_win = float(np.mean(wins)) if wins else 0.0
        avg_loss = float(abs(np.mean(losses))) if losses else 0.0
        win_loss_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0
        expectancy_r = round(float(np.mean(r_mults)), 2) if r_mults else 0.0

        long_trades = sum(1 for t in trades if t["direction"] == "LONG")
        short_trades = sum(1 for t in trades if t["direction"] == "SHORT")

        return {
            "total_trades": total_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": profit_factor,
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "win_loss_ratio": win_loss_ratio,
            "expectancy_r": expectancy_r,
            "long_trades": long_trades,
            "short_trades": short_trades,
        }

    def _calculate_regimes(self, df_eq: pd.DataFrame, trades: List[Dict]) -> Dict:
        """
        Analyzes performance across 3 distinct macroeconomic market regimes.
        """
        regime_defs = {
            "2021_2022_Bear_Crash": ("2021-09-01", "2022-12-31"),
            "2023_Chop_Accumulation": ("2023-01-01", "2023-12-31"),
            "2024_2026_Bull_Expansion": ("2024-01-01", "2026-12-31"),
        }

        results = {}
        for r_name, (s_date, e_date) in regime_defs.items():
            s_dt = pd.to_datetime(s_date)
            e_dt = pd.to_datetime(e_date)

            sub_eq = df_eq[(df_eq["date"] >= s_dt) & (df_eq["date"] <= e_dt)]
            if len(sub_eq) >= 2:
                r_start = float(sub_eq["equity"].iloc[0])
                r_end = float(sub_eq["equity"].iloc[-1])
                r_ret = ((r_end - r_start) / r_start) * 100.0

                sub_peak = sub_eq["equity"].cummax()
                sub_dd = (sub_eq["equity"] - sub_peak) / sub_peak
                r_mdd = float(sub_dd.min()) * 100.0

                # Trades in this regime
                regime_trades = [
                    t for t in trades
                    if s_date <= t.get("entry_date", "") <= e_date
                ]
                t_count = len(regime_trades)
                t_wins = sum(1 for t in regime_trades if t["pnl"] > 0)
                t_wr = (t_wins / t_count * 100.0) if t_count > 0 else 0.0

                results[r_name] = {
                    "return_pct": round(r_ret, 2),
                    "max_drawdown_pct": round(r_mdd, 2),
                    "trade_count": t_count,
                    "win_rate_pct": round(t_wr, 2),
                }

        return results
