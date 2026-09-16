"""
Backtesting Simulation Engine.
Coordinates data feeds, bar-by-bar execution, order fills, and benchmarks.
Supports Spot-Only and Long+Hedge Short modes across multi-asset universes.
"""

from datetime import datetime
import logging
import time
from typing import Dict, List, Optional, Tuple
import pandas as pd

from src.backtest.data_manager import BacktestDataManager, DEFAULT_UNIVERSE
from src.backtest.portfolio import PortfolioManager
from src.backtest.signals import BacktestSignalGenerator

logger = logging.getLogger(__name__)


class BacktestEngine:
    def __init__(
        self,
        universe: Optional[Dict[str, List[str]]] = None,
        start_date: str = "2021-09-01",
        initial_capital: float = 100000.0,
        risk_per_trade: float = 0.01,
        max_positions: int = 10,
        rolling_sr_window: int = 120,
    ):
        self.universe = universe or DEFAULT_UNIVERSE
        self.start_date = start_date
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.max_positions = max_positions
        self.rolling_sr_window = rolling_sr_window

        self.data_manager = BacktestDataManager()
        self.signal_gen = BacktestSignalGenerator(min_warmup=60, rolling_sr_window=rolling_sr_window)

    def run_simulation(
        self,
        mode: str = "spot",  # 'spot' or 'hedge'
        force_refresh_data: bool = False,
    ) -> Dict:
        """
        Executes a full multi-year bar-by-bar portfolio simulation.
        """
        allow_short = (mode == "hedge")
        logger.info(f"=== Initializing Backtest Engine [Mode: {mode.upper()} | Start: {self.start_date}] ===")
        t0 = time.time()

        # 1. Load and prepare multi-asset datasets
        raw_datasets = self.data_manager.load_universe(
            universe=self.universe,
            start_date=self.start_date,
            timeframe="1D",
            force_refresh=force_refresh_data,
        )

        if not raw_datasets:
            raise ValueError("No data available to run backtest.")

        # 2. Precompute vectorized indicators for all assets
        processed_datasets: Dict[str, pd.DataFrame] = {}
        # Date to index lookup for each symbol
        date_to_idx: Dict[str, Dict[str, int]] = {}

        for sym, df in raw_datasets.items():
            feat_df = self.signal_gen.prepare_asset_features(df)
            processed_datasets[sym] = feat_df
            date_to_idx[sym] = {str(d): i for i, d in enumerate(feat_df["date"])}

        # 3. Unified chronological calendar
        all_calendar_dates = self.data_manager.extract_unified_calendar(processed_datasets)

        # 4. Initialize Portfolio Manager
        portfolio = PortfolioManager(
            initial_capital=self.initial_capital,
            risk_per_trade=self.risk_per_trade,
            max_positions=self.max_positions,
        )

        # Signals queued from previous day's close
        pending_entry_signals = []
        pending_structural_exits: Dict[str, str] = {}

        logger.info(f"Simulating across {len(all_calendar_dates)} calendar days and {len(processed_datasets)} assets...")

        for day_idx, current_date in enumerate(all_calendar_dates):
            # Collect today's price bars for assets that traded today
            today_bars: Dict[str, Dict[str, float]] = {}
            for sym, df in processed_datasets.items():
                idx = date_to_idx[sym].get(current_date)
                if idx is not None:
                    row = df.iloc[idx]
                    today_bars[sym] = {
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                    }

            if not today_bars:
                continue

            # A. Process exits for open positions on today's price action
            portfolio.process_intrabar_exits(
                date=current_date,
                price_bars=today_bars,
                structural_exits=pending_structural_exits,
            )

            # B. Execute entries for signals generated on previous day's close
            if pending_entry_signals:
                portfolio.execute_entries(
                    date=current_date,
                    signals=pending_entry_signals,
                    price_bars=today_bars,
                )
                pending_entry_signals = []

            # C. Record end-of-day equity mark-to-market
            portfolio.record_daily_equity(date=current_date, price_bars=today_bars)

            # D. Evaluate close of today's bar to generate signals for tomorrow's open
            pending_entry_signals = []
            pending_structural_exits = {}

            for sym, df in processed_datasets.items():
                idx = date_to_idx[sym].get(current_date)
                if idx is not None and idx >= 60:
                    sig = self.signal_gen.evaluate_bar_signal(
                        symbol=sym,
                        df=df,
                        idx=idx,
                        allow_short=allow_short,
                    )
                    if sig:
                        if sig.action == "BUY_LONG":
                            pending_entry_signals.append(sig)
                            pending_structural_exits[sym] = "EXIT_SHORT"
                        elif sig.action == "SELL_SHORT":
                            pending_entry_signals.append(sig)
                            pending_structural_exits[sym] = "EXIT_LONG"
                        elif sig.action in ["EXIT_LONG", "EXIT_SHORT"]:
                            pending_structural_exits[sym] = sig.action

        elapsed = time.time() - t0
        logger.info(f"Simulation completed in {elapsed:.2f}s | Closed Trades: {len(portfolio.closed_trades)}")

        # Compute benchmark curves for comparison
        benchmarks = self._compute_benchmarks(processed_datasets, all_calendar_dates)

        return {
            "mode": mode,
            "start_date": all_calendar_dates[0] if all_calendar_dates else self.start_date,
            "end_date": all_calendar_dates[-1] if all_calendar_dates else "",
            "initial_capital": self.initial_capital,
            "final_equity": portfolio.equity_curve[-1]["equity"] if portfolio.equity_curve else self.initial_capital,
            "equity_curve": portfolio.equity_curve,
            "closed_trades": [t.__dict__ for t in portfolio.closed_trades],
            "open_positions": [p.__dict__ for p in portfolio.open_positions.values()],
            "benchmarks": benchmarks,
            "elapsed_seconds": elapsed,
        }

    def _compute_benchmarks(
        self,
        datasets: Dict[str, pd.DataFrame],
        calendar: List[str],
    ) -> Dict[str, List[Dict]]:
        """
        Computes benchmark equity curves for BTC and SPY over the exact same calendar dates.
        """
        benchmarks = {}

        for b_sym in ["BTCUSDT", "SPY"]:
            if b_sym in datasets:
                df = datasets[b_sym]
                d_to_c = {str(r["date"]): float(r["close"]) for _, r in df.iterrows()}

                first_price = None
                curve = []
                last_known_val = self.initial_capital

                for d in calendar:
                    if d in d_to_c:
                        p = d_to_c[d]
                        if first_price is None:
                            first_price = p
                        val = (p / first_price) * self.initial_capital
                        last_known_val = val
                    else:
                        val = last_known_val

                    curve.append({"date": d, "equity": round(val, 2)})

                benchmarks[b_sym] = curve

        return benchmarks
