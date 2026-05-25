#!/bin/bash
# ETF Conviction Leader Backtester — Mac launcher
# Double-click or run: bash launch.sh

set -e
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║     ETF Conviction Leader Backtester             ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. Find Python 3.11+ ─────────────────────────────────────────────────────
PYTHON=""
for candidate in python3.11 python3.12 python3.13 python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print(sys.version_info >= (3,11))" 2>/dev/null)
        if [ "$ver" = "True" ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.11 or newer is required."
    echo ""
    echo "Install it from https://www.python.org/downloads/"
    echo "or via Homebrew:  brew install python@3.11"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo "✓ Python: $($PYTHON --version)"

# ── 2. Create virtual environment (once) ─────────────────────────────────────
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creating virtual environment..."
    $PYTHON -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"

# ── 3. Install / upgrade dependencies ────────────────────────────────────────
echo "→ Checking dependencies..."
pip install --quiet --upgrade pip
pip install --quiet \
    anthropic \
    streamlit \
    matplotlib \
    numpy \
    pandas \
    plotly \
    requests \
    yfinance
echo "✓ Dependencies ready"

# ── 4. Anthropic API key ──────────────────────────────────────────────────────
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo ""
    echo "┌─ Anthropic API key not found ────────────────────────────────┐"
    echo "│                                                               │"
    echo "│  The key is used when you type a custom theme that the app   │"
    echo "│  doesn't recognise (e.g. 'water infrastructure', 'uranium'). │"
    echo "│  Claude resolves it to the best matching ETF ticker.         │"
    echo "│                                                               │"
    echo "│  WITHOUT a key:                                               │"
    echo "│    • All 12 quick-example buttons work normally              │"
    echo "│    • Known themes (Gold, Tech, Nasdaq, etc.) work normally   │"
    echo "│    • Unrecognised custom themes will show an error           │"
    echo "│                                                               │"
    echo "│  To add a key later, re-run this script and paste it in,    │"
    echo "│  or set it permanently in your terminal:                     │"
    echo "│    export ANTHROPIC_API_KEY=sk-ant-...                       │"
    echo "│  Get a key at: https://console.anthropic.com/account/keys   │"
    echo "└───────────────────────────────────────────────────────────────┘"
    echo ""
    read -p "Paste your API key, or press Enter to skip: " ANTHROPIC_API_KEY
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        echo "✓ Skipping API key — custom theme resolution will be unavailable"
    else
        export ANTHROPIC_API_KEY
        echo "✓ API key set"
    fi
else
    echo "✓ API key set"
fi

# ── 5. Launch app ─────────────────────────────────────────────────────────────
echo ""
echo "→ Starting app... (opens in your browser at http://localhost:8501)"
echo "   Press Ctrl+C to stop."
echo ""
streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
