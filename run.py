#!/usr/bin/env python3
"""
ETF Conviction Leader Backtester

Usage:
    python run.py "50% US equity, 50% Gold"
    python run.py "100% US equity"
    python run.py "33% Tech, 33% Gold, 34% Defense"
"""

import sys
import time
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents import agent1_interpreter, agent2_holdings, agent3_backtest


def fmt_pct(v: float) -> str:
    return f"{v * 100:+.1f}%"


def fmt_pct_plain(v: float) -> str:
    return f"{v * 100:.1f}%"


def print_header(text: str):
    print(f"\n{'─' * 60}")
    print(f"  {text}")
    print(f"{'─' * 60}")


def print_metrics_table(results: dict, etf_list: list[dict]):
    strategy = results["strategy"]
    spy = results["spy"]
    mix = results["mix"]
    date_range = results["date_range"]

    sleeves = " + ".join(
        f"{item['theme'].title()} ({item['weight']*100:.0f}% → {item['etf']})"
        for item in etf_list
    )

    print_header("BACKTEST RESULTS")
    print(f"  Strategy : {sleeves}")
    print(f"  Period   : {date_range[0]} → {date_range[1]}")
    print()
    print(f"  {'Metric':<22} {'Conviction':>12} {'SPY':>10} {'ETF Mix':>10}")
    print(f"  {'─'*22} {'─'*12} {'─'*10} {'─'*10}")
    print(f"  {'Total Return':<22} {fmt_pct_plain(strategy['TotalReturn']):>12} {fmt_pct_plain(spy['TotalReturn']):>10} {fmt_pct_plain(mix['TotalReturn']):>10}")
    print(f"  {'CAGR':<22} {fmt_pct_plain(strategy['CAGR']):>12} {fmt_pct_plain(spy['CAGR']):>10} {fmt_pct_plain(mix['CAGR']):>10}")
    print(f"  {'Sharpe Ratio':<22} {strategy['Sharpe']:>12.2f} {spy['Sharpe']:>10.2f} {mix['Sharpe']:>10.2f}")
    print(f"  {'Max Drawdown':<22} {fmt_pct_plain(strategy['MaxDrawdown']):>12} {fmt_pct_plain(spy['MaxDrawdown']):>10} {fmt_pct_plain(mix['MaxDrawdown']):>10}")
    print()

    # Annual return table
    all_years = sorted(set(
        list(strategy["Annual"].keys()) +
        list(spy["Annual"].keys())
    ))
    if all_years:
        print(f"  {'Year':<8} {'Conviction':>12} {'SPY':>10} {'ETF Mix':>10}")
        print(f"  {'─'*8} {'─'*12} {'─'*10} {'─'*10}")
        for yr in all_years:
            s = strategy["Annual"].get(yr, 0)
            b = spy["Annual"].get(yr, 0)
            m = mix["Annual"].get(yr, 0)
            print(f"  {yr:<8} {fmt_pct_plain(s):>12} {fmt_pct_plain(b):>10} {fmt_pct_plain(m):>10}")

    print()
    print(f"  Chart saved → {results['chart_path']}")

    print()
    print("  ⚠  DISCLAIMER: N-PORT filings are submitted 60 days after quarter-end.")
    print("     In live trading this strategy would have a ~2-month information lag.")
    print("     Backtest assumes immediate execution at quarter-end. Past performance")
    print("     does not predict future results.")
    print()


def main():
    parser = argparse.ArgumentParser(description="ETF Conviction Leader Backtester")
    parser.add_argument("allocation", nargs="+", help='Allocation string e.g. "50% US equity, 50% Gold"')
    parser.add_argument("--annual", action="store_true", help="Rebalance annually instead of quarterly (~4x faster)")
    args = parser.parse_args()

    prompt = " ".join(args.allocation)
    freq = "annual" if args.annual else "quarterly"
    t0 = time.time()

    print(f"\n🔍 ETF Conviction Leader Backtester")
    print(f"   Input: \"{prompt}\"  [rebalance: {freq}]")

    # Agent 1: Parse allocation and resolve ETFs
    print_header("AGENT 1 — Interpreting allocation...")
    etf_list = agent1_interpreter.run(prompt)
    for item in etf_list:
        print(f"  {item['theme'].title():30} → {item['etf']:6}  ({item['weight']*100:.0f}%)")

    # Agent 2: Fetch holdings from SEC N-PORT
    label = "annual" if freq == "annual" else "quarterly"
    print_header(f"AGENT 2 — Fetching {label} holdings from SEC EDGAR...")
    max_periods = 7 if freq == "annual" else 28
    holdings_history = agent2_holdings.run(etf_list, max_periods=max_periods, freq=freq)

    if not holdings_history:
        print("ERROR: No holdings data retrieved. Cannot backtest.")
        sys.exit(1)

    # Trim etf_list to only ETFs that have holdings data
    etf_list = [item for item in etf_list if item["etf"] in holdings_history]
    if not etf_list:
        print("ERROR: No ETFs with holdings data.")
        sys.exit(1)

    # Renormalize weights after any dropped sleeves
    total_w = sum(item["weight"] for item in etf_list)
    for item in etf_list:
        item["weight"] = item["weight"] / total_w

    # Agent 3: Backtest + metrics + chart
    print_header("AGENT 3 — Running backtest...")
    results = agent3_backtest.run(holdings_history, etf_list)

    # Print results
    print_metrics_table(results, etf_list)

    elapsed = time.time() - t0
    print(f"  Completed in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
