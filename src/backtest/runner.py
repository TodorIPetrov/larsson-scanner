"""
Top-level Backtest Runner.
Orchestrates execution of Spot and Hedge backtests, metric calculations, and report generation.
"""

import logging
from typing import Dict, Optional

from src.backtest.engine import BacktestEngine
from src.backtest.metrics import BacktestMetricsCalculator
from src.backtest.report import BacktestReportGenerator

logger = logging.getLogger(__name__)


def run_full_backtest(
    mode: str = "both",  # 'spot', 'hedge', or 'both'
    start_date: str = "2021-09-01",
    capital: float = 100000.0,
    universe: Optional[Dict] = None,
    force_refresh: bool = False,
) -> Dict:
    """
    Main entry point for executing 5-year institutional backtesting.
    """
    engine = BacktestEngine(
        universe=universe,
        start_date=start_date,
        initial_capital=capital,
    )
    calculator = BacktestMetricsCalculator()
    reporter = BacktestReportGenerator()

    results = {}

    if mode in ["spot", "both"]:
        spot_raw = engine.run_simulation(mode="spot", force_refresh_data=force_refresh)
        spot_raw["metrics"] = calculator.calculate_all_metrics(
            equity_curve=spot_raw["equity_curve"],
            closed_trades=spot_raw["closed_trades"],
            benchmarks=spot_raw.get("benchmarks"),
        )
        results["spot"] = spot_raw

    if mode in ["hedge", "both"]:
        # Do not force refresh data again on hedge if already downloaded
        hedge_raw = engine.run_simulation(mode="hedge", force_refresh_data=False)
        hedge_raw["metrics"] = calculator.calculate_all_metrics(
            equity_curve=hedge_raw["equity_curve"],
            closed_trades=hedge_raw["closed_trades"],
            benchmarks=hedge_raw.get("benchmarks"),
        )
        results["hedge"] = hedge_raw

    if mode == "both":
        reporter.print_terminal_comparison(results["spot"], results["hedge"])
        report_file = reporter.export_markdown_report(results["spot"], results["hedge"])
        html_file = reporter.export_html_report(results["spot"], results["hedge"])
        results["report_path"] = report_file
        results["html_report_path"] = html_file
    elif mode == "spot":
        reporter.print_terminal_comparison(results["spot"], results["spot"])
        report_file = reporter.export_markdown_report(results["spot"], results["spot"])
        html_file = reporter.export_html_report(results["spot"], results["spot"])
        results["report_path"] = report_file
        results["html_report_path"] = html_file
    else:
        reporter.print_terminal_comparison(results["hedge"], results["hedge"])
        report_file = reporter.export_markdown_report(results["hedge"], results["hedge"])
        html_file = reporter.export_html_report(results["hedge"], results["hedge"])
        results["report_path"] = report_file
        results["html_report_path"] = html_file

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    run_full_backtest(mode="both")
