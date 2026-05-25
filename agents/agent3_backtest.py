"""Agent 3: Downloads prices, simulates quarterly rebalancing, computes metrics, generates chart."""

from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

OUTPUT_DIR = Path(__file__).parent.parent


def _download_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Download adjusted close prices for a list of tickers."""
    if not tickers:
        return pd.DataFrame()
    try:
        data = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"]
        else:
            prices = data[["Close"]] if len(tickers) == 1 else data
            if len(tickers) == 1:
                prices.columns = tickers
        return prices.ffill().dropna(how="all")
    except Exception as e:
        print(f"  WARNING: price download failed for {tickers}: {e}")
        return pd.DataFrame()


def _normalize_to_quarter_end(date_str: str) -> pd.Timestamp:
    """Snap a date string to the nearest quarter-end business day."""
    ts = pd.Timestamp(str(date_str)[:10])
    return ts + pd.offsets.BQuarterEnd(0)


def _build_sleeve_schedule(holdings: list[dict]) -> pd.DataFrame:
    """Convert raw holdings list to a quarterly rebalance schedule."""
    rows = []
    for h in holdings:
        date = _normalize_to_quarter_end(h["date"])
        rows.append({"date": date, "ticker": h["ticker"]})
    df = pd.DataFrame(rows).drop_duplicates(subset="date").sort_values("date")
    return df.reset_index(drop=True)


def _simulate_strategy(schedules: dict, weights: dict, prices: pd.DataFrame) -> pd.Series:
    """
    Simulate the conviction strategy: hold only #1 position per sleeve.

    schedules: {etf: DataFrame with [date, ticker]}
    weights: {etf: float}
    prices: DataFrame of adjusted close prices, indexed by date

    LOSING CASES:
    1. The conviction pick itself declines: if the #1 AUM holding drops in price,
       the strategy takes that loss directly — there is no diversification within a sleeve.
    2. Chasing a momentum top: the #1 AUM holding often just had a strong run,
       so the strategy may buy near a local peak and hold through the reversal.
    3. Concentrated vs diversified: SPY holds ~500 stocks; this strategy holds one
       stock per sleeve, so a single bad pick in a sleeve causes the full sleeve weight
       to drag on the portfolio.
    """
    if prices.empty:
        return pd.Series(dtype=float)

    price_returns = prices.pct_change().fillna(0)

    # Build rebalance dates: union across all sleeves
    all_dates = sorted(set(
        d for sched in schedules.values() for d in sched["date"]
    ))

    portfolio_returns = []
    idx = prices.index

    for i, rebal_date in enumerate(all_dates):
        # Period: from this rebal date to the next
        next_date = all_dates[i + 1] if i + 1 < len(all_dates) else idx[-1]

        # Find price dates in this window
        mask = (idx > rebal_date) & (idx <= next_date)
        period_dates = idx[mask]
        if len(period_dates) == 0:
            continue

        daily_port_ret = pd.Series(0.0, index=period_dates)

        for etf, sched in schedules.items():
            w = weights.get(etf, 0.0)
            if w == 0:
                continue
            # Find the current top holding for this sleeve at rebal_date
            past = sched[sched["date"] <= rebal_date]
            if past.empty:
                past = sched.iloc[:1]
            ticker = past.iloc[-1]["ticker"]

            # LOSING CASE: ticker missing from price data → sleeve silently earns 0%
            # while still carrying its full weight. The portfolio loses the return that
            # weight *should* have generated, causing drag vs any benchmark that was
            # actually invested. This happens for small/illiquid or delisted holdings.
            if ticker not in price_returns.columns:
                continue

            sleeve_ret = price_returns.loc[period_dates, ticker].fillna(0)
            daily_port_ret += w * sleeve_ret

        portfolio_returns.append(daily_port_ret)

    if not portfolio_returns:
        return pd.Series(dtype=float)

    return pd.concat(portfolio_returns).sort_index()


def _simulate_etf_mix(etf_prices: pd.DataFrame, weights: dict) -> pd.Series:
    """Benchmark 2: weighted daily return of constituent ETFs, no rebalancing."""
    returns = etf_prices.pct_change().fillna(0)
    port = pd.Series(0.0, index=returns.index)
    for etf, w in weights.items():
        if etf in returns.columns:
            port += w * returns[etf].fillna(0)
    return port


def _compute_metrics(returns: pd.Series, rf_annual: float = 0.045) -> dict:
    """Compute CAGR, Sharpe, max drawdown, total return, annual returns."""
    if returns.empty or len(returns) < 2:
        return {"CAGR": 0, "Sharpe": 0, "MaxDrawdown": 0, "TotalReturn": 0, "Annual": {}}

    rf_daily = (1 + rf_annual) ** (1 / 252) - 1
    excess = returns - rf_daily
    n = len(returns)

    total_return = (1 + returns).prod() - 1
    cagr = (1 + total_return) ** (252 / n) - 1
    sharpe = excess.mean() / excess.std() * np.sqrt(252) if excess.std() > 0 else 0

    prices = (1 + returns).cumprod()
    # LOSING CASE: max_dd is the deepest peak-to-trough decline in the period.
    # It is always ≤ 0. A value of -0.30 means the portfolio fell 30% from its
    # previous high before recovering. The strategy "loses" whenever daily returns
    # are negative; max_dd captures the worst sustained losing streak.
    max_dd = (prices / prices.cummax() - 1).min()

    # Annual returns
    annual = (1 + returns).resample("YE").prod() - 1
    annual_dict = {str(d.year): float(v) for d, v in annual.items()}

    return {
        "CAGR": float(cagr),
        "Sharpe": float(sharpe),
        "MaxDrawdown": float(max_dd),
        "TotalReturn": float(total_return),
        "Annual": annual_dict,
    }


def _generate_chart(
    strategy_returns: pd.Series,
    spy_returns: pd.Series,
    mix_returns: pd.Series,
    etf_labels: str,
    output_path: Path,
):
    """Generate 3-panel chart: cumulative returns, annual bar chart, drawdown."""
    fig, axes = plt.subplots(3, 1, figsize=(12, 14))
    fig.suptitle(f"ETF Conviction Leader Backtest\n{etf_labels}", fontsize=13, fontweight="bold")

    # Panel 1: Cumulative returns
    ax1 = axes[0]
    for series, label, color in [
        (strategy_returns, "Conviction Strategy", "#1f77b4"),
        (spy_returns, "SPY", "#d62728"),
        (mix_returns, "ETF Mix", "#2ca02c"),
    ]:
        if not series.empty:
            cumret = (1 + series).cumprod()
            ax1.plot(cumret.index, cumret.values, label=label, color=color, linewidth=1.5)
    ax1.set_ylabel("Portfolio Value ($1 → $X)")
    ax1.set_title("Cumulative Total Return")
    ax1.legend()
    ax1.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    ax1.grid(alpha=0.3)

    # Panel 2: Annual returns bar chart
    ax2 = axes[1]
    years = sorted(set(
        list(strategy_returns.resample("YE").groups.keys()) +
        list(spy_returns.resample("YE").groups.keys())
    ))
    year_labels = [str(y.year) for y in years]
    x = np.arange(len(years))
    width = 0.28

    def annual_series(returns):
        ann = (1 + returns).resample("YE").prod() - 1
        return [float(ann.get(y, 0)) for y in years]

    for offset, series, label, color in [
        (-width, strategy_returns, "Conviction", "#1f77b4"),
        (0, spy_returns, "SPY", "#d62728"),
        (width, mix_returns, "ETF Mix", "#2ca02c"),
    ]:
        if not series.empty:
            vals = annual_series(series)
            bars = ax2.bar(x + offset, [v * 100 for v in vals], width, label=label, color=color, alpha=0.8)

    ax2.set_xticks(x)
    ax2.set_xticklabels(year_labels, rotation=45)
    ax2.set_ylabel("Annual Return (%)")
    ax2.set_title("Annual Returns")
    ax2.axhline(0, color="black", linewidth=0.5)
    ax2.legend()
    ax2.grid(alpha=0.3, axis="y")

    # Panel 3: Drawdown
    ax3 = axes[2]
    for series, label, color in [
        (strategy_returns, "Conviction Strategy", "#1f77b4"),
        (spy_returns, "SPY", "#d62728"),
        (mix_returns, "ETF Mix", "#2ca02c"),
    ]:
        if not series.empty:
            prices = (1 + series).cumprod()
            dd = (prices / prices.cummax() - 1) * 100
            ax3.fill_between(dd.index, dd.values, 0, alpha=0.3, color=color)
            ax3.plot(dd.index, dd.values, label=label, color=color, linewidth=1)
    ax3.set_ylabel("Drawdown (%)")
    ax3.set_title("Drawdown from Peak")
    ax3.legend()
    ax3.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


_DCA_FREQ = {
    "monthly":   pd.DateOffset(months=1),
    "quarterly": pd.DateOffset(months=3),
    "annual":    pd.DateOffset(years=1),
}


def _generate_dca_dates(start_str: str, end_str: str, frequency: str = "quarterly") -> list:
    """Return list of Timestamps at which DCA tranches are deployed."""
    start  = pd.Timestamp(start_str)
    end    = pd.Timestamp(end_str)
    offset = _DCA_FREQ.get(frequency, _DCA_FREQ["quarterly"])
    dates, current = [], start
    while current <= end:
        dates.append(current)
        current = current + offset
    return dates


def _simulate_dca(returns: pd.Series, dca_dates: list, period_investment: float) -> dict:
    """
    DCA simulation using the existing return series.

    Deploys period_investment dollars at each dca_date, letting each tranche compound
    at the strategy's own daily returns from its entry date onward.
    Returns dollar-value series + summary metrics.
    """
    n       = max(len(dca_dates), 1)
    tranche = period_investment          # user specifies per-period amount
    cumret  = (1 + returns).cumprod()
    port    = pd.Series(0.0, index=returns.index)

    for entry_date in dca_dates:
        ts = pd.Timestamp(entry_date)
        if ts > returns.index[-1]:
            break
        idx = cumret.index.searchsorted(ts)
        if idx >= len(cumret):
            continue
        actual_date = cumret.index[idx]
        factor      = float(cumret.iloc[idx])
        if factor == 0:
            continue
        growth = cumret / factor
        growth[cumret.index < actual_date] = 0.0
        port = port + tranche * growth

    # Cumulative deployed capital at each trading day (O(n+m))
    dca_ts = sorted(pd.Timestamp(d) for d in dca_dates)
    j, deployed = 0, []
    for date in returns.index:
        while j < len(dca_ts) and dca_ts[j] <= date:
            j += 1
        deployed.append(j * tranche)
    invested = pd.Series(deployed, index=returns.index)

    total_capital = tranche * n          # equivalent lump-sum amount
    lump_value    = total_capital * cumret
    final_val     = float(port.iloc[-1])
    total_inv     = float(invested.iloc[-1])
    lump_final    = float(lump_value.iloc[-1])

    return {
        "portfolio_value": port,
        "invested":        invested,
        "lump_value":      lump_value,
        "final_value":     final_val,
        "total_invested":  total_inv,
        "profit":          final_val - total_inv,
        "roi":             (final_val - total_inv) / total_inv if total_inv > 0 else 0.0,
        "lump_final":      lump_final,
        "lump_profit":     lump_final - total_capital,
        "lump_roi":        (lump_final - total_capital) / total_capital,
        "tranche":         tranche,
        "n_tranches":      n,
    }


def run(holdings_history: dict, etf_list: list[dict], start_year: int = None, end_year: int = None,
        dca: bool = False, dca_frequency: str = "quarterly", period_investment: float = 1_000) -> dict:
    """
    Run backtest and generate chart.

    holdings_history: {"VOO": [{"date": ..., "ticker": ..., "weight": ...}], ...}
    etf_list: [{"etf": "VOO", "weight": 0.5, "theme": "us equity"}, ...]

    Returns: {"strategy": metrics, "spy": metrics, "mix": metrics, "date_range": [...]}
    """
    weights = {item["etf"]: item["weight"] for item in etf_list}

    # Build rebalance schedules per sleeve
    schedules = {}
    all_tickers = set(["SPY"])

    for etf, holdings in holdings_history.items():
        sched = _build_sleeve_schedule(holdings)
        schedules[etf] = sched
        all_tickers.update(sched["ticker"].tolist())
        all_tickers.add(etf)

    # Find common date range across all sleeves
    sleeve_starts = []
    for sched in schedules.values():
        if not sched.empty:
            sleeve_starts.append(sched["date"].min())

    if not sleeve_starts:
        raise ValueError("No holdings data available for any sleeve.")

    start_date = max(sleeve_starts) - pd.offsets.BDay(5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = datetime.today().strftime("%Y-%m-%d")

    if start_year:
        start_str = max(start_str, f"{start_year}-01-01")
    if end_year:
        end_str = f"{end_year}-12-31"

    print(f"  Backtest window: {start_str} → {end_str}")
    print(f"  Downloading prices for {len(all_tickers)} tickers: {sorted(all_tickers)}")

    all_tickers_list = sorted(all_tickers)
    prices = _download_prices(all_tickers_list, start_str, end_str)

    if prices.empty:
        raise ValueError("Failed to download price data.")

    # Align prices to common date index
    prices = prices.loc[prices.index >= start_str]

    # Simulate the conviction strategy
    print("  Simulating conviction strategy...")
    strategy_returns = _simulate_strategy(schedules, weights, prices)

    # Align all return series to the same index
    common_idx = strategy_returns.index
    if common_idx.empty:
        raise ValueError("Strategy produced no returns — check holdings data.")

    # SPY benchmark
    spy_returns = (
        prices["SPY"].pct_change().fillna(0).loc[common_idx]
        if "SPY" in prices.columns else pd.Series(dtype=float)
    )

    # ETF mix benchmark
    etf_prices = prices.reindex(columns=list(weights.keys()))
    mix_returns = _simulate_etf_mix(etf_prices, weights).loc[common_idx]

    # Compute metrics
    strategy_metrics = _compute_metrics(strategy_returns)
    spy_metrics = _compute_metrics(spy_returns)
    mix_metrics = _compute_metrics(mix_returns)

    # Generate chart
    etf_labels = " | ".join(
        f"{item['theme'].title()} → {item['etf']} ({item['weight']*100:.0f}%)"
        for item in etf_list
    )
    chart_path = OUTPUT_DIR / "portfolio_backtest.png"
    print(f"  Generating chart → {chart_path}")
    _generate_chart(strategy_returns, spy_returns, mix_returns, etf_labels, chart_path)

    cum_strategy = (1 + strategy_returns).cumprod()
    cum_spy      = (1 + spy_returns).cumprod()
    cum_mix      = (1 + mix_returns).cumprod()

    result = {
        "strategy": strategy_metrics,
        "spy": spy_metrics,
        "mix": mix_metrics,
        "date_range": [start_str, end_str],
        "chart_path": str(chart_path),
        "cumulative": {
            "strategy": cum_strategy,
            "spy":      cum_spy,
            "mix":      cum_mix,
        },
        "returns": {
            "strategy": strategy_returns,
            "spy":      spy_returns,
            "mix":      mix_returns,
        },
    }

    if dca:
        print(f"  Computing DCA ({dca_frequency}) ${period_investment:,.0f}/period…")
        dca_dates        = _generate_dca_dates(start_str, end_str, dca_frequency)
        dca_conviction   = _simulate_dca(strategy_returns, dca_dates, period_investment)
        dca_spy          = _simulate_dca(spy_returns,      dca_dates, period_investment)
        result["dca"] = {
            **dca_conviction,
            "spy_dca_value":  dca_spy["portfolio_value"],
            "spy_lump_value": dca_spy["lump_value"],
            "spy_dca_final":  dca_spy["final_value"],
            "spy_dca_profit": dca_spy["profit"],
            "spy_dca_roi":    dca_spy["roi"],
            "dca_dates":      dca_dates,
            "frequency":      dca_frequency,
        }

    return result
