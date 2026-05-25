#!/usr/bin/env python3
"""
SQL query CLI for holdings.db

Usage:
    python3.11 query_db.py "SELECT * FROM etf_info"
    python3.11 query_db.py "SELECT * FROM top_holdings WHERE etf='VOO'"
    python3.11 query_db.py  # interactive mode

Useful queries:
    -- All ETFs by theme
    SELECT ticker, theme, asset_class FROM etf_info ORDER BY asset_class, theme;

    -- When did NVDA become the top holding of any ETF?
    SELECT etf, start_date, end_date FROM top_holdings WHERE stock='NVDA';

    -- What is each ETF holding RIGHT NOW?
    SELECT e.ticker, e.theme, h.stock, h.start_date
    FROM etf_info e JOIN top_holdings h ON e.ticker=h.etf
    WHERE h.end_date IS NULL ORDER BY e.asset_class;

    -- Which ETF held AAPL the longest?
    SELECT etf, stock, start_date, end_date,
           COALESCE(end_date, date('now')) as effective_end
    FROM top_holdings WHERE stock='AAPL'
    ORDER BY start_date;

    -- All gold-theme ETFs
    SELECT * FROM etf_info WHERE asset_class='GOLD' OR theme LIKE '%gold%';

    -- ETFs that switched top holding more than twice
    SELECT etf, COUNT(*) as changes FROM top_holdings
    GROUP BY etf HAVING changes > 2 ORDER BY changes DESC;
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "cache" / "holdings.db"

SAMPLE_QUERIES = [
    ("All ETFs by theme",
     "SELECT ticker, name, theme, asset_class FROM etf_info ORDER BY asset_class, theme"),
    ("Current top holding per ETF",
     "SELECT e.ticker, e.theme, h.stock, h.start_date FROM etf_info e "
     "JOIN top_holdings h ON e.ticker=h.etf WHERE h.end_date IS NULL ORDER BY e.asset_class"),
    ("Which ETFs ever held NVDA",
     "SELECT etf, start_date, end_date FROM top_holdings WHERE stock='NVDA'"),
    ("ETFs with most holding changes",
     "SELECT etf, COUNT(*) as periods FROM top_holdings GROUP BY etf ORDER BY periods DESC"),
]


def run_query(conn: sqlite3.Connection, sql: str):
    try:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        if not cols:
            print("(no results)")
            return
        # Column widths
        widths = [max(len(c), max((len(str(r[i] or "")) for r in rows), default=0))
                  for i, c in enumerate(cols)]
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        print(fmt.format(*cols))
        print("  ".join("─" * w for w in widths))
        for row in rows:
            print(fmt.format(*[str(v) if v is not None else "—" for v in row]))
        print(f"\n{len(rows)} row(s)")
    except Exception as e:
        print(f"Error: {e}")


def main():
    if not DB_PATH.exists():
        print(f"DB not found at {DB_PATH}")
        print("Run:  python3.11 build_holdings_db.py")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)

    if len(sys.argv) > 1:
        # One-shot query
        sql = " ".join(sys.argv[1:])
        run_query(conn, sql)
        conn.close()
        return

    # Interactive mode
    print(f"Holdings DB — {DB_PATH}")
    print("Type SQL or a number for a sample query. Ctrl+C to exit.\n")
    for i, (label, _) in enumerate(SAMPLE_QUERIES, 1):
        print(f"  [{i}] {label}")
    print()

    while True:
        try:
            raw = input("sql> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if not raw:
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(SAMPLE_QUERIES):
            label, sql = SAMPLE_QUERIES[int(raw) - 1]
            print(f"-- {label}\n{sql}\n")
            run_query(conn, sql)
        else:
            run_query(conn, raw)
        print()

    conn.close()


if __name__ == "__main__":
    main()
