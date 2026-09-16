"""
Institutional Report Generator for Backtesting.
Produces terminal tear sheet tables, rich Markdown documentation,
and interactive visual HTML reports.
"""

from datetime import datetime
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "research")


class BacktestReportGenerator:
    def __init__(self, output_dir: str = REPORT_DIR):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def print_terminal_comparison(self, spot_res: Dict, hedge_res: Dict):
        """
        Prints a side-by-side institutional comparison table in the console.
        """
        sm = spot_res.get("metrics", {})
        hm = hedge_res.get("metrics", {})
        st = sm.get("trade_stats", {})
        ht = hm.get("trade_stats", {})
        sb = sm.get("benchmarks", {})

        print("\n" + "=" * 80)
        print("🏛️  LARSSON LINE INSTITUTIONAL 5-YEAR MULTI-ASSET BACKTEST (2021 - 2026)")
        print("=" * 80)
        print(f"Period: {spot_res.get('start_date')} to {spot_res.get('end_date')} ({sm.get('years', 5)} Years)")
        print(f"Initial Capital: ${sm.get('initial_capital', 100000):,.2f} | Risk per Trade: 1.0% ATR")
        print("-" * 80)
        print(f"{'METRIC':<30} | {'🟢 SPOT ONLY':<20} | {'🟡 LONG + HEDGE 2X':<20}")
        print("-" * 80)
        print(f"{'Final Equity':<30} | ${sm.get('final_equity', 0):<19,.2f} | ${hm.get('final_equity', 0):<19,.2f}")
        print(f"{'Total Return':<30} | {sm.get('total_return_pct', 0):>+18.2f}% | {hm.get('total_return_pct', 0):>+18.2f}%")
        print(f"{'CAGR (Annual Return)':<30} | {sm.get('cagr', 0):>+18.2f}% | {hm.get('cagr', 0):>+18.2f}%")
        print(f"{'Max Drawdown (MDD)':<30} | {sm.get('max_drawdown_pct', 0):>18.2f}% | {hm.get('max_drawdown_pct', 0):>18.2f}%")
        print(f"{'Max Drawdown Duration':<30} | {sm.get('max_drawdown_duration_days', 0):>15} days | {hm.get('max_drawdown_duration_days', 0):>15} days")
        print(f"{'Annualized Volatility':<30} | {sm.get('annualized_volatility_pct', 0):>18.2f}% | {hm.get('annualized_volatility_pct', 0):>18.2f}%")
        print(f"{'Sharpe Ratio (rf=3%)':<30} | {sm.get('sharpe_ratio', 0):>19.2f} | {hm.get('sharpe_ratio', 0):>19.2f}")
        print(f"{'Sortino Ratio':<30} | {sm.get('sortino_ratio', 0):>19.2f} | {hm.get('sortino_ratio', 0):>19.2f}")
        print(f"{'Calmar Ratio (CAGR/MDD)':<30} | {sm.get('calmar_ratio', 0):>19.2f} | {hm.get('calmar_ratio', 0):>19.2f}")
        print(f"{'Profit Factor':<30} | {st.get('profit_factor', 0):>19.2f} | {ht.get('profit_factor', 0):>19.2f}")
        print(f"{'Win Rate':<30} | {st.get('win_rate_pct', 0):>18.2f}% | {ht.get('win_rate_pct', 0):>18.2f}%")
        print(f"{'Total Closed Trades':<30} | {st.get('total_trades', 0):>19} | {ht.get('total_trades', 0):>19}")
        print(f"{'Win / Loss Ratio':<30} | {st.get('win_loss_ratio', 0):>19.2f} | {ht.get('win_loss_ratio', 0):>19.2f}")
        print(f"{'Expectancy (R-multiple)':<30} | {st.get('expectancy_r', 0):>18.2f}R | {ht.get('expectancy_r', 0):>18.2f}R")
        print("-" * 80)

        # Regimes
        s_reg = sm.get("regimes", {})
        h_reg = hm.get("regimes", {})
        print("📊 MARKET REGIME BREAKDOWN:")
        for r_key in s_reg.keys():
            s_r = s_reg.get(r_key, {})
            h_r = h_reg.get(r_key, {})
            r_title = r_key.replace("_", " ")
            print(f"  • {r_title}:")
            print(f"      Spot: Return {s_r.get('return_pct', 0):>+6.1f}% | MDD {s_r.get('max_drawdown_pct', 0):>6.1f}% | Win Rate {s_r.get('win_rate_pct', 0):.1f}% ({s_r.get('trade_count', 0)} trades)")
            print(f"      Hedge: Return {h_r.get('return_pct', 0):>+5.1f}% | MDD {h_r.get('max_drawdown_pct', 0):>6.1f}% | Win Rate {h_r.get('win_rate_pct', 0):.1f}% ({h_r.get('trade_count', 0)} trades)")

        if sb:
            print("-" * 80)
            print("📈 BUY & HOLD BENCHMARKS:")
            for b_sym, b_data in sb.items():
                print(f"  • {b_sym} Buy & Hold: Return {b_data.get('total_return_pct', 0):>+6.1f}% | CAGR {b_data.get('cagr', 0):>+5.1f}% | Max DD {b_data.get('max_drawdown_pct', 0):>5.1f}%")
        print("=" * 80 + "\n")

    def export_markdown_report(self, spot_res: Dict, hedge_res: Dict, filename: str = "BACKTEST_REPORT.md") -> str:
        """
        Generates a comprehensive Markdown report artifact.
        """
        sm = spot_res.get("metrics", {})
        hm = hedge_res.get("metrics", {})
        st = sm.get("trade_stats", {})
        ht = hm.get("trade_stats", {})
        sb = sm.get("benchmarks", {})
        s_reg = sm.get("regimes", {})
        h_reg = hm.get("regimes", {})

        md = []
        md.append("# 🏛️ Larsson Line Institutional Backtest Report")
        md.append(f"\n**Времеви обхват:** `{spot_res.get('start_date')}` до `{spot_res.get('end_date')}` ({sm.get('years')} години)")
        md.append(f"**Начален капитал:** `${sm.get('initial_capital', 100000):,.2f}` | **Риск на сделка:** `1.0% ATR` | **Макс позиции:** `10`\n")

        md.append("## ⚖️ Сравнителен анализ: Spot Only срещу Long + Light Hedge Short (2x)\n")
        md.append("| Метрика | 🟢 Spot Only | 🟡 Long + Hedge Short (2x) | Бележки |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **Краен капитал** | `${sm.get('final_equity', 0):,.2f}` | `${hm.get('final_equity', 0):,.2f}` | Начален: $100k |")
        md.append(f"| **Обща възвръщаемост** | `+{sm.get('total_return_pct', 0):.2f}%` | `+{hm.get('total_return_pct', 0):.2f}%` | За 5-те години |")
        md.append(f"| **CAGR (Годишна възвр.)** | `+{sm.get('cagr', 0):.2f}%` | `+{hm.get('cagr', 0):.2f}%` | Годишен темп |")
        md.append(f"| **Max Drawdown (MDD)** | `{sm.get('max_drawdown_pct', 0):.2f}%` | `{hm.get('max_drawdown_pct', 0):.2f}%` | Максимално пропадане |")
        md.append(f"| **Drawdown Duration** | `{sm.get('max_drawdown_duration_days', 0)} дни` | `{hm.get('max_drawdown_duration_days', 0)} дни` | Продължителност под вода |")
        md.append(f"| **Годишна волатилност** | `{sm.get('annualized_volatility_pct', 0):.2f}%` | `{hm.get('annualized_volatility_pct', 0):.2f}%` | Стандартно отклонение |")
        md.append(f"| **Sharpe Ratio** | `★ {sm.get('sharpe_ratio', 0):.2f}` | `★ {hm.get('sharpe_ratio', 0):.2f}` | Институционално (>1.5) |")
        md.append(f"| **Sortino Ratio** | `★ {sm.get('sortino_ratio', 0):.2f}` | `★ {hm.get('sortino_ratio', 0):.2f}` | Наказание само за лош риск |")
        md.append(f"| **Calmar Ratio** | `{sm.get('calmar_ratio', 0):.2f}` | `{hm.get('calmar_ratio', 0):.2f}` | CAGR / Max DD |")
        md.append(f"| **Profit Factor** | `{st.get('profit_factor', 0):.2f}` | `{ht.get('profit_factor', 0):.2f}` | Брутна печалба / загуба |")
        md.append(f"| **Win Rate %** | `{st.get('win_rate_pct', 0):.1f}%` | `{ht.get('win_rate_pct', 0):.1f}%` | Процент успешни сделки |")
        md.append(f"| **Общ брой сделки** | `{st.get('total_trades', 0)}` | `{ht.get('total_trades', 0)}` | Реализирани изходи |")
        md.append(f"| **Win / Loss Ratio** | `{st.get('win_loss_ratio', 0):.2f}` | `{ht.get('win_loss_ratio', 0):.2f}` | Средна печалба към загуба |")
        md.append(f"| **Expectancy** | `+{st.get('expectancy_r', 0):.2f}R` | `+{ht.get('expectancy_r', 0):.2f}R` | Очаквана стойност на сделка |")

        md.append("\n---\n")
        md.append("## 🌊 Анализ по пазарни цикли (Market Regimes)\n")
        md.append("| Пазарен цикъл | Режим | Възвръщаемост | Max DD | Сделки | Win Rate |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for r_k in s_reg.keys():
            sr = s_reg[r_k]
            hr = h_reg[r_k]
            r_name = r_k.replace("_", " ")
            md.append(f"| **{r_name}** | 🟢 Spot Only | `{sr.get('return_pct', 0):+0.1f}%` | `{sr.get('max_drawdown_pct', 0):0.1f}%` | {sr.get('trade_count', 0)} | {sr.get('win_rate_pct', 0):.1f}% |")
            md.append(f"| | 🟡 Hedge 2x | `{hr.get('return_pct', 0):+0.1f}%` | `{hr.get('max_drawdown_pct', 0):0.1f}%` | {hr.get('trade_count', 0)} | {hr.get('win_rate_pct', 0):.1f}% |")

        if sb:
            md.append("\n---\n")
            md.append("## 🏆 Сравнение с пасивни бенчмаркове (Buy & Hold)\n")
            md.append("| Бенчмарк | Обща възвръщаемост | CAGR | Max Drawdown |")
            md.append("| :--- | :--- | :--- | :--- |")
            for b_sym, bd in sb.items():
                md.append(f"| **{b_sym} Buy & Hold** | `{bd.get('total_return_pct', 0):+0.1f}%` | `{bd.get('cagr', 0):+0.1f}%` | `{bd.get('max_drawdown_pct', 0):0.1f}%` |")

        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(md))

        logger.info(f"Exported markdown report to {filepath}")
        return filepath

    def export_html_report(self, spot_res: Dict, hedge_res: Dict, filename: str = "BACKTEST_REPORT.html") -> str:
        """
        Generates a standalone, dark-themed institutional HTML report with interactive SVG equity charts.
        """
        sm = spot_res.get("metrics", {})
        hm = hedge_res.get("metrics", {})
        st = sm.get("trade_stats", {})
        ht = hm.get("trade_stats", {})

        s_curve = spot_res.get("equity_curve", [])
        h_curve = hedge_res.get("equity_curve", [])

        # Sample 100 points for smooth SVG rendering
        def sample_curve(curve, n=120):
            if len(curve) <= n:
                return curve
            step = len(curve) / n
            return [curve[int(i * step)] for i in range(n)] + [curve[-1]]

        s_sampled = sample_curve(s_curve)
        h_sampled = sample_curve(h_curve)

        all_vals = [p["equity"] for p in s_sampled + h_sampled] if (s_sampled and h_sampled) else [100000]
        min_y = min(all_vals) * 0.95
        max_y = max(all_vals) * 1.05
        y_range = max(1.0, max_y - min_y)

        def make_svg_path(sampled, width=800, height=260):
            if not sampled:
                return ""
            pts = []
            for i, p in enumerate(sampled):
                x = (i / (len(sampled) - 1)) * (width - 40) + 20
                y = height - 20 - ((p["equity"] - min_y) / y_range) * (height - 40)
                pts.append(f"{x:.1f},{y:.1f}")
            return "M " + " L ".join(pts)

        spot_path = make_svg_path(s_sampled)
        hedge_path = make_svg_path(h_sampled)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Larsson Line 5-Year Institutional Backtest Report</title>
    <style>
        :root {{
            --bg-main: #0B0E14;
            --bg-card: #151A23;
            --border: #232B3B;
            --gold: #F59E0B;
            --blue: #3B82F6;
            --green: #10B981;
            --red: #EF4444;
            --text-main: #F3F4F6;
            --text-muted: #9CA3AF;
        }}
        body {{
            background: var(--bg-main);
            color: var(--text-main);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 30px 20px;
        }}
        .container {{ max-width: 1100px; margin: 0 auto; }}
        header {{ margin-bottom: 25px; border-bottom: 1px solid var(--border); padding-bottom: 15px; }}
        h1 {{ font-size: 24px; margin: 0 0 8px 0; color: #FFF; display: flex; align-items: center; gap: 10px; }}
        .badge {{ font-size: 12px; padding: 3px 8px; border-radius: 4px; background: rgba(245, 158, 11, 0.2); color: var(--gold); }}
        .meta {{ color: var(--text-muted); font-size: 14px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 25px; }}
        .card {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }}
        .card .title {{ font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
        .card .value {{ font-size: 22px; font-weight: 700; margin-top: 6px; }}
        .chart-box {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 25px; }}
        .table-box {{ background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 25px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; text-align: left; }}
        th, td {{ padding: 12px 16px; border-bottom: 1px solid var(--border); }}
        th {{ background: #1B2230; color: var(--text-muted); font-weight: 600; }}
        tr:hover {{ background: rgba(255, 255, 255, 0.02); }}
        .legend {{ display: flex; gap: 20px; font-size: 13px; margin-bottom: 12px; }}
        .leg-item {{ display: flex; align-items: center; gap: 6px; }}
        .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏛️ Larsson Line Institutional Backtest <span class="badge">5-Year Multi-Asset</span></h1>
            <div class="meta">
                Period: <strong>{spot_res.get('start_date')}</strong> to <strong>{spot_res.get('end_date')}</strong> &nbsp;|&nbsp; 
                Initial: <strong>${sm.get('initial_capital', 100000):,.0f}</strong> &nbsp;|&nbsp; 
                Universe: <strong>Crypto, US Equities, Commodities</strong>
            </div>
        </header>

        <div class="grid">
            <div class="card">
                <div class="title">Spot Final Equity</div>
                <div class="value" style="color: var(--green);">${sm.get('final_equity', 0):,.2f}</div>
                <div style="font-size: 12px; color: var(--green); margin-top: 4px;">+{sm.get('total_return_pct', 0):.1f}% (+{sm.get('cagr', 0):.1f}%/yr)</div>
            </div>
            <div class="card">
                <div class="title">Hedge 2x Final Equity</div>
                <div class="value" style="color: var(--gold);">${hm.get('final_equity', 0):,.2f}</div>
                <div style="font-size: 12px; color: var(--gold); margin-top: 4px;">+{hm.get('total_return_pct', 0):.1f}% (+{hm.get('cagr', 0):.1f}%/yr)</div>
            </div>
            <div class="card">
                <div class="title">Spot Max Drawdown</div>
                <div class="value" style="color: var(--blue);">{sm.get('max_drawdown_pct', 0):.2f}%</div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Sharpe: {sm.get('sharpe_ratio', 0):.2f} | PF: {st.get('profit_factor', 0):.2f}</div>
            </div>
            <div class="card">
                <div class="title">Hedge Max Drawdown</div>
                <div class="value" style="color: var(--blue);">{hm.get('max_drawdown_pct', 0):.2f}%</div>
                <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">Sharpe: {hm.get('sharpe_ratio', 0):.2f} | PF: {ht.get('profit_factor', 0):.2f}</div>
            </div>
        </div>

        <div class="chart-box">
            <div class="legend">
                <div class="leg-item"><div class="dot" style="background: var(--green);"></div> 🟢 Spot Only Equity Curve</div>
                <div class="leg-item"><div class="dot" style="background: var(--gold);"></div> 🟡 Long + Hedge Short (2x)</div>
            </div>
            <svg viewBox="0 0 800 260" style="width: 100%; height: auto; display: block;">
                <!-- Grid Lines -->
                <line x1="20" y1="20" x2="780" y2="20" stroke="#1E2636" stroke-dasharray="4" />
                <line x1="20" y1="130" x2="780" y2="130" stroke="#1E2636" stroke-dasharray="4" />
                <line x1="20" y1="240" x2="780" y2="240" stroke="#1E2636" stroke-dasharray="4" />
                <!-- Equity Paths -->
                <path d="{spot_path}" fill="none" stroke="#10B981" stroke-width="2.5" />
                <path d="{hedge_path}" fill="none" stroke="#F59E0B" stroke-width="2.5" />
            </svg>
        </div>

        <div class="table-box">
            <table>
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>🟢 Spot Only</th>
                        <th>🟡 Long + Hedge Short (2x)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td>Total Return</td><td>+{sm.get('total_return_pct', 0):.2f}%</td><td>+{hm.get('total_return_pct', 0):.2f}%</td></tr>
                    <tr><td>CAGR (Annualized Return)</td><td>+{sm.get('cagr', 0):.2f}%</td><td>+{hm.get('cagr', 0):.2f}%</td></tr>
                    <tr><td>Max Drawdown</td><td>{sm.get('max_drawdown_pct', 0):.2f}%</td><td>{hm.get('max_drawdown_pct', 0):.2f}%</td></tr>
                    <tr><td>Max Drawdown Duration</td><td>{sm.get('max_drawdown_duration_days', 0)} days</td><td>{hm.get('max_drawdown_duration_days', 0)} days</td></tr>
                    <tr><td>Annual Volatility</td><td>{sm.get('annualized_volatility_pct', 0):.2f}%</td><td>{hm.get('annualized_volatility_pct', 0):.2f}%</td></tr>
                    <tr><td>Sharpe Ratio</td><td>{sm.get('sharpe_ratio', 0):.2f}</td><td>{hm.get('sharpe_ratio', 0):.2f}</td></tr>
                    <tr><td>Sortino Ratio</td><td>{sm.get('sortino_ratio', 0):.2f}</td><td>{hm.get('sortino_ratio', 0):.2f}</td></tr>
                    <tr><td>Calmar Ratio</td><td>{sm.get('calmar_ratio', 0):.2f}</td><td>{hm.get('calmar_ratio', 0):.2f}</td></tr>
                    <tr><td>Profit Factor</td><td>{st.get('profit_factor', 0):.2f}</td><td>{ht.get('profit_factor', 0):.2f}</td></tr>
                    <tr><td>Win Rate</td><td>{st.get('win_rate_pct', 0):.1f}%</td><td>{ht.get('win_rate_pct', 0):.1f}%</td></tr>
                    <tr><td>Total Trades</td><td>{st.get('total_trades', 0)}</td><td>{ht.get('total_trades', 0)}</td></tr>
                    <tr><td>Expectancy (R-multiple)</td><td>+{st.get('expectancy_r', 0):.2f}R</td><td>+{ht.get('expectancy_r', 0):.2f}R</td></tr>
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"Exported interactive HTML report to {filepath}")
        return filepath
