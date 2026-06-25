#!/usr/bin/env python3
"""
parse_report.py — Parse MT5 Strategy Tester HTML report and print key metrics.

Usage:
    python3 parse_report.py path/to/report.htm
    python3 parse_report.py          # auto-finds latest .htm in terminal data dir
"""

import sys
import os
import re

TERMINAL_DATA = "/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/F1138FAFA5BD40AC6E39B58188E4EE88"


def load_html(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:2] == b"\xff\xfe":
        return raw[2:].decode("utf-16-le", errors="replace")
    return raw.decode("utf-8", errors="replace")


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_float(s: str) -> float | None:
    try:
        return float(re.sub(r"[^\d.\-]", "", s.split("(")[0].strip()))
    except (ValueError, AttributeError):
        return None


def extract_summary(html: str) -> dict:
    """Extract key-value pairs from the MT5 summary table.
    Each summary row contains multiple label:value pairs in alternating cells."""
    results = {}
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        clean = [strip_tags(c) for c in cells]
        # Pairs: cells[0]=label, cells[1]=value, cells[2]=label, cells[3]=value ...
        for i in range(0, len(clean) - 1, 2):
            label = clean[i].rstrip(":")
            value = clean[i + 1]
            if label and value:
                results[label] = value
    return results


def extract_orders(html: str) -> list:
    """Extract closing order rows from the Orders table.
    Closing orders: comment is 'sl ...', 'trail ...', or 'timeout'."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL | re.IGNORECASE)
    closes = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        clean = [strip_tags(c) for c in cells]
        if len(clean) < 11:
            continue
        # Order rows: [Open Time, Order, Symbol, Type, Volume, Price, S/L, T/P, Time, State, Comment]
        order_type = clean[3].lower()
        comment    = clean[10].lower()
        state      = clean[9].lower()
        if state != "filled":
            continue
        # Closing orders have sl/trail/timeout in comment
        if comment.startswith("sl"):
            closes.append("sl")
        elif comment.startswith("trail"):
            closes.append("trail")
        elif "timeout" in comment:
            closes.append("timeout")
    return closes


def analyse(path: str):
    print(f"\nReport : {os.path.basename(path)}")
    print("=" * 58)

    html    = load_html(path)
    summary = extract_summary(html)
    closes  = extract_orders(html)

    def s(label):
        for k, v in summary.items():
            if label.lower() in k.lower():
                return v
        return "n/a"

    # ── Summary stats ──────────────────────────────────────────────
    total_trades  = parse_float(s("Total Trades")) or 0
    net_profit    = parse_float(s("Total Net Profit"))
    profit_factor = parse_float(s("Profit Factor"))
    expected_pf   = parse_float(s("Expected Payoff"))
    sharpe        = parse_float(s("Sharpe Ratio"))
    short_info    = s("Short Trades")   # "92 (44.57%)"
    long_info     = s("Long Trades")    # "72 (47.22%)"
    profit_info   = s("Profit Trades")  # "75 (45.73%)"
    max_dd_eq     = s("Equity Drawdown Maximal")

    # Extract win rates from "92 (44.57%)" strings
    def pct_from(text):
        m = re.search(r"\((\d+\.?\d*)%\)", text)
        return float(m.group(1)) if m else None

    short_wr = pct_from(short_info)
    long_wr  = pct_from(long_info)
    total_wr = pct_from(profit_info)

    print(f"  Total Trades    : {int(total_trades)}")
    print(f"  Net Profit ($)  : {net_profit}")
    print(f"  Profit Factor   : {profit_factor}")
    print(f"  Expected Payoff : {expected_pf}")
    print(f"  Sharpe Ratio    : {sharpe}")
    print(f"  Max DD (equity) : {max_dd_eq}")
    print()
    print(f"  Win Rate (ALL)  : {total_wr}%  {'✓' if total_wr and 44<=total_wr<=55 else '✗'}")
    print(f"  Win Rate (BUY)  : {long_wr}%")
    print(f"  Win Rate (SELL) : {short_wr}%")

    # ── Exit breakdown ─────────────────────────────────────────────
    if closes:
        n_sl      = closes.count("sl")
        n_trail   = closes.count("trail")
        n_timeout = closes.count("timeout")
        total_c   = len(closes)
        print()
        print(f"  --- Exit Breakdown ({total_c} closes) ---")
        print(f"  SL hit          : {n_sl}  ({100*n_sl/total_c:.1f}%)")
        print(f"  Trail stop      : {n_trail}  ({100*n_trail/total_c:.1f}%)")
        print(f"  Timeout         : {n_timeout}  ({100*n_timeout/total_c:.1f}%)")

    # ── Verdict ────────────────────────────────────────────────────
    # Research target (VECTOR003_CONTRACT.md, MODERATE preset):
    #   180–250 trades/month → 210–292 trades for 35-day window
    #   WR: 47–50%, SL rate: 48–55%
    #   If SL rate >65% → universe mismatch (wrong bars scored by GBM)
    TEST_DAYS = 35
    trades_per_day = total_trades / TEST_DAYS if total_trades else 0
    expected_lo = int(180 * TEST_DAYS / 30)   # 210
    expected_hi = int(250 * TEST_DAYS / 30)   # 291

    sl_rate = (closes.count("sl") / len(closes) * 100) if closes else None

    print()
    print(f"  --- Verdict (v2.31 local-N gate + immediate trail) ---")
    print(f"  Trades total    : {int(total_trades)}  (target {expected_lo}–{expected_hi} for 35d)")
    print(f"  Trades/day      : {trades_per_day:.1f}")

    if expected_lo <= total_trades <= expected_hi:
        print("  ✓ Trade count on target")
    elif total_trades > 800:
        print("  ✗ ~800+/day — ZZ gate not filtering. CopyBuffer read broken.")
    elif total_trades < 50:
        print("  ✗ Too few — ZZ confirmation firing (late), not formation zone.")
    else:
        delta = "low" if total_trades < expected_lo else "high"
        print(f"  ? Trade count {delta} — investigate Stage 1 or cooldown")

    if total_wr is not None:
        if 44 <= total_wr <= 55:
            print(f"  ✓ Win rate {total_wr:.1f}% — model scoring correctly")
        else:
            print(f"  ✗ Win rate {total_wr:.1f}% — outside expected range 44–55%")

    if sl_rate is not None:
        if sl_rate <= 60:
            print(f"  ✓ SL rate {sl_rate:.1f}% — universe match OK")
        else:
            print(f"  ✗ SL rate {sl_rate:.1f}% — >60% signals universe mismatch (wrong bars scored)")
    print()


def main():
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        reports = sorted(
            [f for f in os.listdir(TERMINAL_DATA) if f.endswith(".htm")],
            key=lambda f: os.path.getmtime(os.path.join(TERMINAL_DATA, f)),
            reverse=True
        )
        if not reports:
            print("No reports found.")
            sys.exit(1)
        path = os.path.join(TERMINAL_DATA, reports[0])
        print(f"Auto-selected: {reports[0]}")

    analyse(path)


if __name__ == "__main__":
    main()
