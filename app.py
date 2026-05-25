"""
ETF Conviction Leader Backtester — Streamlit frontend

Run:
    streamlit run app.py
"""

import io
import os
import smtplib
import sys
import time
from contextlib import redirect_stdout
from email.mime.text import MIMEText
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from agents import agent1_interpreter, agent2_holdings, agent3_backtest

# ── PDF report generator ────────────────────────────────────────────────────────
_GS_BLUE   = "#7297C5"
_GS_DARK   = "#181818"
_GS_GRAY   = "#888888"
_GS_LIGHT  = "#F4F5F7"
_GS_GREEN  = "#2E8B57"
_GS_RED    = "#C0392B"

def _build_trade_rows(etf_list, holdings_history):
    rows = []
    for item in etf_list:
        etf = item["etf"]
        if etf not in holdings_history:
            continue
        h = sorted(holdings_history[etf], key=lambda x: x["date"])
        prev = None
        for entry in h:
            tkr, dt = entry["ticker"], entry["date"][:10]
            if tkr != prev:
                if prev:
                    rows.append({"Date": dt, "Action": "SELL", "Ticker": prev,
                                 "Sleeve": f"{item['theme'].title()} ({etf})"})
                rows.append({"Date": dt, "Action": "BUY", "Ticker": tkr,
                             "Sleeve": f"{item['theme'].title()} ({etf})"})
                prev = tkr
    return pd.DataFrame(rows).sort_values("Date").reset_index(drop=True) if rows else pd.DataFrame()


def generate_pdf(results, etf_list, holdings_history, allocation_str, freq):
    strategy  = results["strategy"]
    spy       = results["spy"]
    mix       = results["mix"]
    date_range = results["date_range"]
    cum       = results["cumulative"]
    df_trades = _build_trade_rows(etf_list, holdings_history)

    fig = plt.figure(figsize=(8.5, 11), facecolor="white")
    gs  = gridspec.GridSpec(
        7, 4, figure=fig,
        hspace=0.55, wspace=0.4,
        left=0.08, right=0.92, top=0.91, bottom=0.05,
    )

    # ── Header bar ────────────────────────────────────────────────────────────
    header_ax = fig.add_axes([0, 0.93, 1, 0.07])
    header_ax.set_facecolor(_GS_BLUE)
    header_ax.axis("off")
    header_ax.text(0.03, 0.55, "ETF CONVICTION LEADER — BACKTEST REPORT",
                   color="white", fontsize=10, fontweight="bold",
                   va="center", transform=header_ax.transAxes, family="sans-serif")
    header_ax.text(0.97, 0.55, f"Generated {pd.Timestamp.now():%d %b %Y}",
                   color="white", fontsize=7, va="center", ha="right",
                   transform=header_ax.transAxes, family="sans-serif")

    # ── Allocation subtitle ───────────────────────────────────────────────────
    sub_ax = fig.add_subplot(gs[0, :])
    sub_ax.axis("off")
    sub_ax.text(0, 0.8, allocation_str,
                fontsize=9, color=_GS_DARK, fontweight="bold", family="sans-serif")
    sub_ax.text(0, 0.35,
                f"Period: {date_range[0]} → {date_range[1]}  ·  Rebalancing: {freq}  ·  "
                f"Dividends included  ·  No fees modeled",
                fontsize=7, color=_GS_GRAY, family="sans-serif")

    # ── ETF selection row ──────────────────────────────────────────────────────
    etf_ax = fig.add_subplot(gs[1, :])
    etf_ax.set_facecolor(_GS_LIGHT)
    etf_ax.set_xlim(0, len(etf_list))
    etf_ax.set_ylim(0, 1)
    etf_ax.axis("off")
    # blue top rule
    etf_ax.axhline(y=0.97, color=_GS_BLUE, linewidth=1.5, xmin=0, xmax=1)
    etf_ax.text(0.02, 0.80, "SELECTED ETFs", fontsize=6, color=_GS_BLUE,
                fontweight="bold", family="sans-serif", va="center")
    for i, item in enumerate(etf_list):
        cx = i + 0.5
        etf_ax.text(cx, 0.50, item["etf"], fontsize=11, color=_GS_DARK,
                    fontweight="bold", family="sans-serif", ha="center", va="center")
        etf_ax.text(cx, 0.22, item["theme"].title(), fontsize=6, color=_GS_GRAY,
                    family="sans-serif", ha="center", va="center")
        etf_ax.text(cx, 0.06, f"{item['weight']*100:.0f}%", fontsize=7,
                    color=_GS_BLUE, fontweight="bold",
                    family="sans-serif", ha="center", va="center")
        if i > 0:
            etf_ax.axvline(x=i, ymin=0.05, ymax=0.85, color="#DDDDDD", linewidth=0.8)

    # ── KPI boxes ─────────────────────────────────────────────────────────────
    kpis = [
        ("TOTAL RETURN",  f"{strategy['TotalReturn']*100:.1f}%",
         f"{(strategy['TotalReturn']-spy['TotalReturn'])*100:+.1f}pp vs SPY"),
        ("CAGR",          f"{strategy['CAGR']*100:.1f}%",
         f"{(strategy['CAGR']-spy['CAGR'])*100:+.1f}pp vs SPY"),
        ("SHARPE RATIO",  f"{strategy['Sharpe']:.2f}",
         f"{strategy['Sharpe']-spy['Sharpe']:+.2f} vs SPY"),
        ("MAX DRAWDOWN",  f"{strategy['MaxDrawdown']*100:.1f}%",
         f"{(strategy['MaxDrawdown']-spy['MaxDrawdown'])*100:+.1f}pp vs SPY"),
    ]
    for col, (label, value, delta) in enumerate(kpis):
        ax = fig.add_subplot(gs[2, col])
        ax.set_facecolor(_GS_LIGHT)
        ax.axis("off")
        ax.axhline(y=0.92, xmin=0, xmax=1, color=_GS_BLUE, linewidth=2)
        ax.text(0.1, 0.65, label, fontsize=6, color=_GS_BLUE, fontweight="bold",
                family="sans-serif", transform=ax.transAxes, va="center")
        ax.text(0.1, 0.35, value, fontsize=14, color=_GS_DARK, fontweight="bold",
                family="sans-serif", transform=ax.transAxes, va="center")
        d_color = _GS_GREEN if delta.startswith("+") else _GS_RED
        ax.text(0.1, 0.10, delta, fontsize=6, color=d_color,
                family="sans-serif", transform=ax.transAxes, va="center")

    # ── Cumulative returns chart ───────────────────────────────────────────────
    ax_cum = fig.add_subplot(gs[3:5, :])
    ax_cum.set_facecolor(_GS_LIGHT)
    for spine in ax_cum.spines.values():
        spine.set_visible(False)
    ax_cum.tick_params(colors=_GS_GRAY, labelsize=7)
    ax_cum.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax_cum.set_title("Cumulative Return", fontsize=8, color=_GS_DARK,
                     fontweight="bold", loc="left", pad=6)

    strat_pct = (cum["strategy"] - 1) * 100
    spy_pct   = (cum["spy"]      - 1) * 100
    mix_pct   = (cum["mix"]      - 1) * 100

    ax_cum.plot(strat_pct.index, strat_pct.values, color=_GS_BLUE,  lw=2,   label="Conviction Strategy")
    ax_cum.plot(spy_pct.index,   spy_pct.values,   color=_GS_GRAY,  lw=1.2, linestyle="--", label="SPY")
    ax_cum.plot(mix_pct.index,   mix_pct.values,   color="#C06030", lw=1.2, linestyle=":",  label="ETF Mix")
    ax_cum.axhline(0, color="#CCCCCC", lw=0.5)
    ax_cum.legend(fontsize=6, framealpha=0, labelcolor=_GS_DARK)
    ax_cum.grid(axis="y", color="#DDDDDD", lw=0.5)

    # ── Annual returns bar chart ───────────────────────────────────────────────
    ax_ann = fig.add_subplot(gs[5, :])
    ax_ann.set_facecolor(_GS_LIGHT)
    for spine in ax_ann.spines.values():
        spine.set_visible(False)
    ax_ann.tick_params(colors=_GS_GRAY, labelsize=7)
    ax_ann.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:.0f}%"))
    ax_ann.set_title("Annual Returns", fontsize=8, color=_GS_DARK,
                     fontweight="bold", loc="left", pad=6)

    ann_s = strategy["Annual"]
    ann_b = spy["Annual"]
    years = sorted(set(list(ann_s.keys()) + list(ann_b.keys())))
    x = np.arange(len(years))
    w = 0.35
    ax_ann.bar(x - w/2, [ann_s.get(yr, 0)*100 for yr in years], w,
               color=_GS_BLUE, label="Conviction")
    ax_ann.bar(x + w/2, [ann_b.get(yr, 0)*100 for yr in years], w,
               color=_GS_GRAY, alpha=0.7, label="SPY")
    ax_ann.set_xticks(x)
    ax_ann.set_xticklabels(years, fontsize=6)
    ax_ann.axhline(0, color="#CCCCCC", lw=0.5)
    ax_ann.legend(fontsize=6, framealpha=0, labelcolor=_GS_DARK)
    ax_ann.grid(axis="y", color="#DDDDDD", lw=0.5)

    # ── Trade history table ────────────────────────────────────────────────────
    ax_tr = fig.add_subplot(gs[6, :])
    ax_tr.axis("off")
    ax_tr.set_title("Trade History", fontsize=8, color=_GS_DARK,
                    fontweight="bold", loc="left", pad=4)

    if not df_trades.empty:
        tbl_data = df_trades[["Date", "Action", "Ticker", "Sleeve"]].values.tolist()
        tbl = ax_tr.table(
            cellText=tbl_data,
            colLabels=["DATE", "ACTION", "TICKER", "SLEEVE"],
            cellLoc="left", loc="upper left",
            bbox=[0, -0.1, 1, 1.0],
        )
        tbl.auto_set_font_size(False)
        tbl.set_fontsize(6)
        for (r, c), cell in tbl.get_celld().items():
            cell.set_edgecolor("#DDDDDD")
            if r == 0:
                cell.set_facecolor(_GS_BLUE)
                cell.set_text_props(color="white", fontweight="bold")
            else:
                cell.set_facecolor("white" if r % 2 == 0 else _GS_LIGHT)
                txt = cell.get_text().get_text()
                if txt == "BUY":
                    cell.set_text_props(color=_GS_GREEN, fontweight="bold")
                elif txt == "SELL":
                    cell.set_text_props(color=_GS_RED, fontweight="bold")

    # ── Footer ────────────────────────────────────────────────────────────────
    fig.text(0.08, 0.015,
             "⚠ Past performance does not predict future results. "
             "Dividends included via adjusted prices. No fees, taxes or transaction costs modeled.",
             fontsize=5.5, color=_GS_GRAY, family="sans-serif")

    buf = io.BytesIO()
    fig.savefig(buf, format="pdf", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.read()

st.set_page_config(
    page_title="ETF Conviction Backtester",
    page_icon="📈",
    layout="wide",
)

st.markdown("""
<style>
/* ── Base typography ───────────────────────────────────────────────────────── */
h1, h2, h3 { color: #181818 !important; letter-spacing: 0.01em; font-weight: 600; }
.stCaption  { color: #888888 !important; }

/* ── Example pill buttons ──────────────────────────────────────────────────── */
div[data-testid="stHorizontalBlock"] .stButton > button {
    background: transparent;
    border: 1px solid #7297C580;
    border-radius: 20px;
    color: #4A78B0;
    font-size: 0.78rem;
    padding: 0.25rem 0.75rem;
    transition: all 0.15s ease;
}
div[data-testid="stHorizontalBlock"] .stButton > button:hover {
    background: #7297C514;
    border-color: #7297C5;
    color: #2A5890;
}

/* ── Run button ────────────────────────────────────────────────────────────── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: #7297C5;
    color: #FFFFFF;
    font-weight: 700;
    border: none;
    border-radius: 3px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-size: 0.8rem;
}
div[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #5A80B0;
}

/* ── Metric cards ──────────────────────────────────────────────────────────── */
div[data-testid="stMetric"] {
    background: #F4F5F7;
    border-top: 2px solid #7297C5;
    border-left: none; border-right: none; border-bottom: none;
    border-radius: 2px;
    padding: 1rem 1.25rem;
}
div[data-testid="stMetricValue"] { color: #181818 !important; font-size: 1.6rem !important; }
div[data-testid="stMetricLabel"] { color: #7297C5 !important; font-size: 0.72rem !important; letter-spacing: 0.10em; text-transform: uppercase; }

/* ── Tabs ──────────────────────────────────────────────────────────────────── */
button[data-baseweb="tab"] { color: #888888 !important; letter-spacing: 0.04em; }
button[data-baseweb="tab"][aria-selected="true"] { color: #181818 !important; border-bottom-color: #7297C5 !important; }

/* ── Dataframe headers ─────────────────────────────────────────────────────── */
div[data-testid="stDataFrame"] th { background: #F4F5F7 !important; color: #4A78B0 !important; letter-spacing: 0.06em; text-transform: uppercase; font-size: 0.72rem !important; }

/* ── Divider ───────────────────────────────────────────────────────────────── */
hr { border-color: #E0E0E0 !important; }

/* ── Expander ──────────────────────────────────────────────────────────────── */
details summary { color: #4A78B0 !important; }
</style>
""", unsafe_allow_html=True)

# ── Session state ───────────────────────────────────────────────────────────────
if "allocation" not in st.session_state:
    st.session_state["allocation"] = "50% US equity, 50% Gold"

def _load_example(text: str) -> None:
    st.session_state["allocation"] = text

st.title("📈 ETF Conviction Leader Backtester")
st.caption(
    "Each theme sleeve holds only the ETF's #1 position by AUM weight. "
    "Rebalances when the top holding changes. Compare vs SPY and plain ETF mix."
)

st.markdown("""
<div style="background:#F4F5F7;border-left:4px solid #7297C5;padding:16px 20px;border-radius:2px;margin:12px 0 20px 0;">
  <div style="font-size:0.78rem;font-weight:700;color:#7297C5;letter-spacing:0.09em;text-transform:uppercase;margin-bottom:8px;">The Strategy</div>
  <div style="font-size:0.94rem;color:#181818;line-height:1.65;">
    Most ETF portfolios hold <em>hundreds</em> of stocks diluted across the index.
    The <strong>Conviction Leader</strong> approach asks: <em>what if you only held the #1 position?</em>
    You choose any allocation — e.g. <strong>50% US Equity + 50% Gold</strong>.
    For each sleeve we identify the ETF's single highest-conviction stock (largest AUM weight),
    hold only that, and rebalance whenever the fund's top holding rotates.
  </div>
  <div style="font-size:0.78rem;color:#888888;margin-top:10px;">
    Data: SEC N-PORT quarterly filings &nbsp;·&nbsp; Prices: yfinance adjusted-close (dividends included) &nbsp;·&nbsp; Benchmark: SPY
  </div>
</div>
""", unsafe_allow_html=True)

# ── Examples ────────────────────────────────────────────────────────────────────
EXAMPLES = [
    # row 1 — classic / simple
    ("🇺🇸 All US",            "100% US equity"),
    ("🥇 US + Gold",          "50% US equity, 50% Gold"),
    ("💻 Tech + Gold + 🛡 Defense", "33% Tech, 33% Gold, 34% Defense"),
    ("📡 Nasdaq + ⚡ Energy",  "50% Nasdaq, 50% Energy"),
    # row 2 — global / regional
    ("🌏 US + EM + Gold",     "40% S&P 500, 30% Emerging Markets, 30% Gold"),
    ("🇮🇳 India + Tech + Gold", "33% Tech, 33% India, 34% Gold miners"),
    ("🇯🇵 Japan + Growth + Gold", "50% US Growth, 25% Japan, 25% Gold"),
    ("💊 Healthcare + 🛡 Defense", "50% Healthcare, 25% Defense, 25% Gold"),
    # row 3 — thematic
    ("🤖 AI + Semis + Nasdaq",  "33% Nasdaq, 33% Semiconductors, 34% AI"),
    ("🌿 Clean Energy + EM",   "50% Clean Energy, 25% India, 25% Emerging Markets"),
    ("💰 Dividend + REIT",     "50% Dividend, 30% Real Estate, 20% Energy"),
    ("🌍 Diversified 4x",     "25% Tech, 25% Energy, 25% Gold, 25% Emerging Markets"),
]

st.caption("Quick examples — click to load:")
_rows = [EXAMPLES[i:i+4] for i in range(0, len(EXAMPLES), 4)]
for _row in _rows:
    _cols = st.columns(len(_row))
    for _col, (label, query) in zip(_cols, _row):
        _col.button(label, on_click=_load_example, args=(query,), use_container_width=True)

# ── Inputs ─────────────────────────────────────────────────────────────────────
col_input, col_mode, col_dca = st.columns([3, 1, 1])

with col_input:
    allocation = st.text_input(
        "Allocation",
        key="allocation",
        placeholder="e.g. 33% Tech, 33% Gold, 34% Defense",
        help="Use % weights and theme names. Weights are auto-normalized.",
    )

with col_mode:
    annual = st.checkbox(
        "Annual rebalancing",
        value=True,
        help="Annual: ~7 data points per ETF, 3x faster. Quarterly: ~28 data points, more granular.",
    )

with col_dca:
    dca_mode = st.checkbox(
        "DCA comparison",
        value=False,
        help="Compare lump-sum vs dollar-cost averaging. Same total capital, different timing.",
    )
    if dca_mode:
        dca_freq   = st.selectbox("DCA frequency", ["Quarterly", "Monthly", "Annual"], index=0)
        period_inv = st.number_input(
            "Frequency investment ($)", min_value=100, max_value=1_000_000,
            value=1_000, step=100,
            help="Amount invested at each period (e.g. $1 000 per quarter).",
        )
    else:
        dca_freq   = "Quarterly"
        period_inv = 1_000

_current_year = __import__("datetime").date.today().year
col_from, col_to = st.columns(2)
with col_from:
    start_year = st.selectbox("From", list(range(2015, _current_year + 1)), index=0)
with col_to:
    end_year = st.selectbox("To", list(range(2015, _current_year + 1)), index=_current_year - 2015)

run = st.button("▶  Run Backtest", type="primary", use_container_width=False)

# ── Run ────────────────────────────────────────────────────────────────────────
if run and allocation.strip():
    freq = "annual" if annual else "quarterly"
    max_periods = 7 if annual else 28

    t0 = time.time()

    with st.status("Running backtest…", expanded=True) as status:

        # Agent 1
        st.write("**Agent 1** — Interpreting allocation…")
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                etf_list = agent1_interpreter.run(allocation)
        except Exception as e:
            err = str(e)
            if "api_key" in err or "authentication" in err.lower() or "ANTHROPIC_API_KEY" in err:
                st.error(
                    "**Unknown theme — Anthropic API key needed.**\n\n"
                    "One of your themes isn't in the built-in map, so Claude is needed to resolve it.\n\n"
                    "**Fix:** close this tab, go back to Terminal, press Ctrl+C to stop the app, "
                    "then rerun:\n"
                    "```\nbash launch.sh\n```\n"
                    "When prompted, paste your Anthropic API key "
                    "(get one at https://console.anthropic.com/account/keys).\n\n"
                    "**Or:** switch to a supported theme — click any of the quick-example buttons above."
                )
            else:
                st.error(f"Agent 1 failed: {e}")
            st.stop()

        sleeve_str = "  ·  ".join(
            f"**{i['theme'].title()}** → `{i['etf']}` ({i['weight']*100:.0f}%)"
            for i in etf_list
        )
        st.markdown(f"✅ {sleeve_str}")

        # Agent 2 — show cache status per ETF before fetching
        cached_etfs = [i["etf"] for i in etf_list if agent2_holdings._load_holdings_cache(i["etf"], freq)]
        cold_etfs   = [i["etf"] for i in etf_list if not agent2_holdings._load_holdings_cache(i["etf"], freq)]

        if cached_etfs:
            st.write(f"**Agent 2** — Cache hit: `{'` `'.join(cached_etfs)}` ✅")
        if cold_etfs:
            st.write(f"**Agent 2** — Fetching from SEC EDGAR: `{'` `'.join(cold_etfs)}` ⏳ (~30–90s first time)")

        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                holdings_history = agent2_holdings.run(
                    etf_list, max_periods=max_periods, freq=freq
                )
        except Exception as e:
            st.error(f"Agent 2 failed: {e}")
            st.stop()

        if not holdings_history:
            st.error("No holdings data returned — cannot backtest.")
            st.stop()

        for etf, h in holdings_history.items():
            st.markdown(f"✅ `{etf}`: {len(h)} {'years' if freq == 'annual' else 'quarters'} resolved")

        # Trim + renormalize dropped sleeves
        etf_list = [item for item in etf_list if item["etf"] in holdings_history]
        total_w = sum(item["weight"] for item in etf_list)
        for item in etf_list:
            item["weight"] /= total_w

        # Agent 3
        st.write("**Agent 3** — Running backtest & generating chart…")
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                results = agent3_backtest.run(
                    holdings_history, etf_list,
                    start_year=start_year, end_year=end_year,
                    dca=dca_mode,
                    dca_frequency=dca_freq.lower(),
                    period_investment=float(period_inv),
                )
        except Exception as e:
            st.error(f"Agent 3 failed: {e}")
            st.stop()

        elapsed = time.time() - t0
        status.update(label=f"Done in {elapsed:.0f}s", state="complete", expanded=False)

    # ── Results ────────────────────────────────────────────────────────────────
    st.divider()

    strategy = results["strategy"]
    spy = results["spy"]
    mix = results["mix"]
    date_range = results["date_range"]

    st.subheader("Backtest Results")
    st.caption(
        f"Period: **{date_range[0]}** → **{date_range[1]}**  ·  "
        f"Rebalancing: **{freq}**"
    )

    # ── ETF selection cards ────────────────────────────────────────────────────
    cards_html = "<div style='display:flex;gap:10px;margin:8px 0 20px 0;'>"
    for item in etf_list:
        cards_html += f"""
        <div style='flex:1;background:#F4F5F7;border-top:3px solid #7297C5;
                    padding:12px 8px;border-radius:2px;text-align:center;min-width:0;'>
          <div style='font-size:1.35rem;font-weight:700;color:#181818;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{item['etf']}</div>
          <div style='font-size:0.7rem;color:#888;margin-top:3px;
                      text-transform:uppercase;letter-spacing:0.07em;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{item['theme'].title()}</div>
          <div style='font-size:0.8rem;font-weight:700;color:#7297C5;margin-top:4px;'>{item['weight']*100:.0f}%</div>
        </div>"""
    cards_html += "</div>"
    st.markdown(cards_html, unsafe_allow_html=True)

    # KPI cards
    m1, m2, m3, m4 = st.columns(4)

    def delta(strat_val, spy_val, pct=True):
        d = strat_val - spy_val
        return f"{d*100:+.1f}pp vs SPY" if pct else f"{d:+.2f} vs SPY"

    m1.metric(
        "Total Return",
        f"{strategy['TotalReturn']*100:.1f}%",
        delta(strategy["TotalReturn"], spy["TotalReturn"]),
    )
    m2.metric(
        "CAGR",
        f"{strategy['CAGR']*100:.1f}%",
        delta(strategy["CAGR"], spy["CAGR"]),
    )
    m3.metric(
        "Sharpe Ratio",
        f"{strategy['Sharpe']:.2f}",
        delta(strategy["Sharpe"], spy["Sharpe"], pct=False),
    )
    m4.metric(
        "Max Drawdown",
        f"{strategy['MaxDrawdown']*100:.1f}%",
        delta(strategy["MaxDrawdown"], spy["MaxDrawdown"]),
        delta_color="inverse",
    )

    # Comparison table
    st.subheader("Metrics Comparison")
    rows = {
        "Total Return": [
            f"{strategy['TotalReturn']*100:.1f}%",
            f"{spy['TotalReturn']*100:.1f}%",
            f"{mix['TotalReturn']*100:.1f}%",
        ],
        "CAGR": [
            f"{strategy['CAGR']*100:.1f}%",
            f"{spy['CAGR']*100:.1f}%",
            f"{mix['CAGR']*100:.1f}%",
        ],
        "Sharpe Ratio": [
            f"{strategy['Sharpe']:.2f}",
            f"{spy['Sharpe']:.2f}",
            f"{mix['Sharpe']:.2f}",
        ],
        "Max Drawdown": [
            f"{strategy['MaxDrawdown']*100:.1f}%",
            f"{spy['MaxDrawdown']*100:.1f}%",
            f"{mix['MaxDrawdown']*100:.1f}%",
        ],
    }
    df_metrics = pd.DataFrame(rows, index=["Conviction Strategy", "SPY", "ETF Mix"]).T
    st.dataframe(df_metrics, use_container_width=False)

    # Annual returns table
    all_years = sorted(
        set(list(strategy["Annual"].keys()) + list(spy["Annual"].keys()))
    )
    if all_years:
        st.subheader("Annual Returns")
        ann_rows = {
            yr: {
                "Conviction": f"{strategy['Annual'].get(yr, 0)*100:.1f}%",
                "SPY": f"{spy['Annual'].get(yr, 0)*100:.1f}%",
                "ETF Mix": f"{mix['Annual'].get(yr, 0)*100:.1f}%",
            }
            for yr in all_years
        }
        st.dataframe(pd.DataFrame(ann_rows).T, use_container_width=False)

    # ── Build trade list (needed for chart markers + table) ────────────────────
    trade_rows = []
    for item in etf_list:
        etf = item["etf"]
        if etf not in holdings_history:
            continue
        h = sorted(holdings_history[etf], key=lambda x: x["date"])
        prev_ticker = None
        for entry in h:
            ticker = entry["ticker"]
            date   = entry["date"][:10]
            weight = item["weight"]
            if ticker != prev_ticker:
                if prev_ticker is not None:
                    trade_rows.append({
                        "Date": date,
                        "Sleeve": f"{item['theme'].title()} ({etf})",
                        "Action": "SELL",
                        "Ticker": prev_ticker,
                        "Sleeve Weight": f"{weight*100:.0f}%",
                    })
                trade_rows.append({
                    "Date": date,
                    "Sleeve": f"{item['theme'].title()} ({etf})",
                    "Action": "BUY",
                    "Ticker": ticker,
                    "Sleeve Weight": f"{weight*100:.0f}%",
                })
                prev_ticker = ticker

    df_trades = pd.DataFrame(trade_rows).sort_values("Date").reset_index(drop=True) if trade_rows else pd.DataFrame()

    # ── Interactive chart ──────────────────────────────────────────────────────
    st.subheader("Chart")
    st.caption(
        "✅ **Dividends included** (yfinance adjusted-close prices = total return).  "
        "⚠️ **No fees modeled** — no ETF expense ratios, no transaction costs, no taxes."
    )
    cum = results["cumulative"]

    def _drawdown(s):
        return (s / s.cummax() - 1) * 100

    def _add_trade_markers(fig, cum_series, y_series, df_trades):
        """Overlay BUY (▲ green) and SELL (▼ red) markers snapped to closest trading day."""
        if df_trades.empty:
            return
        buy_dates, buy_y, buy_labels = [], [], []
        sell_dates, sell_y, sell_labels = [], [], []
        for _, row in df_trades.iterrows():
            try:
                idx = cum_series.index.asof(pd.Timestamp(row["Date"]))
            except Exception:
                continue
            if pd.isnull(idx) or idx not in y_series.index:
                continue
            yval = float(y_series.loc[idx])
            label = f"{row['Action']} {row['Ticker']}<br>{row['Sleeve']}"
            if row["Action"] == "BUY":
                buy_dates.append(idx); buy_y.append(yval); buy_labels.append(label)
            else:
                sell_dates.append(idx); sell_y.append(yval); sell_labels.append(label)
        if buy_dates:
            fig.add_trace(go.Scatter(
                x=buy_dates, y=buy_y, mode="markers", name="BUY",
                marker=dict(symbol="triangle-up", color="#3DBA7A", size=13, line=dict(width=1, color="#08101F")),
                text=buy_labels, hovertemplate="%{text}<extra></extra>",
                showlegend=True,
            ))
        if sell_dates:
            fig.add_trace(go.Scatter(
                x=sell_dates, y=sell_y, mode="markers", name="SELL",
                marker=dict(symbol="triangle-down", color="#E05C5C", size=13, line=dict(width=1, color="#08101F")),
                text=sell_labels, hovertemplate="%{text}<extra></extra>",
                showlegend=True,
            ))

    _GS_PAPER  = "#FFFFFF"   # white
    _GS_PLOT   = "#F4F5F7"   # light gray plot area
    _GS_BLUE   = "#7297C5"   # GS steel blue — conviction strategy
    _GS_SILVER = "#999999"   # SPY — neutral gray
    _GS_ORANGE = "#C06030"   # ETF Mix — muted rust
    _GS_GRID   = "#E8E8E8"   # subtle light grid
    _GS_TEXT   = "#888888"   # axis labels

    _LAYOUT = dict(
        hovermode="x unified",
        paper_bgcolor=_GS_PAPER,
        plot_bgcolor=_GS_PLOT,
        font=dict(color=_GS_TEXT),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(color="#E8EAF0")),
        xaxis=dict(gridcolor=_GS_GRID, showline=False, zeroline=False),
        yaxis=dict(gridcolor=_GS_GRID, showline=False, zeroline=False),
        margin=dict(t=30, b=0),
    )

    _tab_labels = ["📈 Cumulative Returns", "📉 Drawdown", "📊 Annual Returns"]
    if dca_mode and results.get("dca"):
        _tab_labels.append("💰 DCA vs Lump Sum")
    _tabs = st.tabs(_tab_labels)
    tab_cum, tab_dd, tab_ann = _tabs[0], _tabs[1], _tabs[2]
    tab_dca = _tabs[3] if len(_tabs) > 3 else None

    with tab_cum:
        cum_pct = (cum["strategy"] - 1) * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=cum["strategy"].index, y=cum_pct,
            name="Conviction Strategy", line=dict(color=_GS_BLUE, width=2.5),
        ))
        fig.add_trace(go.Scatter(
            x=cum["spy"].index, y=(cum["spy"] - 1) * 100,
            name="SPY", line=dict(color=_GS_SILVER, width=1.5, dash="dot"),
        ))
        fig.add_trace(go.Scatter(
            x=cum["mix"].index, y=(cum["mix"] - 1) * 100,
            name="ETF Mix", line=dict(color=_GS_ORANGE, width=1.5, dash="dash"),
        ))
        _add_trade_markers(fig, cum["strategy"], cum_pct, df_trades)
        fig.update_layout(yaxis_title="Cumulative Return (%)", height=420, **_LAYOUT)
        fig.update_yaxes(ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

    with tab_dd:
        dd_pct = _drawdown(cum["strategy"])
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=cum["strategy"].index, y=dd_pct,
            name="Conviction Strategy", line=dict(color=_GS_BLUE, width=2),
            fill="tozeroy", fillcolor="rgba(114,151,197,0.10)",
        ))
        fig2.add_trace(go.Scatter(
            x=cum["spy"].index, y=_drawdown(cum["spy"]),
            name="SPY", line=dict(color=_GS_SILVER, width=1.5, dash="dot"),
        ))
        _add_trade_markers(fig2, cum["strategy"], dd_pct, df_trades)
        fig2.update_layout(yaxis_title="Drawdown (%)", height=380, **_LAYOUT)
        fig2.update_yaxes(ticksuffix="%")
        st.plotly_chart(fig2, use_container_width=True)

    with tab_ann:
        ann_strat = strategy["Annual"]
        ann_spy   = spy["Annual"]
        years_sorted = sorted(set(list(ann_strat.keys()) + list(ann_spy.keys())))
        fig3 = go.Figure()
        fig3.add_trace(go.Bar(
            x=years_sorted, y=[ann_strat.get(yr, 0) * 100 for yr in years_sorted],
            name="Conviction Strategy", marker_color=_GS_BLUE,
        ))
        fig3.add_trace(go.Bar(
            x=years_sorted, y=[ann_spy.get(yr, 0) * 100 for yr in years_sorted],
            name="SPY", marker_color=_GS_SILVER,
        ))
        fig3.update_layout(barmode="group", yaxis_title="Annual Return (%)", height=370, **_LAYOUT)
        fig3.update_yaxes(ticksuffix="%")
        st.plotly_chart(fig3, use_container_width=True)

    # ── DCA vs Lump Sum tab ────────────────────────────────────────────────────
    if tab_dca is not None:
        with tab_dca:
            dca_data = results["dca"]
            freq_label = dca_data["frequency"].capitalize()

            fig_dca = go.Figure()
            fig_dca.add_trace(go.Scatter(
                x=dca_data["lump_value"].index, y=dca_data["lump_value"],
                name="Conviction — Lump Sum",
                line=dict(color=_GS_BLUE, width=2.5),
            ))
            fig_dca.add_trace(go.Scatter(
                x=dca_data["portfolio_value"].index, y=dca_data["portfolio_value"],
                name=f"Conviction — DCA {freq_label} ({dca_data['n_tranches']}× ${dca_data['tranche']:,.0f})",
                line=dict(color="#1A6B9B", width=2.5, dash="dash"),
            ))
            fig_dca.add_trace(go.Scatter(
                x=dca_data["spy_lump_value"].index, y=dca_data["spy_lump_value"],
                name="SPY — Lump Sum",
                line=dict(color=_GS_SILVER, width=1.5, dash="dot"),
            ))
            fig_dca.add_trace(go.Scatter(
                x=dca_data["spy_dca_value"].index, y=dca_data["spy_dca_value"],
                name=f"SPY — DCA {freq_label}",
                line=dict(color="#BBBBBB", width=1.5, dash="dashdot"),
            ))
            fig_dca.add_trace(go.Scatter(
                x=dca_data["invested"].index, y=dca_data["invested"],
                name="Capital deployed",
                line=dict(color="#555555", width=1, dash="longdash"),
                fill="tozeroy", fillcolor="rgba(0,0,0,0.04)",
            ))
            fig_dca.update_layout(height=460, yaxis_title="Portfolio Value ($)", **_LAYOUT)
            fig_dca.update_yaxes(tickprefix="$", tickformat=",.0f")
            st.plotly_chart(fig_dca, use_container_width=True)

            # Summary table
            st.subheader("Final Comparison")
            _rows_dca = {
                "Final Value": [
                    f"${dca_data['lump_final']:,.0f}",
                    f"${dca_data['final_value']:,.0f}",
                    f"${dca_data['spy_dca_final']:,.0f}",
                ],
                "Total Invested": [
                    f"${dca_data['total_invested']:,.0f}",
                    f"${dca_data['total_invested']:,.0f}",
                    f"${dca_data['total_invested']:,.0f}",
                ],
                "Profit": [
                    f"${dca_data['lump_profit']:,.0f}",
                    f"${dca_data['profit']:,.0f}",
                    f"${dca_data['spy_dca_profit']:,.0f}",
                ],
                "ROI": [
                    f"{dca_data['lump_roi']*100:.1f}%",
                    f"{dca_data['roi']*100:.1f}%",
                    f"{dca_data['spy_dca_roi']*100:.1f}%",
                ],
            }
            df_dca_metrics = pd.DataFrame(
                _rows_dca,
                index=[
                    "Conviction — Lump Sum",
                    f"Conviction — DCA ({freq_label.lower()})",
                    f"SPY — DCA ({freq_label.lower()})",
                ],
            ).T
            st.dataframe(df_dca_metrics, use_container_width=False)

            st.caption(
                f"**DCA** invests ${dca_data['tranche']:,.0f} every {freq_label.lower()} "
                f"({dca_data['n_tranches']} payments → ${dca_data['total_invested']:,.0f} total).  "
                f"**Lump Sum** deploys the equivalent ${dca_data['total_invested']:,.0f} on day 1.  "
                "Both use the identical conviction strategy — only capital timing differs."
            )

    # ── Trade History table ────────────────────────────────────────────────────
    st.subheader("Trade History")
    if not df_trades.empty:
        def color_action(val):
            return "color: #2ca02c; font-weight: bold" if val == "BUY" else "color: #d62728; font-weight: bold"
        st.dataframe(
            df_trades.style.map(color_action, subset=["Action"]),
            use_container_width=False,
            hide_index=True,
        )
    else:
        st.caption("No trades — single holding throughout.")

    # Holdings history per sleeve
    with st.expander("Holdings history (what the strategy held each period)"):
        for item in etf_list:
            etf = item["etf"]
            if etf not in holdings_history:
                continue
            h = holdings_history[etf]
            rows_h = [
                {"Period": r["date"][:7], "Ticker": r["ticker"], "Source": r["source"]}
                for r in h
            ]
            # Mark changes
            prev = None
            for r in rows_h:
                r["Changed"] = "🔄" if r["Ticker"] != prev else ""
                prev = r["Ticker"]
            st.markdown(f"**{item['theme'].title()} → {etf}**")
            st.dataframe(pd.DataFrame(rows_h), use_container_width=False, hide_index=True)

    st.caption(
        "⚠️ N-PORT filings are submitted ~60 days after quarter-end. "
        "In live trading this strategy would carry a ~2-month information lag. "
        "Past performance does not predict future results."
    )

    # ── PDF export ─────────────────────────────────────────────────────────────
    st.divider()
    with st.spinner("Preparing PDF…"):
        pdf_bytes = generate_pdf(results, etf_list, holdings_history, allocation, freq)
    fname = f"backtest_{pd.Timestamp.now():%Y%m%d}.pdf"
    st.download_button(
        label="⬇  Download PDF report",
        data=pdf_bytes,
        file_name=fname,
        mime="application/pdf",
        type="primary",
    )

elif run and not allocation.strip():
    st.warning("Enter an allocation first.")

# ── Custom backtest CTA ─────────────────────────────────────────────────────────
st.divider()
st.markdown("""
<div style="text-align:center;padding:8px 0 4px 0;">
  <div style="font-size:1.15rem;font-weight:700;color:#181818;margin-bottom:6px;">Want a backtest built for <em>your</em> strategy?</div>
  <div style="font-size:0.88rem;color:#555;max-width:520px;margin:0 auto 16px auto;line-height:1.6;">
    Describe your strategy and I'll build a personalised backtest for it — custom ETFs, custom date range, full PDF report.
  </div>
</div>
""", unsafe_allow_html=True)

with st.form("custom_backtest_request", clear_on_submit=True):
    col_a, col_b = st.columns(2)
    with col_a:
        req_name  = st.text_input("Your name", placeholder="Optional")
    with col_b:
        req_email = st.text_input("Your email *", placeholder="you@example.com")
    req_strategy = st.text_area(
        "Describe your strategy *",
        placeholder="e.g. focus on high-momentum tech leaders + gold hedge, rebalance quarterly — any themes, any date range.",
        height=100,
    )
    submitted = st.form_submit_button("Send Request", type="primary")

if submitted:
    if not req_email.strip() or not req_strategy.strip():
        st.warning("Please fill in your email and strategy description.")
    else:
        import urllib.parse
        name_line = f"Name: {req_name.strip()}\n" if req_name.strip() else ""
        body = (
            f"{name_line}"
            f"Email: {req_email.strip()}\n\n"
            f"Strategy request:\n{req_strategy.strip()}"
        )
        mailto = "mailto:tradeukinvest@gmail.com?subject=" + urllib.parse.quote("Custom Backtest Request") + "&body=" + urllib.parse.quote(body)
        st.success("Ready to send! Click the button below to open your email client.")
        st.markdown(f'<a href="{mailto}" target="_blank" style="display:inline-block;background:#ff4b4b;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:700;">Open Email to Send Request</a>', unsafe_allow_html=True)
