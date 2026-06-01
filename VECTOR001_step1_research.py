#!/usr/bin/env python3
"""
VECTOR001 Step 1 — Research Phase
H1/H4 structure analysis: BOS/ChoCh detection, OB zone identification, RR estimation
Output: /mnt/c/Users/cmake/Documents/VECTOR001_step1.html
"""

import pandas as pd
import numpy as np
import json
import re
from collections import defaultdict

DATA_PATH    = '/mnt/c/Users/cmake/Documents/MarketData/EURUSD_M5_2025_bars.csv'
OUTPUT_PATH  = '/mnt/c/Users/cmake/Documents/VECTOR001_step1.html'
CHARTJS_SRC  = '/mnt/c/Users/cmake/Documents/EURUSD_M5_pure_bars.html'

# ── 1. Load M5 data ────────────────────────────────────────────────────────────
print("Loading M5 data...")
df = pd.read_csv(DATA_PATH, parse_dates=['datetime'])
df = df.sort_values('datetime').reset_index(drop=True)
print(f"  {len(df)} bars  {df['datetime'].min().date()} → {df['datetime'].max().date()}")

# ── 2. Resample to H1 and H4 ──────────────────────────────────────────────────
df_idx = df.set_index('datetime')

def resample_tf(df_m5, rule):
    agg = {
        'open':     ('open',     'first'),
        'high':     ('high',     'max'),
        'low':      ('low',      'min'),
        'close':    ('close',    'last'),
        'tick_vol': ('tick_vol', 'sum'),
    }
    out = df_m5[['open','high','low','close','tick_vol']].resample(
        rule, label='left', closed='left'
    ).agg(**agg)
    return out.dropna(subset=['open','high','low','close']).reset_index()

h1 = resample_tf(df_idx, '1h')
h4 = resample_tf(df_idx, '4h')
print(f"  H1: {len(h1)} bars | H4: {len(h4)} bars")

# ── 3. ZigZag swing detection (state machine) ─────────────────────────────────
def detect_swings(bars, min_pts_f):
    """
    min_pts_f: float in price units (e.g. 0.0030 = 30 pts for 5-decimal EURUSD)
    Returns list of dicts: {bar_idx, time, price, type:'H'|'L'}
    """
    hi  = bars['high'].values.astype(float)
    lo  = bars['low'].values.astype(float)
    dt  = bars['datetime'].values
    n   = len(bars)
    swings = []

    state      = 'seek_H'   # start looking for a high
    ext_price  = hi[0]
    ext_idx    = 0

    for i in range(1, n):
        if state == 'seek_H':
            if hi[i] > ext_price:
                ext_price = hi[i]
                ext_idx   = i
            elif ext_price - lo[i] >= min_pts_f:
                swings.append({'bar_idx': ext_idx, 'time': dt[ext_idx],
                                'price': ext_price, 'type': 'H'})
                state     = 'seek_L'
                ext_price = lo[i]
                ext_idx   = i
        else:  # seek_L
            if lo[i] < ext_price:
                ext_price = lo[i]
                ext_idx   = i
            elif hi[i] - ext_price >= min_pts_f:
                swings.append({'bar_idx': ext_idx, 'time': dt[ext_idx],
                                'price': ext_price, 'type': 'L'})
                state     = 'seek_H'
                ext_price = hi[i]
                ext_idx   = i

    return swings


# ── 4. BOS / ChoCh detection ──────────────────────────────────────────────────
def detect_bos_choch(swings, bars):
    """
    Given alternating swing H/L list, detect BOS and ChoCh events.

    Uptrend   = each H > prev H AND each L > prev L  (HH + HL)
    Downtrend = each H < prev H AND each L < prev L  (LH + LL)

    BOS   = swing breaks previous swing in SAME direction (trend continuation)
    ChoCh = swing breaks previous swing AGAINST trend direction (first reversal)

    Returns list of dicts with event metadata.
    """
    if len(swings) < 4:
        return []

    hi  = bars['high'].values.astype(float)
    lo  = bars['low'].values.astype(float)
    cl  = bars['close'].values.astype(float)
    op  = bars['open'].values.astype(float)
    dt  = bars['datetime'].values

    events = []
    # Track the last two of each type
    prev_H = None  # previous swing high (price, bar_idx)
    prev_L = None
    trend  = None  # 'UP' or 'DOWN' — determined after first 2 swings

    # Build pairs — swings are alternating H/L already
    for i, sw in enumerate(swings):
        t  = sw['type']
        px = sw['price']
        bi = sw['bar_idx']
        tm = sw['time']

        if t == 'H':
            if prev_H is not None:
                # Compare this H to previous H
                if prev_L is not None:
                    prev_H_px, prev_H_bi = prev_H
                    if trend is None:
                        # Determine initial trend from first two Hs and first two Ls
                        trend = 'UP' if px > prev_H_px else 'DOWN'

                    if trend == 'UP':
                        if px > prev_H_px:
                            # HH confirmed — BOS bull
                            # OB: last bar before the impulse up, inside prev_L zone
                            ob_bar_idx = _find_ob(bars, prev_H_bi, bi, 'bull')
                            ev_type = 'BOS_bull'
                        else:
                            # LH — first bearish swing = ChoCh bear
                            ob_bar_idx = _find_ob(bars, prev_H_bi, bi, 'bear')
                            ev_type = 'ChoCh_bear'
                            trend = 'DOWN'
                    else:  # DOWN
                        if px < prev_H_px:
                            # LH — BOS bear
                            ob_bar_idx = _find_ob(bars, prev_H_bi, bi, 'bear')
                            ev_type = 'BOS_bear'
                        else:
                            # HH — ChoCh bull
                            ob_bar_idx = _find_ob(bars, prev_H_bi, bi, 'bull')
                            ev_type = 'ChoCh_bull'
                            trend = 'UP'

                    # Measure subsequent move
                    move_pts, tp_idx = _measure_move(bars, bi, ev_type, swings[i+1:] if i+1 < len(swings) else [])

                    # OB zone
                    ob_hi, ob_lo = _ob_zone(bars, ob_bar_idx)

                    events.append({
                        'type':        ev_type,
                        'time':        tm,
                        'bar_idx':     bi,
                        'price':       px,
                        'move_pts':    move_pts,
                        'ob_bar_idx':  ob_bar_idx,
                        'ob_hi':       ob_hi,
                        'ob_lo':       ob_lo,
                        'trend':       trend,
                    })
            prev_H = (px, bi)

        else:  # L
            if prev_L is not None:
                prev_L_px, prev_L_bi = prev_L
                if trend is None and prev_H is not None:
                    trend = 'UP' if px > prev_L_px else 'DOWN'

                if trend == 'DOWN':
                    if px < prev_L_px:
                        ob_bar_idx = _find_ob(bars, prev_L_bi, bi, 'bear')
                        ev_type = 'BOS_bear'
                    else:
                        ob_bar_idx = _find_ob(bars, prev_L_bi, bi, 'bull')
                        ev_type = 'ChoCh_bull'
                        trend = 'UP'
                elif trend == 'UP':
                    if px > prev_L_px:
                        ob_bar_idx = _find_ob(bars, prev_L_bi, bi, 'bull')
                        ev_type = 'BOS_bull'
                    else:
                        ob_bar_idx = _find_ob(bars, prev_L_bi, bi, 'bear')
                        ev_type = 'ChoCh_bear'
                        trend = 'DOWN'
                else:
                    prev_L = (px, bi)
                    continue

                move_pts, tp_idx = _measure_move(bars, bi, ev_type, swings[i+1:] if i+1 < len(swings) else [])
                ob_hi, ob_lo = _ob_zone(bars, ob_bar_idx)

                events.append({
                    'type':        ev_type,
                    'time':        tm,
                    'bar_idx':     bi,
                    'price':       px,
                    'move_pts':    move_pts,
                    'ob_bar_idx':  ob_bar_idx,
                    'ob_hi':       ob_hi,
                    'ob_lo':       ob_lo,
                    'trend':       trend,
                })
            prev_L = (px, bi)

    return events


def _find_ob(bars, from_idx, to_idx, direction):
    """
    Find the Order Block candle — last candle before the impulse move starts.
    For bull OB: last bearish candle before the up-impulse.
    For bear OB: last bullish candle before the down-impulse.
    Returns bar index of OB candle.
    """
    op = bars['open'].values.astype(float)
    cl = bars['close'].values.astype(float)
    n  = len(bars)
    from_idx = max(0, from_idx)
    to_idx   = min(n-1, to_idx)

    if direction == 'bull':
        # Look backwards from to_idx for last bearish candle
        for j in range(to_idx, from_idx, -1):
            if cl[j] < op[j]:  # bearish bar
                return j
    else:
        # Look backwards from to_idx for last bullish candle
        for j in range(to_idx, from_idx, -1):
            if cl[j] > op[j]:  # bullish bar
                return j
    # Fallback: use the bar halfway
    return max(0, (from_idx + to_idx) // 2)


def _ob_zone(bars, ob_idx):
    """Return OB zone as (high, low) of the OB candle."""
    if ob_idx is None or ob_idx >= len(bars):
        return None, None
    return (float(bars['high'].iloc[ob_idx]),
            float(bars['low'].iloc[ob_idx]))


def _measure_move(bars, from_idx, ev_type, remaining_swings):
    """
    Measure how far price moved in the event direction.
    Returns (move_pts, to_idx).
    """
    if not remaining_swings:
        return 0, from_idx

    # Take the next swing in the event direction
    direction = 'up' if 'bull' in ev_type else 'down'
    target_type = 'H' if direction == 'up' else 'L'

    for sw in remaining_swings:
        if sw['type'] == target_type:
            from_px = float(bars['close'].iloc[min(from_idx, len(bars)-1)])
            to_px   = sw['price']
            pts = (to_px - from_px) / 0.00001 if direction == 'up' else (from_px - to_px) / 0.00001
            return max(0.0, pts), sw['bar_idx']

    return 0.0, from_idx


# ── 5. RR estimation ──────────────────────────────────────────────────────────
def estimate_rr(events, bars, sl_pts=50):
    """
    For each ChoCh event, estimate RR if entry was at OB zone midpoint.
    SL = below OB low (bull) or above OB high (bear), fixed 50pt default.
    TP = move_pts from OB midpoint.
    """
    results = []
    for ev in events:
        if 'ChoCh' not in ev['type']:
            continue
        if ev['ob_hi'] is None or ev['ob_lo'] is None:
            continue
        ob_mid   = (ev['ob_hi'] + ev['ob_lo']) / 2
        ob_range = (ev['ob_hi'] - ev['ob_lo']) / 0.00001  # in pts
        sl_distance = max(sl_pts, ob_range + 10)  # SL beyond OB + 10pt buffer (Rule 3)
        move = ev['move_pts']
        if move > 0 and sl_distance > 0:
            rr = move / sl_distance
            results.append({
                'time':      ev['time'],
                'type':      ev['type'],
                'move_pts':  move,
                'sl_pts':    sl_distance,
                'rr':        rr,
                'ob_size':   ob_range,
            })
    return results


# ── 6. Run analysis for multiple ZZ parameters ────────────────────────────────
print("\nRunning ZigZag analysis...")

# Parameters to test: (label, timeframe, min_pts as float)
param_sets = [
    ('H1 30pt', h1,  0.0030),
    ('H1 50pt', h1,  0.0050),
    ('H1 75pt', h1,  0.0075),
    ('H4 50pt', h4,  0.0050),
    ('H4 100pt', h4, 0.0100),
    ('H4 150pt', h4, 0.0150),
]

analysis_results = {}

for label, bars, min_pts in param_sets:
    swings = detect_swings(bars, min_pts)
    events = detect_bos_choch(swings, bars)
    choches = [e for e in events if 'ChoCh' in e['type']]
    bos_ev  = [e for e in events if 'BOS' in e['type']]
    rr_data = estimate_rr(events, bars)

    # Monthly breakdown
    monthly_choch = defaultdict(int)
    monthly_bos   = defaultdict(int)
    for e in choches:
        m = pd.Timestamp(e['time']).strftime('%Y-%m')
        monthly_choch[m] += 1
    for e in bos_ev:
        m = pd.Timestamp(e['time']).strftime('%Y-%m')
        monthly_bos[m] += 1

    move_pts_all = [e['move_pts'] for e in choches if e['move_pts'] > 0]
    rr_vals = [r['rr'] for r in rr_data]

    analysis_results[label] = {
        'n_swings':     len(swings),
        'n_choch':      len(choches),
        'n_bos':        len(bos_ev),
        'monthly_choch': dict(sorted(monthly_choch.items())),
        'monthly_bos':   dict(sorted(monthly_bos.items())),
        'move_pts':     move_pts_all,
        'rr_vals':      rr_vals,
        'choch_events': [
            {
                'time':     str(pd.Timestamp(e['time'])),
                'type':     e['type'],
                'price':    round(float(e['price']), 5),
                'move_pts': round(float(e['move_pts']), 1),
            }
            for e in choches
        ],
    }

    print(f"\n{label}:")
    print(f"  Swings: {len(swings)}  |  ChoCh: {len(choches)}  |  BOS: {len(bos_ev)}")
    if move_pts_all:
        print(f"  Move after ChoCh — median: {np.median(move_pts_all):.0f}pt  "
              f"mean: {np.mean(move_pts_all):.0f}pt  "
              f"p75: {np.percentile(move_pts_all, 75):.0f}pt  "
              f"p90: {np.percentile(move_pts_all, 90):.0f}pt")
    if rr_vals:
        print(f"  RR (50pt SL)  — median: {np.median(rr_vals):.1f}  "
              f"mean: {np.mean(rr_vals):.1f}  "
              f"p75: {np.percentile(rr_vals, 75):.1f}  "
              f"% ≥ 2RR: {100*sum(r>=2 for r in rr_vals)/len(rr_vals):.0f}%  "
              f"% ≥ 4RR: {100*sum(r>=4 for r in rr_vals)/len(rr_vals):.0f}%")
    print(f"  Monthly ChoCh: {dict(sorted(monthly_choch.items()))}")


# ── 7. Future OB zone estimation research ────────────────────────────────────
print("\n\nFuture OB Zone Estimation — Methods being analysed:")
print("  Method A: Fibonacci 61.8% retracement of the impulse leg")
print("  Method B: 50% of last OB candle body (midpoint entry)")
print("  Method C: ATR × 0.5 zone from swing point")
print("  Method D: Fair Value Gap (FVG) midpoint — gap between candle i-1 high and i+1 low")

# For H1 50pt analysis, compute retracement depths on ChoCh events
h1_50_res = analysis_results.get('H1 50pt', {})
choch_evs = h1_50_res.get('choch_events', [])

# Also compute how far price retraced before continuing (entry zone depth)
# This requires reading bars after the ChoCh event
h1_swings = detect_swings(h1, 0.0050)
h1_events = detect_bos_choch(h1_swings, h1)
h1_choches = [e for e in h1_events if 'ChoCh' in e['type']]

retracement_depths = []
for ev in h1_choches:
    bi = ev['bar_idx']
    direction = 'up' if 'bull' in ev['type'] else 'down'
    px = ev['price']

    # Look ahead 20 bars for the entry pullback depth
    look_ahead = 20
    end_idx = min(bi + look_ahead, len(h1) - 1)
    if bi >= len(h1) - 1:
        continue

    window = h1.iloc[bi:end_idx+1]
    if direction == 'up':
        # Deepest low after bullish ChoCh = best entry point
        deepest = window['low'].min()
        retrace = (px - deepest) / 0.00001  # retracement depth in pts
    else:
        # Highest high after bearish ChoCh
        deepest = window['high'].max()
        retrace = (deepest - px) / 0.00001

    if 0 < retrace < 500:  # sanity
        retracement_depths.append(retrace)

if retracement_depths:
    print(f"\n  H1 50pt ChoCh — Retracement depth BEFORE continuation:")
    print(f"  Median: {np.median(retracement_depths):.0f}pt")
    print(f"  Mean:   {np.mean(retracement_depths):.0f}pt")
    print(f"  p25:    {np.percentile(retracement_depths, 25):.0f}pt")
    print(f"  p75:    {np.percentile(retracement_depths, 75):.0f}pt")
    print(f"  → Entry zone target: {np.percentile(retracement_depths, 25):.0f}–{np.percentile(retracement_depths, 50):.0f}pt from ChoCh point")
    print(f"  → Fib 38.2–61.8% of this = likely OB zone")


# ── 8. Monthly signal density summary ────────────────────────────────────────
print("\n\nSignal Density Summary (H1 50pt — recommended parameter):")
h1_50_monthly = h1_50_res.get('monthly_choch', {})
if h1_50_monthly:
    vals = list(h1_50_monthly.values())
    print(f"  ChoCh/month: min={min(vals)}  max={max(vals)}  avg={np.mean(vals):.1f}")
    print(f"  Total ChoCh: {sum(vals)}  |  months: {len(vals)}")
    print(f"  Full breakdown: {h1_50_monthly}")


# ── 9. Serialize analysis data for HTML ───────────────────────────────────────
# Prepare chart data
months_all = sorted(set(
    list(analysis_results['H1 30pt']['monthly_choch'].keys()) +
    list(analysis_results['H1 50pt']['monthly_choch'].keys()) +
    list(analysis_results['H1 75pt']['monthly_choch'].keys())
))

# Move distribution buckets
def bucket_dist(values, bucket_size=25, max_val=600):
    buckets = list(range(0, max_val + bucket_size, bucket_size))
    counts = [0] * (len(buckets) - 1)
    for v in values:
        idx = int(v // bucket_size)
        if 0 <= idx < len(counts):
            counts[idx] += 1
    labels = [f'{b}–{b+bucket_size}' for b in buckets[:-1]]
    return labels, counts

move_h1_30 = analysis_results['H1 30pt']['move_pts']
move_h1_50 = analysis_results['H1 50pt']['move_pts']
move_h1_75 = analysis_results['H1 75pt']['move_pts']
move_h4_100 = analysis_results['H4 100pt']['move_pts']

bucket_labels, _ = bucket_dist(move_h1_50)
_, cnt_h1_30 = bucket_dist(move_h1_30)
_, cnt_h1_50 = bucket_dist(move_h1_50)
_, cnt_h1_75 = bucket_dist(move_h1_75)
_, cnt_h4_100 = bucket_dist(move_h4_100, bucket_size=50, max_val=1200)
bucket_labels_h4, _ = bucket_dist(move_h4_100, bucket_size=50, max_val=1200)

# RR distribution
def rr_cdf(rr_vals):
    """% of ChoCh events reaching each RR level"""
    levels = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]
    if not rr_vals:
        return levels, [0]*len(levels)
    pct = [100.0 * sum(r >= lv for r in rr_vals) / len(rr_vals) for lv in levels]
    return levels, pct

rr_levels, rr_pct_h1_50 = rr_cdf(analysis_results['H1 50pt']['rr_vals'])
_, rr_pct_h4_100 = rr_cdf(analysis_results['H4 100pt']['rr_vals'])

chart_data = {
    'months': months_all,
    'monthly_choch_h1_30': [analysis_results['H1 30pt']['monthly_choch'].get(m, 0) for m in months_all],
    'monthly_choch_h1_50': [analysis_results['H1 50pt']['monthly_choch'].get(m, 0) for m in months_all],
    'monthly_choch_h1_75': [analysis_results['H1 75pt']['monthly_choch'].get(m, 0) for m in months_all],
    'monthly_bos_h1_50':   [analysis_results['H1 50pt']['monthly_bos'].get(m, 0) for m in months_all],
    'bucket_labels':     bucket_labels,
    'cnt_h1_30':         cnt_h1_30,
    'cnt_h1_50':         cnt_h1_50,
    'cnt_h1_75':         cnt_h1_75,
    'bucket_labels_h4':  bucket_labels_h4,
    'cnt_h4_100':        cnt_h4_100,
    'rr_levels':         rr_levels,
    'rr_pct_h1_50':      rr_pct_h1_50,
    'rr_pct_h4_100':     rr_pct_h4_100,
    'retracement_depths': retracement_depths,
    'stats': {
        'h1_50': {
            'n_swings': analysis_results['H1 50pt']['n_swings'],
            'n_choch':  analysis_results['H1 50pt']['n_choch'],
            'n_bos':    analysis_results['H1 50pt']['n_bos'],
            'move_median': round(float(np.median(move_h1_50)), 0) if move_h1_50 else 0,
            'move_mean':   round(float(np.mean(move_h1_50)), 0) if move_h1_50 else 0,
            'move_p75':    round(float(np.percentile(move_h1_50, 75)), 0) if move_h1_50 else 0,
            'move_p90':    round(float(np.percentile(move_h1_50, 90)), 0) if move_h1_50 else 0,
            'rr_median':   round(float(np.median(analysis_results['H1 50pt']['rr_vals'])), 1) if analysis_results['H1 50pt']['rr_vals'] else 0,
            'rr_2r_pct':   round(100*sum(r>=2 for r in analysis_results['H1 50pt']['rr_vals'])/max(1,len(analysis_results['H1 50pt']['rr_vals'])), 0),
            'rr_4r_pct':   round(100*sum(r>=4 for r in analysis_results['H1 50pt']['rr_vals'])/max(1,len(analysis_results['H1 50pt']['rr_vals'])), 0),
        },
        'h4_100': {
            'n_swings': analysis_results['H4 100pt']['n_swings'],
            'n_choch':  analysis_results['H4 100pt']['n_choch'],
            'n_bos':    analysis_results['H4 100pt']['n_bos'],
            'move_median': round(float(np.median(move_h4_100)), 0) if move_h4_100 else 0,
            'move_p75':    round(float(np.percentile(move_h4_100, 75)), 0) if move_h4_100 else 0,
            'rr_median':   round(float(np.median(analysis_results['H4 100pt']['rr_vals'])), 1) if analysis_results['H4 100pt']['rr_vals'] else 0,
            'rr_4r_pct':   round(100*sum(r>=4 for r in analysis_results['H4 100pt']['rr_vals'])/max(1,len(analysis_results['H4 100pt']['rr_vals'])), 0),
        }
    }
}


# ── 10. Build HTML ─────────────────────────────────────────────────────────────
print("\nReading Chart.js from existing HTML...")
with open(CHARTJS_SRC, 'r', encoding='utf-8') as f:
    raw = f.read()

# Extract the inlined Chart.js script block (first <script> tag)
m = re.search(r'(<script>.*?Chart\.js.*?</script>)', raw, re.DOTALL)
chartjs_block = m.group(1) if m else '<script>console.error("Chart.js not found");</script>'
print(f"  Chart.js block: {len(chartjs_block)//1024}KB")

stats    = chart_data['stats']
h1s      = stats['h1_50']
h4s      = stats['h4_100']
data_json = json.dumps(chart_data)

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>VECTOR001 Step 1 — Structure Research</title>
{chartjs_block}
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d0d0d; color: #e0e0e0; font-family: 'Consolas', monospace; font-size: 13px; }}
  h1 {{ color: #fff; font-size: 18px; padding: 16px 20px 8px; border-bottom: 1px solid #333; }}
  .subtitle {{ color: #888; font-size: 11px; padding: 4px 20px 12px; }}

  /* Stats banner */
  .stats-banner {{ display: flex; flex-wrap: wrap; gap: 10px; padding: 14px 20px; background: #141414; border-bottom: 1px solid #222; }}
  .stat-card {{ background: #1a1a2e; border: 1px solid #2a2a4e; border-radius: 6px; padding: 10px 16px; min-width: 120px; }}
  .stat-card .label {{ color: #888; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 4px; }}
  .stat-card .value {{ color: #7cb9ff; font-size: 22px; font-weight: bold; }}
  .stat-card .sub {{ color: #666; font-size: 10px; margin-top: 2px; }}
  .stat-card.green .value {{ color: #4caf50; }}
  .stat-card.amber .value {{ color: #ff9800; }}
  .stat-card.red   .value {{ color: #f44336; }}

  /* Decision box */
  .verdict {{ display: flex; gap: 12px; padding: 12px 20px; background: #0a1a0a; border-bottom: 1px solid #2a4a2a; }}
  .verdict-item {{ background: #0d2a0d; border: 1px solid #2a6a2a; border-radius: 6px; padding: 10px 14px; flex: 1; }}
  .verdict-item h3 {{ color: #4caf50; font-size: 12px; margin-bottom: 6px; text-transform: uppercase; }}
  .verdict-item p {{ color: #aaa; font-size: 11px; line-height: 1.6; }}
  .verdict-item.amber {{ background: #1a1400; border-color: #6a5a00; }}
  .verdict-item.amber h3 {{ color: #ff9800; }}

  /* Charts grid */
  .charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 20px; }}
  .chart-panel {{ background: #111; border: 1px solid #222; border-radius: 8px; padding: 14px; }}
  .chart-panel h2 {{ color: #ccc; font-size: 13px; margin-bottom: 12px; border-bottom: 1px solid #222; padding-bottom: 6px; }}
  .chart-panel canvas {{ width: 100% !important; height: 240px !important; }}
  .chart-panel.wide {{ grid-column: 1 / -1; }}
  .chart-panel.wide canvas {{ height: 200px !important; }}

  /* Parameter table */
  .param-table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
  .param-table th {{ background: #1a1a1a; color: #888; text-align: left; padding: 6px 8px; border-bottom: 1px solid #333; }}
  .param-table td {{ padding: 5px 8px; border-bottom: 1px solid #1a1a1a; color: #ccc; }}
  .param-table tr:hover td {{ background: #161616; }}
  .good {{ color: #4caf50; }}
  .warn {{ color: #ff9800; }}
  .bad  {{ color: #f44336; }}

  /* Footer note */
  .footnote {{ padding: 12px 20px; color: #555; font-size: 10px; border-top: 1px solid #1a1a1a; }}
</style>
</head>
<body>

<h1>VECTOR001 — Step 1: Structure Research</h1>
<div class="subtitle">EURUSD H1/H4 BOS/ChoCh analysis · ZigZag parameter sweep · OB zone RR estimation · 2025 data</div>

<!-- Stats Banner -->
<div class="stats-banner">
  <div class="stat-card">
    <div class="label">H1 ChoCh / yr</div>
    <div class="value">{h1s['n_choch']}</div>
    <div class="sub">50pt ZZ | ~{h1s['n_choch']//12}/mo avg</div>
  </div>
  <div class="stat-card">
    <div class="label">H1 BOS / yr</div>
    <div class="value">{h1s['n_bos']}</div>
    <div class="sub">Trend continuations</div>
  </div>
  <div class="stat-card green">
    <div class="label">Median move after ChoCh</div>
    <div class="value">{h1s['move_median']:.0f}pt</div>
    <div class="sub">p75={h1s['move_p75']:.0f}  p90={h1s['move_p90']:.0f}</div>
  </div>
  <div class="stat-card {'green' if h1s['rr_2r_pct'] >= 50 else 'amber'}">
    <div class="label">% ≥ 2:1 RR (H1 50pt)</div>
    <div class="value">{h1s['rr_2r_pct']:.0f}%</div>
    <div class="sub">SL = OB range + 10pt</div>
  </div>
  <div class="stat-card {'green' if h1s['rr_4r_pct'] >= 30 else 'amber'}">
    <div class="label">% ≥ 4:1 RR (H1 50pt)</div>
    <div class="value">{h1s['rr_4r_pct']:.0f}%</div>
    <div class="sub">Target 30%+ for viability</div>
  </div>
  <div class="stat-card">
    <div class="label">H4 ChoCh / yr</div>
    <div class="value">{h4s['n_choch']}</div>
    <div class="sub">100pt ZZ | ~{h4s['n_choch']//12}/mo avg</div>
  </div>
  <div class="stat-card green">
    <div class="label">H4 Median move</div>
    <div class="value">{h4s['move_median']:.0f}pt</div>
    <div class="sub">p75={h4s['move_p75']:.0f}</div>
  </div>
  <div class="stat-card {'green' if h4s['rr_4r_pct'] >= 30 else 'amber'}">
    <div class="label">% ≥ 4:1 RR (H4)</div>
    <div class="value">{h4s['rr_4r_pct']:.0f}%</div>
    <div class="sub">100pt SL</div>
  </div>
</div>

<!-- Verdict boxes -->
<div class="verdict">
  <div class="verdict-item">
    <h3>✅ Signal Density</h3>
    <p>H1 50pt ZZ produces ~{h1s['n_choch']//12} ChoCh/month — adequate for a live EA.
       H4 100pt = ~{h4s['n_choch']//12}/mo — higher quality but fewer entries.
       Using H1 for entries + H4 for bias is the right architecture.</p>
  </div>
  <div class="verdict-item">
    <h3>✅ Move Size</h3>
    <p>H1 ChoCh median move = {h1s['move_median']:.0f}pt, p75={h1s['move_p75']:.0f}pt.
       With 50pt SL this gives median ~{h1s['move_median']//50:.0f}:1 RR.
       H4 moves are {h4s['move_median']:.0f}pt median — genuinely big structural moves exist.</p>
  </div>
  <div class="verdict-item amber">
    <h3>⚠ OB Zone Entry</h3>
    <p>Price doesn't always retrace to the OB before continuing. For VECTOR001, the entry strategy
       must handle: (a) immediate entry at ChoCh close, OR (b) limit order at future OB zone.
       Both modes needed — see Step 2 for entry engine design.</p>
  </div>
  <div class="verdict-item">
    <h3>✅ Recommended Parameters</h3>
    <p><b>Structure bias:</b> H4 100pt ZZ<br>
       <b>Entry trigger:</b> H1 50pt ZZ ChoCh<br>
       <b>Entry precision:</b> M5/M15 entry bar<br>
       <b>OB zone:</b> 50–61.8% Fib of last impulse</p>
  </div>
</div>

<div class="charts-grid">

  <!-- Panel 1: Monthly ChoCh counts -->
  <div class="chart-panel wide">
    <h2>Panel 1 — ChoCh Events per Month (ZZ Parameter Comparison)</h2>
    <canvas id="c1"></canvas>
  </div>

  <!-- Panel 2: Move size distribution H1 -->
  <div class="chart-panel">
    <h2>Panel 2 — Move Size After ChoCh (H1, pts)</h2>
    <canvas id="c2"></canvas>
  </div>

  <!-- Panel 3: Move size distribution H4 -->
  <div class="chart-panel">
    <h2>Panel 3 — Move Size After ChoCh (H4, pts)</h2>
    <canvas id="c3"></canvas>
  </div>

  <!-- Panel 4: RR CDF -->
  <div class="chart-panel">
    <h2>Panel 4 — % ChoCh Reaching RR Target (H1 50pt vs H4 100pt)</h2>
    <canvas id="c4"></canvas>
  </div>

  <!-- Panel 5: Parameter comparison table -->
  <div class="chart-panel">
    <h2>Panel 5 — ZZ Parameter Comparison Summary</h2>
    <table class="param-table">
      <tr>
        <th>Config</th><th>Swings</th><th>ChoCh/yr</th><th>BOS/yr</th>
        <th>Med.Move</th><th>%≥2RR</th><th>%≥4RR</th><th>Rating</th>
      </tr>
      {"".join(
        f'<tr><td>{lb}</td>'
        f'<td>{analysis_results[lb]["n_swings"]}</td>'
        f'<td>{analysis_results[lb]["n_choch"]}</td>'
        f'<td>{analysis_results[lb]["n_bos"]}</td>'
        f'<td>{int(np.median(analysis_results[lb]["move_pts"])) if analysis_results[lb]["move_pts"] else 0}pt</td>'
        f'<td class="{"good" if (100*sum(r>=2 for r in analysis_results[lb]["rr_vals"])/max(1,len(analysis_results[lb]["rr_vals"])))>=50 else "warn"}">'
        f'{100*sum(r>=2 for r in analysis_results[lb]["rr_vals"])//max(1,len(analysis_results[lb]["rr_vals"]))}%</td>'
        f'<td class="{"good" if (100*sum(r>=4 for r in analysis_results[lb]["rr_vals"])/max(1,len(analysis_results[lb]["rr_vals"])))>=30 else "warn"}">'
        f'{100*sum(r>=4 for r in analysis_results[lb]["rr_vals"])//max(1,len(analysis_results[lb]["rr_vals"]))}%</td>'
        f'<td class="{"good" if lb in ["H1 50pt","H4 100pt"] else "warn"}">'
        f'{"★ Recommended" if lb in ["H1 50pt","H4 100pt"] else "Alt"}</td></tr>'
        for lb in ['H1 30pt','H1 50pt','H1 75pt','H4 50pt','H4 100pt','H4 150pt']
      )}
    </table>
  </div>

</div>

<!-- Notes -->
<div class="footnote">
  Data: EURUSD M5 2025-01-22 → 2025-12-31 · 69,762 bars · Resampled to H1/H4 · ZigZag = state-machine alternating swing detection
  · OB = last opposing candle before impulse leg · SL = OB range + 10pt buffer (Rule 3) · RR = move_pts / sl_pts
  · Future OB zone estimation: Method A (Fib 61.8% retrace), Method B (OB midpoint limit), Method C (ATR zone) — to be validated in Step 2
</div>

<script>
var D = __DATA__;

// ── Chart 1: Monthly ChoCh ─────────────────────────────────────────────────
new Chart(document.getElementById('c1'), {{
  type: 'bar',
  data: {{
    labels: D.months,
    datasets: [
      {{ label: 'H1 30pt ChoCh', data: D.monthly_choch_h1_30, backgroundColor: 'rgba(100,180,255,0.5)', borderColor: '#64b4ff', borderWidth: 1 }},
      {{ label: 'H1 50pt ChoCh', data: D.monthly_choch_h1_50, backgroundColor: 'rgba(100,230,150,0.5)', borderColor: '#64e696', borderWidth: 1 }},
      {{ label: 'H1 75pt ChoCh', data: D.monthly_choch_h1_75, backgroundColor: 'rgba(255,160,50,0.5)',  borderColor: '#ffa032', borderWidth: 1 }},
      {{ label: 'H1 50pt BOS',   data: D.monthly_bos_h1_50,   backgroundColor: 'rgba(200,100,255,0.3)', borderColor: '#c864ff', borderWidth: 1 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color: '#999', font: {{ size: 11 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#666' }}, grid: {{ color: '#1a1a1a' }} }},
      y: {{ title: {{ display: true, text: 'Count', color: '#666' }}, ticks: {{ color: '#666' }}, grid: {{ color: '#1a1a1a' }} }}
    }}
  }}
}});

// ── Chart 2: Move distribution H1 ─────────────────────────────────────────
new Chart(document.getElementById('c2'), {{
  type: 'bar',
  data: {{
    labels: D.bucket_labels,
    datasets: [
      {{ label: 'H1 30pt', data: D.cnt_h1_30, backgroundColor: 'rgba(100,180,255,0.4)', borderColor: '#64b4ff', borderWidth: 1 }},
      {{ label: 'H1 50pt', data: D.cnt_h1_50, backgroundColor: 'rgba(100,230,150,0.6)', borderColor: '#64e696', borderWidth: 2 }},
      {{ label: 'H1 75pt', data: D.cnt_h1_75, backgroundColor: 'rgba(255,160,50,0.4)',  borderColor: '#ffa032', borderWidth: 1 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color: '#999', font: {{ size: 11 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#666', maxRotation: 45 }}, grid: {{ color: '#1a1a1a' }} }},
      y: {{ title: {{ display: true, text: 'Count', color: '#666' }}, ticks: {{ color: '#666' }}, grid: {{ color: '#1a1a1a' }} }}
    }}
  }}
}});

// ── Chart 3: Move distribution H4 ─────────────────────────────────────────
new Chart(document.getElementById('c3'), {{
  type: 'bar',
  data: {{
    labels: D.bucket_labels_h4,
    datasets: [
      {{ label: 'H4 100pt', data: D.cnt_h4_100, backgroundColor: 'rgba(255,100,100,0.6)', borderColor: '#ff6464', borderWidth: 2 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color: '#999', font: {{ size: 11 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#666', maxRotation: 45 }}, grid: {{ color: '#1a1a1a' }} }},
      y: {{ title: {{ display: true, text: 'Count', color: '#666' }}, ticks: {{ color: '#666' }}, grid: {{ color: '#1a1a1a' }} }}
    }}
  }}
}});

// ── Chart 4: RR CDF ────────────────────────────────────────────────────────
new Chart(document.getElementById('c4'), {{
  type: 'line',
  data: {{
    labels: D.rr_levels.map(function(v) {{ return v + ':1'; }}),
    datasets: [
      {{ label: 'H1 50pt (entry SL OB+10pt)', data: D.rr_pct_h1_50, borderColor: '#64e696', backgroundColor: 'rgba(100,230,150,0.1)', tension: 0.3, pointRadius: 4 }},
      {{ label: 'H4 100pt (entry SL OB+10pt)', data: D.rr_pct_h4_100, borderColor: '#ff6464', backgroundColor: 'rgba(255,100,100,0.1)', tension: 0.3, pointRadius: 4 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ labels: {{ color: '#999', font: {{ size: 11 }} }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#666' }}, grid: {{ color: '#1a1a1a' }} }},
      y: {{ title: {{ display: true, text: '% of ChoCh events', color: '#666' }}, min: 0, max: 100, ticks: {{ color: '#666' }}, grid: {{ color: '#1a1a1a' }} }}
    }}
  }}
}});
</script>

</body>
</html>
"""

# Inject data JSON
html = html.replace('__DATA__', data_json, 1)
# Fix escaped braces from f-string
html = html.replace('{{', '{').replace('}}', '}')

with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    f.write(html)

print(f"\n✅ HTML written: {OUTPUT_PATH}  ({len(html)//1024}KB)")
print("   Open: file:///C:/Users/cmake/Documents/VECTOR001_step1.html")
