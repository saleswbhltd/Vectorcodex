//+------------------------------------------------------------------+
//|                                                  VECTOR003.mq5   |
//|        Per-class GBM scoring + running-extreme gate + 5p trail   |
//|                                                                  |
//|  Architecture:                                                   |
//|    1. M5 bar closes → EA computes feature vector                 |
//|    2. EA writes vector003_request.json                           |
//|    3. Python bridge reads, scores 8 GBMs, writes response        |
//|    4. EA reads response, validates ZZ-prox + cooldown           |
//|    5. If valid, MARKET order at bar close                        |
//|    6. Manage with 5p SL + 5p trail + 60min time stop             |
//|                                                                  |
//|  Validation (OOS, realistic 1p spread):                          |
//|    ~227 trades/month, ~48% win, +274 pips/month                  |
//|    Walk-forward across 11 months: 11/11 profitable               |
//+------------------------------------------------------------------+
#property strict
#property version   "2.31"
#property copyright "VECTOR research 2026"
#property description "Per-class GBM + local-N extreme gate + market exec + bridge watchdog"

#import "shell32.dll"
int ShellExecuteW(int hwnd, string lpOperation, string lpFile,
                  string lpParameters, string lpDirectory, int nShowCmd);
#import

//══════════════════════════════════════════════════════════════════
// INPUTS
//══════════════════════════════════════════════════════════════════
input group "=== Risk ==="
input double  InpRiskPct        = 0.5;     // % equity per trade
input int     InpMaxOpenTrades  = 4;
input int     InpMagic          = 20030001;

input group "=== Signal Filter ==="
input double  InpThreshold      = 0.70;    // max-prob threshold (0.50 wide, 0.85 strict)
input int     InpCooldownMin    = 30;      // min minutes between same-direction signals
input int     InpLocalN         = 3;       // local-extreme window: BUY only if bar[1].low=min-of-N, SELL only if bar[1].high=max-of-N
input int     InpEntryWindowBars = 15;     // (unused — kept for compatibility)

input group "=== ZigZag (must match research: D12/Dev5/Back3) ==="
input string  InpZZName         = "Market\\ZigZag Lines MTF for MT5";
input int     InpZZTmpMaxBars   = 20000;   // indicator tmp_max_bars param
input int     InpZZIndPeriod    = 0;       // indicator ind_period param (0 = current TF)
input int     InpZZDepth        = 12;
input int     InpZZDeviation    = 5;
input int     InpZZBackstep     = 3;
input int     InpZZScanBars     = 300;

input group "=== Trade Management ==="
input double  InpSLPips         = 5.0;     // initial SL distance
input double  InpTrailPips      = 5.0;     // trail distance behind max-favorable
input int     InpTimeoutMin     = 60;      // close after this many minutes

input group "=== Bridge ==="
input int     InpBridgeTimeoutMs   = 3000;   // max wait for Python response
input bool    InpAutoStartBridge   = true;   // auto-launch start_bridge.bat if no heartbeat
input int     InpBridgeStartWaitS  = 25;     // seconds to wait for heartbeat after launching
input int     InpBridgeStaleSec    = 15;     // mark bridge DOWN if heartbeat older than this
input bool    InpDrawArrows        = true;
input bool    InpShowPanel         = true;

//══════════════════════════════════════════════════════════════════
// GLOBALS
//══════════════════════════════════════════════════════════════════
double   g_pip;
datetime g_last_m5_bar = 0;
datetime g_last_sell_signal = 0;
datetime g_last_buy_signal  = 0;
int      g_signals_fired = 0;
int      g_request_id = 0;

// Bridge watchdog state
bool     g_bridge_down       = true;
double   g_last_heartbeat_ts = 0.0;     // bridge ts as unix seconds (double)
datetime g_last_hb_check     = 0;       // last time we polled heartbeat
datetime g_last_ea_lock_ts   = 0;       // last time we refreshed our EA lock
string   g_ea_identity       = "";      // terminal+chart fingerprint

// ZigZag pivot struct
struct SZZPivot
{
    datetime time;    // pivot bar time (broker)
    double   price;
    string   side;    // "HIGH" or "LOW"
    string   label;   // "HH","HL","LH","LL"
    int      shift;   // bar shift from current bar when detected
};

int      g_zz_handle         = INVALID_HANDLE;
datetime g_last_zz_pivot_seen = 0;   // deduplicate ZZ pivots

// Indicator handles — M5
int g_h_rsi14   = INVALID_HANDLE;
int g_h_atr5    = INVALID_HANDLE;
int g_h_atr14   = INVALID_HANDLE;
int g_h_atr50   = INVALID_HANDLE;
int g_h_stoch   = INVALID_HANDLE;
int g_h_wpr14   = INVALID_HANDLE;
int g_h_macd    = INVALID_HANDLE;
int g_h_bb      = INVALID_HANDLE;
int g_h_adx14   = INVALID_HANDLE;
int g_h_ema20   = INVALID_HANDLE;
int g_h_ema50   = INVALID_HANDLE;
int g_h_ema200  = INVALID_HANDLE;
// Indicator handles — H1
int g_h_h1_ema20  = INVALID_HANDLE;
int g_h_h1_ema50  = INVALID_HANDLE;
int g_h_h1_ema200 = INVALID_HANDLE;
int g_h_h1_atr14  = INVALID_HANDLE;
int g_h_h1_rsi14  = INVALID_HANDLE;
int g_h_h1_bb     = INVALID_HANDLE;  // H1 Bollinger Bands (for h1_bb_pctB)

#define MAX_POSITIONS 8

struct SPosition
{
    bool      active;
    ulong     ticket;
    datetime  entry_time;
    double    entry_price;
    double    current_sl;
    bool      is_buy;
    double    max_favorable_pips;
    double    lots;
    string    best_class;
    double    prob;
};
SPosition g_positions[MAX_POSITIONS];

//══════════════════════════════════════════════════════════════════
// HELPERS
//══════════════════════════════════════════════════════════════════
double Pip()
{
    int d = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    return (d == 5 || d == 3) ? 10.0 * _Point : _Point;
}

double GetIndicator(int handle, int buffer, int shift)
{
    double buf[];
    if(handle == INVALID_HANDLE) return 0.0;
    if(CopyBuffer(handle, buffer, shift, 1, buf) < 1) return 0.0;
    return buf[0];
}

double CalcLots(double sl_pips)
{
    double equity     = AccountInfoDouble(ACCOUNT_EQUITY);
    double risk_amount = equity * InpRiskPct / 100.0;
    double tick_size   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double tick_value  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    if(tick_size <= 0 || tick_value <= 0) return 0;
    double pip_value = (tick_value / tick_size) * g_pip;
    if(pip_value <= 0) return 0;
    double raw = risk_amount / (sl_pips * pip_value);
    double step    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double lots = MathFloor(raw / step) * step;
    if(lots < min_lot) lots = min_lot;
    if(lots > max_lot) lots = max_lot;
    return lots;
}

int CountOpen()
{
    int n = 0;
    for(int i = 0; i < MAX_POSITIONS; i++)
        if(g_positions[i].active) n++;
    return n;
}

double Normalize(double price)
{
    return NormalizeDouble(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
}

// Rolling mean of first n elements
double RolMean(const double &a[], int n)
{
    double s = 0; for(int i = 0; i < n; i++) s += a[i]; return s / n;
}
// Rolling sample std (ddof=1) of first n elements given their mean
double RolStd(const double &a[], int n, double mean)
{
    if(n < 2) return 0.0;
    double s = 0; for(int i = 0; i < n; i++) s += (a[i]-mean)*(a[i]-mean);
    return MathSqrt(s / (n-1));
}
// Population std (ddof=0)
double RolStdPop(const double &a[], int n, double mean)
{
    if(n < 1) return 0.0;
    double s = 0; for(int i = 0; i < n; i++) s += (a[i]-mean)*(a[i]-mean);
    return MathSqrt(s / n);
}
// Percentile rank of val in first n elements of arr (0..1)
double PctRank(double val, const double &a[], int n)
{
    int below = 0; for(int i = 0; i < n; i++) if(a[i] <= val) below++;
    return (double)below / n;
}

//══════════════════════════════════════════════════════════════════
// ZIGZAG PIVOT DETECTION — same indicator + settings as research
//══════════════════════════════════════════════════════════════════
// Local-3 extreme: bar[1] is the highest high / lowest low over last 3 M5 bars.
// This is the final entry gate from VECTOR003_SPEC.md Section 6.
bool IsLocalHigh(int n)
{
    double h = iHigh(_Symbol, PERIOD_M5, 1);
    for(int k = 2; k <= n; k++) if(iHigh(_Symbol, PERIOD_M5, k) > h) return false;
    return true;
}
bool IsLocalLow(int n)
{
    double l = iLow(_Symbol, PERIOD_M5, 1);
    for(int k = 2; k <= n; k++) if(iLow(_Symbol, PERIOD_M5, k) < l) return false;
    return true;
}

// Gate 1: pip-threshold ZigZag formation zone — pure price action, no indicator buffers.
// Walks InpZZScanBars of OHLC data to find the current ZZ state using a InpZZDepth-pip
// threshold (matching the research D12 = 12-pip ZigZag that trained the GBMs).
// Returns "BUY" when bar[bar_shift] is within InpZZBackstep bars of the current running LOW.
// Returns "SELL" when within InpZZBackstep bars of the current running HIGH.
// Fires on ~36-48 bars/day — the exact population the GBMs were trained on.
string PipZZFormationSide(int bar_shift)
{
    double thresh = (double)InpZZDepth * 10.0 * _Point;   // InpZZDepth pips
    int n = MathMin(InpZZScanBars, Bars(_Symbol, PERIOD_M5) - bar_shift);
    if(n < 5) return "";

    int start = bar_shift + n - 1;   // oldest bar (largest shift = farthest back)

    // Seed from oldest bar
    double h_s = iHigh(_Symbol, PERIOD_M5, start);
    double l_s = iLow (_Symbol, PERIOD_M5, start);
    bool   dir_up = (h_s >= l_s);
    double ext    = dir_up ? h_s : l_s;
    int    ext_bar = start;

    // Walk forward (decreasing shift = moving toward present)
    for(int i = start - 1; i >= bar_shift; i--)
    {
        double h = iHigh(_Symbol, PERIOD_M5, i);
        double l = iLow (_Symbol, PERIOD_M5, i);
        if(dir_up)
        {
            if(h > ext) { ext = h; ext_bar = i; }
            else if(ext - l >= thresh) { dir_up = false; ext = l; ext_bar = i; }
        }
        else
        {
            if(l < ext) { ext = l; ext_bar = i; }
            else if(h - ext >= thresh) { dir_up = true; ext = h; ext_bar = i; }
        }
    }

    // Formation zone: running extreme was within InpZZBackstep bars of bar[bar_shift]
    if(ext_bar - bar_shift > InpZZBackstep) return "";
    return dir_up ? "SELL" : "BUY";
}

bool IsTimestampLike(double v)
{
    // ZZLines MTF stores pivot time as unix timestamp in buffer 1
    return (v > 1e9 && v < 2e9);
}

// Read confirmed ZZ pivots from indicator buffer into array (oldest→newest)
bool LoadZZPivots(SZZPivot &pivots[], int &count)
{
    count = 0;
    ArrayResize(pivots, 0);
    if(g_zz_handle == INVALID_HANDLE) return false;
    int n = MathMin(InpZZScanBars, Bars(_Symbol, PERIOD_M5));
    if(n < 50) return false;

    double b0[], b1[], b4[];
    datetime times[];
    ArraySetAsSeries(b0, true); ArraySetAsSeries(b1, true);
    ArraySetAsSeries(b4, true); ArraySetAsSeries(times, true);
    if(CopyBuffer(g_zz_handle, 0, 0, n, b0) <= 0 ||
       CopyBuffer(g_zz_handle, 1, 0, n, b1) <= 0 ||
       CopyBuffer(g_zz_handle, 4, 0, n, b4) <= 0 ||
       CopyTime(_Symbol, PERIOD_M5, 0, n, times) <= 0)
        return false;

    double last_high = 0, last_low = 0;
    for(int i = n - 1; i >= 0; i--)
    {
        if(b0[i] == 0.0 || b4[i] == 0.0) continue;
        SZZPivot p;
        p.time  = IsTimestampLike(b1[i]) ? (datetime)b1[i] : times[i];
        p.price = b0[i];
        p.side  = (b4[i] > 0.0) ? "HIGH" : "LOW";
        p.shift = i;
        if(p.side == "HIGH")
        {
            p.label = (last_high > 0 && p.price > last_high) ? "HH" : "LH";
            last_high = p.price;
        }
        else
        {
            p.label = (last_low > 0 && p.price > last_low) ? "HL" : "LL";
            last_low = p.price;
        }
        int sz = ArraySize(pivots);
        ArrayResize(pivots, sz + 1);
        pivots[sz] = p;
        count++;
    }
    return count > 0;
}

// Returns true if a NEW ZZ pivot just appeared within the entry window.
// Fills pivot with its details (including bar shift).
bool LatestNewZZPivot(SZZPivot &pivot)
{
    SZZPivot pivots[];
    int count = 0;
    if(!LoadZZPivots(pivots, count) || count == 0) return false;
    SZZPivot latest = pivots[count - 1];
    if(latest.time <= g_last_zz_pivot_seen) return false;
    if(latest.shift > InpEntryWindowBars) return false;  // too old to enter
    g_last_zz_pivot_seen = latest.time;
    pivot = latest;
    return true;
}

//══════════════════════════════════════════════════════════════════
// FEATURE COMPUTATION — exact match to research/35_build_full_panel.py
// and research/34_tick_features.py.
// s = bar shift of the ZZ pivot bar (1 = last closed, 2 = two bars ago, etc.)
//══════════════════════════════════════════════════════════════════
string BuildFeaturesJSON(int s)
{
    string json = "{";
    double pip = g_pip;
    datetime bar1_broker = iTime(_Symbol, PERIOD_M5, s);  // pivot bar broker time
    double   cls = iClose(_Symbol, PERIOD_M5, s);
    double   opn = iOpen (_Symbol, PERIOD_M5, s);
    double   hi  = iHigh (_Symbol, PERIOD_M5, s);
    double   lo  = iLow  (_Symbol, PERIOD_M5, s);
    double   rng = hi - lo;
    double   body= cls - opn;

    // ── UTC time fix (broker = UTC+offset; research used Dukascopy UTC) ──────
    datetime utc_offset = TimeCurrent() - TimeGMT();   // seconds broker is ahead of UTC
    datetime bar1_utc   = bar1_broker - utc_offset;
    MqlDateTime dtu;
    TimeToStruct(bar1_utc, dtu);
    int hour_utc = dtu.hour;
    int dow      = dtu.day_of_week;

    // ── Tick features — from CopyTicksRange over bar[1] ─────────────────────
    double tick_count              = 0;
    double median_tick_interval_ms = 0;
    double max_tick_interval_ms    = 0;
    double spread_avg              = 0;
    double spread_max              = 0;
    double bid_aggressor_pct       = 0;
    double ask_aggressor_pct       = 0;
    double imbalance               = 0;
    double tick_velocity_first_half  = 0;
    double tick_velocity_second_half = 0;
    double vel_ratio_2nd_to_1st    = 0;
    double max_run_up_pips         = 0;
    double max_run_dn_pips         = 0;
    double ticks_at_high_pct       = 0;
    double ticks_at_low_pct        = 0;

    {
        MqlTick ticks[];
        datetime bar0_broker = iTime(_Symbol, PERIOD_M5, s - 1);  // bar after pivot bar
        long from_ms = (long)bar1_broker * 1000;
        long to_ms   = (long)bar0_broker * 1000 - 1;
        int n = CopyTicksRange(_Symbol, ticks, COPY_TICKS_ALL, from_ms, to_ms);
        if(n >= 4)
        {
            tick_count = (double)n;
            // Spread per tick
            double sum_spread = 0;
            for(int i = 0; i < n; i++)
            {
                double sp = (ticks[i].ask - ticks[i].bid) / pip;
                sum_spread += sp;
                if(sp > spread_max) spread_max = sp;
            }
            spread_avg = sum_spread / n;

            // Time intervals between ticks
            double deltas[];
            ArrayResize(deltas, n - 1);
            for(int i = 1; i < n; i++)
                deltas[i-1] = (double)(ticks[i].time_msc - ticks[i-1].time_msc);
            // median via sort
            double sorted_d[];
            ArrayCopy(sorted_d, deltas);
            ArraySort(sorted_d);
            median_tick_interval_ms = sorted_d[(n-1)/2];
            max_tick_interval_ms    = sorted_d[n-2];

            // Aggressor: bid moved up = buy pressure; ask moved down = sell pressure
            int bid_up_cnt = 0, ask_dn_cnt = 0;
            for(int i = 1; i < n; i++)
            {
                if(ticks[i].bid > ticks[i-1].bid) bid_up_cnt++;
                if(ticks[i].ask < ticks[i-1].ask) ask_dn_cnt++;
            }
            bid_aggressor_pct = 100.0 * bid_up_cnt / n;
            ask_aggressor_pct = 100.0 * ask_dn_cnt / n;
            imbalance = bid_aggressor_pct - ask_aggressor_pct;

            // Half-split velocity (abs mid change per tick)
            int half = n / 2;
            double vel1 = 0, vel2 = 0;
            for(int i = 1; i < n; i++)
            {
                double mc = MathAbs((ticks[i].bid+ticks[i].ask)/2.0
                                   -(ticks[i-1].bid+ticks[i-1].ask)/2.0) / pip;
                if(i <= half) vel1 += mc;
                else          vel2 += mc;
            }
            tick_velocity_first_half  = vel1 / half;
            tick_velocity_second_half = (n - half > 0) ? vel2 / (n - half) : 0;
            vel_ratio_2nd_to_1st = (vel1 > 0) ? tick_velocity_second_half / tick_velocity_first_half : 0;

            // Max run-up / run-dn from first tick mid
            double first_mid = (ticks[0].bid + ticks[0].ask) / 2.0;
            double cummax = first_mid, cummin = first_mid;
            // near high/low tracking
            double bar_hi_t = first_mid, bar_lo_t = first_mid;
            for(int i = 0; i < n; i++)
            {
                double mid = (ticks[i].bid + ticks[i].ask) / 2.0;
                if(mid > bar_hi_t) bar_hi_t = mid;
                if(mid < bar_lo_t) bar_lo_t = mid;
                if(mid > cummax) cummax = mid;
                if(mid < cummin) cummin = mid;
            }
            max_run_up_pips = (cummax - first_mid) / pip;
            max_run_dn_pips = (first_mid - cummin) / pip;

            // Ticks at high / low (within 1 pip)
            int near_h = 0, near_l = 0;
            for(int i = 0; i < n; i++)
            {
                double mid = (ticks[i].bid + ticks[i].ask) / 2.0;
                if((bar_hi_t - mid) / pip <= 1.0) near_h++;
                if((mid - bar_lo_t) / pip <= 1.0) near_l++;
            }
            ticks_at_high_pct = 100.0 * near_h / n;
            ticks_at_low_pct  = 100.0 * near_l / n;
        }
        else
        {
            // Fallback: iTickVolume and OHLC-derived approximations
            tick_count = (double)iTickVolume(_Symbol, PERIOD_M5, s);
            spread_avg = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) * _Point / pip;
            max_run_up_pips = (hi - opn) / pip;
            max_run_dn_pips = (opn - lo) / pip;
        }
    }

    // ── M5 rolling-window features (match 35_build_full_panel.py) ───────────

    // ATR ratio and percentile rank — at pivot bar shift s
    double atr5_v   = GetIndicator(g_h_atr5,  0, s) / pip;
    double atr14_v  = GetIndicator(g_h_atr14, 0, s) / pip;
    double atr50_v  = GetIndicator(g_h_atr50, 0, s) / pip;
    double atr_ratio_5_50 = (atr50_v > 0) ? atr5_v / atr50_v : 1.0;

    double atr14_hist[100];
    CopyBuffer(g_h_atr14, 0, s, 100, atr14_hist);
    for(int i = 0; i < 100; i++) atr14_hist[i] /= pip;
    double atr_pct100 = PctRank(atr14_v, atr14_hist, 100);

    // BB at pivot bar
    double bb_up  = GetIndicator(g_h_bb, 1, s);
    double bb_lo  = GetIndicator(g_h_bb, 2, s);
    double bb_pctB_v     = (bb_up != bb_lo) ? (cls - bb_lo) / (bb_up - bb_lo) : 0.5;
    double bb_width_pips = (bb_up - bb_lo) / pip;

    // BB squeeze = current width / rolling-50 mean width
    double bb_up50[50], bb_lo50[50];
    CopyBuffer(g_h_bb, 1, s, 50, bb_up50);
    CopyBuffer(g_h_bb, 2, s, 50, bb_lo50);
    double widths50[50];
    for(int i = 0; i < 50; i++) widths50[i] = (bb_up50[i] - bb_lo50[i]) / pip;
    double mean_w = RolMean(widths50, 50);
    double bb_squeeze = (mean_w > 0) ? bb_width_pips / mean_w : 1.0;

    // Realized vol 20 starting at pivot bar
    double close21[21]; CopyClose(_Symbol, PERIOD_M5, s, 21, close21);
    double pct_ch[20];
    for(int i = 0; i < 20; i++)
        pct_ch[i] = (close21[i+1] > 0) ? (close21[i] - close21[i+1]) / close21[i+1] : 0;
    double m_pc = RolMean(pct_ch, 20);
    double realized_vol_20 = RolStd(pct_ch, 20, m_pc) * 1e4;

    // range_z20 at pivot bar
    double hi20[20], lo20[20];
    CopyHigh(_Symbol, PERIOD_M5, s, 20, hi20);
    CopyLow (_Symbol, PERIOD_M5, s, 20, lo20);
    double ranges20[20];
    for(int i = 0; i < 20; i++) ranges20[i] = (hi20[i] - lo20[i]) / pip;
    double rm = RolMean(ranges20, 20), rs = RolStd(ranges20, 20, rm);
    double range_z20 = (rs > 0) ? ((rng/pip) - rm) / rs : 0.0;

    // vol_z20 = iTickVolume z-score at pivot bar
    long vol20_raw[20]; CopyTickVolume(_Symbol, PERIOD_M5, s, 20, vol20_raw);
    double vol20[20]; for(int i=0;i<20;i++) vol20[i]=(double)vol20_raw[i];
    double vm = RolMean(vol20, 20), vs = RolStdPop(vol20, 20, vm);
    double vol_z20 = (vs > 0) ? (vol20[0] - vm) / vs : 0.0;

    // vol_of_vol_20 = rolling std of ATR14 over 20 bars at pivot bar
    double atr14_20[20]; CopyBuffer(g_h_atr14, 0, s, 20, atr14_20);
    for(int i=0;i<20;i++) atr14_20[i]/=pip;
    double am = RolMean(atr14_20, 20);
    double vol_of_vol_20 = RolStd(atr14_20, 20, am);

    // consec_up / consec_dn at pivot bar
    double op10[10], cl10[10];
    CopyOpen (_Symbol, PERIOD_M5, s, 10, op10);
    CopyClose(_Symbol, PERIOD_M5, s, 10, cl10);
    int consec_up = 0, consec_dn = 0;
    for(int i = 0; i < 10; i++) { if(cl10[i]>op10[i]) consec_up++; else break; }
    for(int i = 0; i < 10; i++) { if(cl10[i]<op10[i]) consec_dn++; else break; }

    // velocity_3 = close[s] - close[s+3]  (price units)
    double velocity_3      = iClose(_Symbol, PERIOD_M5, s)   - iClose(_Symbol, PERIOD_M5, s+3);
    double velocity_3_prev = iClose(_Symbol, PERIOD_M5, s+1) - iClose(_Symbol, PERIOD_M5, s+4);
    double accel = velocity_3 - velocity_3_prev;

    // EMAs at pivot bar
    double ema20  = GetIndicator(g_h_ema20,  0, s);
    double ema50  = GetIndicator(g_h_ema50,  0, s);
    double ema200 = GetIndicator(g_h_ema200, 0, s);
    double dist_ema20_atr = (atr14_v > 0) ? (cls - ema20) / (atr14_v * pip) : 0;
    double dist_ema50_atr = (atr14_v > 0) ? (cls - ema50) / (atr14_v * pip) : 0;

    // Distance to recent extremes — anchored at pivot bar
    double h5  = iHigh(_Symbol, PERIOD_M5, iHighest(_Symbol, PERIOD_M5, MODE_HIGH, 5,  s));
    double l5  = iLow (_Symbol, PERIOD_M5, iLowest (_Symbol, PERIOD_M5, MODE_LOW,  5,  s));
    double h20 = iHigh(_Symbol, PERIOD_M5, iHighest(_Symbol, PERIOD_M5, MODE_HIGH, 20, s));
    double l20 = iLow (_Symbol, PERIOD_M5, iLowest (_Symbol, PERIOD_M5, MODE_LOW,  20, s));
    double h50 = iHigh(_Symbol, PERIOD_M5, iHighest(_Symbol, PERIOD_M5, MODE_HIGH, 50, s));
    double l50 = iLow (_Symbol, PERIOD_M5, iLowest (_Symbol, PERIOD_M5, MODE_LOW,  50, s));
    // today_h/l: use D1 bar that covers the pivot bar
    int d1_shift = iBarShift(_Symbol, PERIOD_D1, bar1_broker);
    double today_h = iHigh(_Symbol, PERIOD_D1, d1_shift);
    double today_l = iLow (_Symbol, PERIOD_D1, d1_shift);

    // ── H1 features — use H1 bar that contains the pivot bar ─────────────────
    int h1_shift = iBarShift(_Symbol, PERIOD_H1, bar1_broker);
    if(h1_shift < 1) h1_shift = 1;
    double h1_close = iClose(_Symbol, PERIOD_H1, h1_shift);
    double h1_ema50      = GetIndicator(g_h_h1_ema50,  0, h1_shift);
    double h1_ema200     = GetIndicator(g_h_h1_ema200, 0, h1_shift);
    double h1_ema50_24h  = GetIndicator(g_h_h1_ema50,  0, h1_shift + 24);
    double h1_ema200_24h = GetIndicator(g_h_h1_ema200, 0, h1_shift + 24);
    bool up50  = (h1_ema50  - h1_ema50_24h)  > 0;
    bool up200 = (h1_ema200 - h1_ema200_24h) > 0;
    int h1_trend_dir = (up50 && up200) ? 1 : ((!up50 && !up200) ? -1 : 0);

    // H1 BB %B
    double h1_bb_up = GetIndicator(g_h_h1_bb, 1, h1_shift);
    double h1_bb_lo = GetIndicator(g_h_h1_bb, 2, h1_shift);
    double h1_bb_pctB = (h1_bb_up != h1_bb_lo) ? (h1_close - h1_bb_lo) / (h1_bb_up - h1_bb_lo) : 0.5;

    // H1 24h high/low
    int h1_24h_hi_idx = iHighest(_Symbol, PERIOD_H1, MODE_HIGH, 24, h1_shift);
    int h1_24h_lo_idx = iLowest (_Symbol, PERIOD_H1, MODE_LOW,  24, h1_shift);
    double h1_dist_24h_high_pips = (iHigh(_Symbol, PERIOD_H1, h1_24h_hi_idx) - h1_close) / pip;
    double h1_dist_24h_low_pips  = (h1_close - iLow(_Symbol, PERIOD_H1, h1_24h_lo_idx)) / pip;

    // ── Assemble JSON (order matches research feature_lists) ─────────────────
    // Tick features
    json += StringFormat("\"tick_count\":%.1f,",               tick_count);
    json += StringFormat("\"median_tick_interval_ms\":%.2f,",  median_tick_interval_ms);
    json += StringFormat("\"max_tick_interval_ms\":%.2f,",     max_tick_interval_ms);
    json += StringFormat("\"spread_avg\":%.4f,",               spread_avg);
    json += StringFormat("\"spread_max\":%.4f,",               spread_max);
    json += StringFormat("\"bid_aggressor_pct\":%.4f,",        bid_aggressor_pct);
    json += StringFormat("\"ask_aggressor_pct\":%.4f,",        ask_aggressor_pct);
    json += StringFormat("\"imbalance\":%.4f,",                imbalance);
    json += StringFormat("\"tick_velocity_first_half\":%.6f,", tick_velocity_first_half);
    json += StringFormat("\"tick_velocity_second_half\":%.6f,",tick_velocity_second_half);
    json += StringFormat("\"vel_ratio_2nd_to_1st\":%.4f,",     vel_ratio_2nd_to_1st);
    json += StringFormat("\"max_run_up_pips_intrabar\":%.4f,", max_run_up_pips);
    json += StringFormat("\"max_run_dn_pips_intrabar\":%.4f,", max_run_dn_pips);
    json += StringFormat("\"ticks_at_high_pct\":%.4f,",        ticks_at_high_pct);
    json += StringFormat("\"ticks_at_low_pct\":%.4f,",         ticks_at_low_pct);
    // Indicators
    json += StringFormat("\"rsi14\":%.4f,",          GetIndicator(g_h_rsi14, 0, 1));
    json += StringFormat("\"stoch_k\":%.4f,",        GetIndicator(g_h_stoch, 0, 1));
    json += StringFormat("\"stoch_d\":%.4f,",        GetIndicator(g_h_stoch, 1, 1));
    json += StringFormat("\"macd\":%.6f,",           GetIndicator(g_h_macd,  0, 1));
    json += StringFormat("\"macd_sig\":%.6f,",       GetIndicator(g_h_macd,  1, 1));
    json += StringFormat("\"macd_hist\":%.6f,",      GetIndicator(g_h_macd,  0, 1) - GetIndicator(g_h_macd, 1, 1));
    json += StringFormat("\"atr5\":%.4f,",           atr5_v);
    json += StringFormat("\"atr14_pips\":%.4f,",     atr14_v);
    json += StringFormat("\"atr50\":%.4f,",          atr50_v);
    json += StringFormat("\"atr_ratio_5_50\":%.4f,", atr_ratio_5_50);
    json += StringFormat("\"atr_pct100\":%.4f,",     atr_pct100);
    json += StringFormat("\"bb_pctB\":%.4f,",        bb_pctB_v);
    json += StringFormat("\"bb_width_pips\":%.4f,",  bb_width_pips);
    json += StringFormat("\"bb_squeeze\":%.4f,",     bb_squeeze);
    json += StringFormat("\"realized_vol_20\":%.4f,",realized_vol_20);
    json += StringFormat("\"range_pips\":%.4f,",     rng / pip);
    json += StringFormat("\"body_pips\":%.4f,",      body / pip);
    json += StringFormat("\"range_z20\":%.4f,",      range_z20);
    json += StringFormat("\"body_to_range\":%.4f,",  rng > 0 ? body / rng : 0);
    json += StringFormat("\"upper_wick_ratio\":%.4f,",(rng>0)?(hi-MathMax(opn,cls))/rng:0);
    json += StringFormat("\"lower_wick_ratio\":%.4f,",(rng>0)?(MathMin(opn,cls)-lo)/rng:0);
    json += StringFormat("\"vol_z20\":%.4f,",        vol_z20);
    json += StringFormat("\"vol_of_vol_20\":%.4f,",  vol_of_vol_20);
    json += StringFormat("\"consec_up\":%d,",        consec_up);
    json += StringFormat("\"consec_dn\":%d,",        consec_dn);
    json += StringFormat("\"velocity_3\":%.6f,",     velocity_3);
    json += StringFormat("\"accel\":%.6f,",          accel);
    json += StringFormat("\"dist_ema20_atr\":%.4f,", dist_ema20_atr);
    json += StringFormat("\"dist_ema50_atr\":%.4f,", dist_ema50_atr);
    json += StringFormat("\"williams_r14\":%.4f,",   GetIndicator(g_h_wpr14,  0, 1));
    json += StringFormat("\"adx14\":%.4f,",          GetIndicator(g_h_adx14,  0, 1));
    json += StringFormat("\"plus_di\":%.4f,",        GetIndicator(g_h_adx14,  1, 1));
    json += StringFormat("\"minus_di\":%.4f,",       GetIndicator(g_h_adx14,  2, 1));
    json += StringFormat("\"dist_to_5bar_high_pips\":%.4f,",  (h5  - cls) / pip);
    json += StringFormat("\"dist_to_5bar_low_pips\":%.4f,",   (cls - l5 ) / pip);
    json += StringFormat("\"dist_to_20bar_high_pips\":%.4f,", (h20 - cls) / pip);
    json += StringFormat("\"dist_to_20bar_low_pips\":%.4f,",  (cls - l20) / pip);
    json += StringFormat("\"dist_to_50bar_high_pips\":%.4f,", (h50 - cls) / pip);
    json += StringFormat("\"dist_to_50bar_low_pips\":%.4f,",  (cls - l50) / pip);
    json += StringFormat("\"dist_to_today_high_pips\":%.4f,", (today_h - cls) / pip);
    json += StringFormat("\"dist_to_today_low_pips\":%.4f,",  (cls - today_l) / pip);
    json += StringFormat("\"hour_utc\":%d,", hour_utc);
    json += StringFormat("\"dow\":%d,",      dow);
    // H1
    json += StringFormat("\"h1_rsi14\":%.4f,",             GetIndicator(g_h_h1_rsi14, 0, 1));
    json += StringFormat("\"h1_atr14_pips\":%.4f,",        GetIndicator(g_h_h1_atr14, 0, 1) / pip);
    json += StringFormat("\"h1_ema50_slope_pips\":%.4f,",  (h1_ema50  - h1_ema50_24h)  / pip);
    json += StringFormat("\"h1_ema200_slope_pips\":%.4f,", (h1_ema200 - h1_ema200_24h) / pip);
    json += StringFormat("\"h1_dist_ema50_pips\":%.4f,",   (h1_close - h1_ema50)  / pip);
    json += StringFormat("\"h1_dist_ema200_pips\":%.4f,",  (h1_close - h1_ema200) / pip);
    json += StringFormat("\"h1_above_ema50\":%d,",         (h1_close > h1_ema50)  ? 1 : 0);
    json += StringFormat("\"h1_above_ema200\":%d,",        (h1_close > h1_ema200) ? 1 : 0);
    json += StringFormat("\"h1_bb_pctB\":%.4f,",           h1_bb_pctB);
    json += StringFormat("\"h1_trend_dir\":%d,",           h1_trend_dir);
    json += StringFormat("\"h1_dist_24h_high_pips\":%.4f,",h1_dist_24h_high_pips);
    json += StringFormat("\"h1_dist_24h_low_pips\":%.4f",  h1_dist_24h_low_pips);

    json += "}";
    return json;
}

//══════════════════════════════════════════════════════════════════
// BRIDGE WATCHDOG  (heartbeat read + auto-launch + single-EA lock)
//══════════════════════════════════════════════════════════════════
// Read the heartbeat file written by VECTOR003_BRIDGE.py.
// File contents look like: {"pid": 1234, "ts": 1717485660.123}
// Returns true if a fresh timestamp was parsed; updates g_last_heartbeat_ts.
bool ReadBridgeHeartbeat()
{
    if(!FileIsExist("vector003_bridge.heartbeat", FILE_COMMON))
        return false;
    int h = FileOpen("vector003_bridge.heartbeat",
        FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
    if(h == INVALID_HANDLE) return false;
    string body = "";
    while(!FileIsEnding(h)) body += FileReadString(h);
    FileClose(h);
    int p = StringFind(body, "\"ts\":");
    if(p < 0) return false;
    int s = p + 5;
    int e = s;
    while(e < StringLen(body))
    {
        ushort c = StringGetCharacter(body, e);
        if(c == ',' || c == '}') break;
        e++;
    }
    string num = StringSubstr(body, s, e - s);
    StringTrimLeft(num); StringTrimRight(num);
    double ts = StringToDouble(num);
    if(ts <= 0) return false;
    g_last_heartbeat_ts = ts;
    return true;
}

bool BridgeIsAlive(int max_age_sec)
{
    if(!ReadBridgeHeartbeat()) return false;
    // Bridge writes Python time.time() = UTC epoch.  Compare against TimeGMT().
    double age = (double)TimeGMT() - g_last_heartbeat_ts;
    return (age >= -3.0 && age <= (double)max_age_sec);
}

// Launch start_bridge.bat from this terminal's MQL5\Files folder via ShellExecuteW.
// The bridge itself enforces single-instance; this call is harmless if one is already up.
void LaunchBridge()
{
    string data_path = TerminalInfoString(TERMINAL_DATA_PATH);
    string bat_path  = data_path + "\\MQL5\\Files\\start_bridge.bat";
    int rc = ShellExecuteW(0, "open", bat_path, "", "", 0);
    if(rc <= 32)
        PrintFormat("V3 BRIDGE: ShellExecuteW failed rc=%d path=%s", rc, bat_path);
    else
        PrintFormat("V3 BRIDGE: launch requested via %s", bat_path);
}

// EA lock — refuse to run two EA instances against the same bridge.
// Lock file in Common\Files is shared across terminals. Identity = terminal path + chart id + symbol + tf.
string BuildIdentity()
{
    long chart = ChartID();
    return StringFormat("%s|chart=%I64d|sym=%s|tf=%d",
        TerminalInfoString(TERMINAL_DATA_PATH),
        chart, _Symbol, (int)PERIOD_M5);
}

bool ReadEALock(string &out_ident, double &out_ts)
{
    out_ident = ""; out_ts = 0;
    if(!FileIsExist("vector003_ea.lock", FILE_COMMON)) return false;
    int h = FileOpen("vector003_ea.lock",
        FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
    if(h == INVALID_HANDLE) return false;
    string l1 = FileReadString(h);   // timestamp
    string l2 = "";
    while(!FileIsEnding(h)) l2 += FileReadString(h);
    FileClose(h);
    StringTrimLeft(l1); StringTrimRight(l1);
    StringTrimLeft(l2); StringTrimRight(l2);
    out_ts = StringToDouble(l1);
    out_ident = l2;
    return true;
}

void WriteEALock()
{
    int h = FileOpen("vector003_ea.lock",
        FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
    if(h == INVALID_HANDLE)
    {
        PrintFormat("V3 LOCK: cannot write lock (err=%d)", GetLastError());
        return;
    }
    FileWriteString(h, StringFormat("%I64d\r\n%s", (long)TimeCurrent(), g_ea_identity));
    FileClose(h);
}

void DeleteEALock()
{
    string ident; double ts;
    if(ReadEALock(ident, ts) && ident == g_ea_identity)
        FileDelete("vector003_ea.lock", FILE_COMMON);
}

// Returns true if it is OK for this EA to run.  Refuses if another EA's lock
// is fresh and from a different identity.
bool ClaimEALock()
{
    g_ea_identity = BuildIdentity();
    string other_ident; double other_ts;
    if(ReadEALock(other_ident, other_ts))
    {
        double age = (double)TimeCurrent() - other_ts;
        if(age < 30.0 && other_ident != g_ea_identity)
        {
            PrintFormat("V3 LOCK: another EA is active (age=%.0fs).  Refusing to start.", age);
            PrintFormat("V3 LOCK: holder = %s", other_ident);
            return false;
        }
    }
    WriteEALock();
    g_last_ea_lock_ts = TimeCurrent();
    return true;
}

// Refresh own lock every 5s while running.
void RefreshEALock()
{
    if(TimeCurrent() - g_last_ea_lock_ts < 5) return;
    WriteEALock();
    g_last_ea_lock_ts = TimeCurrent();
}

// Wait up to max_sec for heartbeat to appear (used right after launching the bridge).
bool WaitForBridge(int max_sec)
{
    uint t0 = GetTickCount();
    while(GetTickCount() - t0 < (uint)max_sec * 1000)
    {
        if(BridgeIsAlive(InpBridgeStaleSec))
            return true;
        Sleep(500);
    }
    return false;
}

//══════════════════════════════════════════════════════════════════
// BRIDGE COMMUNICATION
//══════════════════════════════════════════════════════════════════
bool QueryBridge(string features_json, string &out_response)
{
    g_request_id++;
    string req = "{";
    req += StringFormat("\"request_id\":\"%d\",", g_request_id);
    req += StringFormat("\"bar_time_unix\":%I64u,", (ulong)iTime(_Symbol, PERIOD_M5, 1));
    req += StringFormat("\"threshold\":%.3f,", InpThreshold);
    req += StringFormat("\"cooldown_min\":%d,", InpCooldownMin);
    // Last signal times for cooldown
    if(g_last_sell_signal > 0)
        req += StringFormat("\"last_sell_signal_unix\":%I64u,", (ulong)g_last_sell_signal);
    if(g_last_buy_signal > 0)
        req += StringFormat("\"last_buy_signal_unix\":%I64u,", (ulong)g_last_buy_signal);
    // Inject features
    req += "\"features\":" + features_json;
    req += "}";

    // Write request
    int h = FileOpen("vector003_request.json",
        FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
    if(h == INVALID_HANDLE)
    {
        PrintFormat("V3 BRIDGE: cannot open request file (err=%d)", GetLastError());
        return false;
    }
    FileWriteString(h, req);
    FileClose(h);

    // Wait for response
    // In tester mode use a short timeout — Sleep() in tester consumes real wall time
    // and triggers MT5's "infinite Sleep loop" watchdog if accumulated over many bars.
    bool is_tester = (bool)MQLInfoInteger(MQL_TESTER);
    uint timeout_ms = is_tester ? 500 : (uint)InpBridgeTimeoutMs;
    uint poll_ms    = is_tester ?  10 : 20;

    uint t0 = GetTickCount();
    while(GetTickCount() - t0 < timeout_ms)
    {
        if(FileIsExist("vector003_response.json", FILE_COMMON))
        {
            int rh = FileOpen("vector003_response.json",
                FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
            if(rh != INVALID_HANDLE)
            {
                out_response = "";
                while(!FileIsEnding(rh))
                    out_response += FileReadString(rh);
                FileClose(rh);
                FileDelete("vector003_response.json", FILE_COMMON);
                // Bridge may still be writing (atomic rename didn't arrive yet):
                // if the file was empty, wait briefly and retry once.
                if(StringLen(out_response) == 0)
                {
                    Sleep(30);
                    if(FileIsExist("vector003_response.json", FILE_COMMON))
                    {
                        int rh2 = FileOpen("vector003_response.json",
                            FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ | FILE_SHARE_WRITE);
                        if(rh2 != INVALID_HANDLE)
                        {
                            while(!FileIsEnding(rh2)) out_response += FileReadString(rh2);
                            FileClose(rh2);
                            FileDelete("vector003_response.json", FILE_COMMON);
                        }
                    }
                }
                if(StringLen(out_response) == 0) { Sleep(poll_ms); continue; }
                return true;
            }
        }
        Sleep(poll_ms);
    }
    PrintFormat("V3 BRIDGE: timeout after %d ms", timeout_ms);
    return false;
}

// Parse minimal fields from JSON response
bool ParseResponse(string json, bool &fire, string &side, double &prob, string &cls)
{
    fire = false;
    int p_fire = StringFind(json, "\"fire\":");
    if(p_fire < 0) return false;
    string snippet = StringSubstr(json, p_fire + 7, 10);
    fire = (StringFind(snippet, "true") >= 0);

    // Python's json.dump writes spaces after colons: "side": "BUY"
    // Find key, then scan to the first quote after the colon.
    int p_side = StringFind(json, "\"side\":");
    if(p_side >= 0)
    {
        int q = StringFind(json, "\"", p_side + 7);   // opening quote of value
        if(q >= 0) { q++; int e = StringFind(json, "\"", q); if(e > q) side = StringSubstr(json, q, e - q); }
    }

    int p_prob = StringFind(json, "\"best_prob\":");
    if(p_prob >= 0)
    {
        int s = p_prob + 12;
        // skip whitespace
        while(s < StringLen(json) && StringGetCharacter(json, s) == ' ') s++;
        int e = s;
        while(e < StringLen(json))
        {
            ushort c = StringGetCharacter(json, e);
            if(c == ',' || c == '}') break;
            e++;
        }
        prob = StringToDouble(StringSubstr(json, s, e - s));
    }

    int p_cls = StringFind(json, "\"best_class\":");
    if(p_cls >= 0)
    {
        int q = StringFind(json, "\"", p_cls + 13);   // opening quote of value
        if(q >= 0) { q++; int e = StringFind(json, "\"", q); if(e > q) cls = StringSubstr(json, q, e - q); }
    }

    return true;
}

//══════════════════════════════════════════════════════════════════
// TRADE EXECUTION
//══════════════════════════════════════════════════════════════════
void OpenPosition(string side, double prob, string best_class)
{
    if(CountOpen() >= InpMaxOpenTrades)
    {
        Print("V3 OpenPosition: max trades reached"); return;
    }
    bool is_buy = (side == "BUY");
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double entry = is_buy ? ask : bid;
    double sl = is_buy ? entry - InpSLPips * g_pip
                        : entry + InpSLPips * g_pip;
    sl = Normalize(sl);

    double lots = CalcLots(InpSLPips);
    if(lots <= 0) { Print("V3 OpenPosition: lots calc failed"); return; }

    MqlTradeRequest req; MqlTradeResult res;
    ZeroMemory(req); ZeroMemory(res);
    req.action    = TRADE_ACTION_DEAL;
    req.symbol    = _Symbol;
    req.volume    = lots;
    req.type      = is_buy ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
    req.price     = Normalize(entry);
    req.sl        = sl;
    req.tp        = 0;
    req.magic     = InpMagic;
    req.deviation = 10;
    req.comment   = StringFormat("V3|%s|p=%.2f", best_class, prob);

    if(!OrderSend(req, res) || res.retcode != TRADE_RETCODE_DONE)
    {
        PrintFormat("V3 OrderSend failed ret=%d", res.retcode);
        return;
    }

    // Track
    int idx = -1;
    for(int i = 0; i < MAX_POSITIONS; i++)
        if(!g_positions[i].active) { idx = i; break; }
    if(idx < 0)
    {
        Print("V3 OpenPosition: no free slot");
        return;
    }
    SPosition p;
    ZeroMemory(p);
    p.active            = true;
    p.ticket            = res.order;
    p.entry_time        = TimeCurrent();
    p.entry_price       = res.price > 0 ? res.price : entry;
    p.current_sl        = sl;
    p.is_buy            = is_buy;
    p.max_favorable_pips = 0;
    p.lots              = lots;
    p.best_class        = best_class;
    p.prob              = prob;
    g_positions[idx]    = p;

    if(is_buy) g_last_buy_signal = TimeCurrent();
    else       g_last_sell_signal = TimeCurrent();
    g_signals_fired++;

    PrintFormat("V3 ENTRY %s ticket=%I64u entry=%.5f sl=%.5f lots=%.2f class=%s p=%.2f",
        side, p.ticket, p.entry_price, sl, lots, best_class, prob);

    if(InpDrawArrows)
    {
        string name = StringFormat("V3_arr_%d", g_signals_fired);
        double pip2 = 2.0 * g_pip;
        double y    = is_buy ? entry - pip2 : entry + pip2;
        int    code = is_buy ? 233 : 234;
        color  clr  = is_buy ? clrDodgerBlue : clrRed;
        if(ObjectCreate(0, name, OBJ_ARROW, 0, TimeCurrent(), y))
        {
            ObjectSetInteger(0, name, OBJPROP_ARROWCODE, code);
            ObjectSetInteger(0, name, OBJPROP_COLOR, clr);
            ObjectSetInteger(0, name, OBJPROP_WIDTH, 3);
        }
    }
}

void ManagePositions()
{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    datetime now = TimeCurrent();
    for(int i = 0; i < MAX_POSITIONS; i++)
    {
        if(!g_positions[i].active) continue;
        if(!PositionSelectByTicket(g_positions[i].ticket))
        {
            // Closed externally
            g_positions[i].active = false; continue;
        }
        // Timeout
        int held_min = (int)((now - g_positions[i].entry_time) / 60);
        if(held_min >= InpTimeoutMin)
        {
            // Close at market
            bool is_buy = g_positions[i].is_buy;
            double price = is_buy ? bid : ask;
            MqlTradeRequest rq; MqlTradeResult rs;
            ZeroMemory(rq); ZeroMemory(rs);
            rq.action    = TRADE_ACTION_DEAL;
            rq.position  = g_positions[i].ticket;
            rq.symbol    = _Symbol;
            rq.volume    = g_positions[i].lots;
            rq.type      = is_buy ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            rq.price     = price;
            rq.deviation = 10;
            rq.magic     = InpMagic;
            rq.comment   = "V3 timeout";
            if(!OrderSend(rq, rs))
                PrintFormat("V3 timeout close failed ticket=%I64u ret=%d",
                            g_positions[i].ticket, rs.retcode);
            else
                PrintFormat("V3 timeout closed ticket=%I64u price=%.5f",
                            g_positions[i].ticket, price);
            g_positions[i].active = false;
            continue;
        }
        // Trail
        bool is_buy = g_positions[i].is_buy;
        double cur = is_buy ? bid : ask;
        double entry = g_positions[i].entry_price;
        double fav_pips = is_buy ? (cur - entry) / g_pip : (entry - cur) / g_pip;
        if(fav_pips > g_positions[i].max_favorable_pips)
            g_positions[i].max_favorable_pips = fav_pips;
        // Trail from first favorable pip — no activation gate (v2.31)
        // Research sim trails immediately: peak tracks max favorable price,
        // new_sl = peak - trail. The 0.5p hysteresis prevents micro-moves.
        if(g_positions[i].max_favorable_pips > 0)
        {
            double peak = is_buy
                ? entry + g_positions[i].max_favorable_pips * g_pip
                : entry - g_positions[i].max_favorable_pips * g_pip;
            double new_sl = is_buy ? peak - InpTrailPips * g_pip
                                    : peak + InpTrailPips * g_pip;
            new_sl = Normalize(new_sl);
            bool better = is_buy ? new_sl > g_positions[i].current_sl + g_pip * 0.5
                                  : new_sl < g_positions[i].current_sl - g_pip * 0.5;
            if(better)
            {
                MqlTradeRequest mq; MqlTradeResult ms;
                ZeroMemory(mq); ZeroMemory(ms);
                mq.action   = TRADE_ACTION_SLTP;
                mq.position = g_positions[i].ticket;
                mq.symbol   = _Symbol;
                mq.sl       = new_sl;
                mq.tp       = 0;
                if(OrderSend(mq, ms))
                    g_positions[i].current_sl = new_sl;
            }
        }
    }
}

//══════════════════════════════════════════════════════════════════
// SIGNAL FLOW (on new M5 bar)
//══════════════════════════════════════════════════════════════════
void CheckSignal()
{
    if(g_bridge_down)
    {
        Print("V3 CheckSignal: bridge DOWN — skipping");
        return;
    }

    // Build all 70 features at bar[1] (last closed bar = candidate bar)
    // Gate 1 removed in v2.20: bridge Stage-1 OR-ensemble gates the training universe.
    string features_json = BuildFeaturesJSON(1);
    string response = "";
    if(!QueryBridge(features_json, response))
        return;

    bool fire = false; string side = ""; double prob = 0; string cls = "";
    if(!ParseResponse(response, fire, side, prob, cls))
    {
        Print("V3: parse response failed");
        return;
    }
    if(!fire) return;

    // Local-N extreme gate (v2.30): only trade when bar[1] is the local extreme
    // Research validated: BUY if bar[1].low=min of last N lows; SELL if bar[1].high=max of last N highs
    bool is_buy = (side == "BUY");
    if(InpLocalN > 1)
    {
        if(is_buy)
        {
            int lowest = iLowest(NULL, PERIOD_CURRENT, MODE_LOW, InpLocalN, 1);
            if(lowest != 1)
            {
                PrintFormat("V3: local-N blocks BUY — bar[1] not lowest low of last %d (bar[%d] is)", InpLocalN, lowest);
                return;
            }
        }
        else
        {
            int highest = iHighest(NULL, PERIOD_CURRENT, MODE_HIGH, InpLocalN, 1);
            if(highest != 1)
            {
                PrintFormat("V3: local-N blocks SELL — bar[1] not highest high of last %d (bar[%d] is)", InpLocalN, highest);
                return;
            }
        }
    }

    // EA-side cooldown (defense in depth — bridge also checks)
    datetime last = is_buy ? g_last_buy_signal : g_last_sell_signal;
    if(last > 0 && (TimeCurrent() - last) < InpCooldownMin * 60)
    {
        PrintFormat("V3: cooldown blocks %s signal", side);
        return;
    }
    OpenPosition(side, prob, cls);
}

//══════════════════════════════════════════════════════════════════
// UpdatePanel
//══════════════════════════════════════════════════════════════════
void UpdatePanel()
{
    if(!InpShowPanel) return;
    string name = "V3_panel";
    string bridge_state;
    color  bridge_clr;
    if(g_bridge_down)
    {
        bridge_state = "BRIDGE DOWN — trading paused";
        bridge_clr   = clrTomato;
    }
    else
    {
        double age = (double)TimeGMT() - g_last_heartbeat_ts;
        bridge_state = StringFormat("bridge OK  hb_age=%.1fs", age);
        bridge_clr   = clrLimeGreen;
    }
    string txt = StringFormat(
        "VECTOR003  thr=%.2f  cd=%d  localN=%d  SL=%.0f trail=%.0f\n"
        "  %s\n"
        "  signals fired: %d  open positions: %d",
        InpThreshold, InpCooldownMin, InpLocalN, InpSLPips, InpTrailPips,
        bridge_state,
        g_signals_fired, CountOpen());
    if(ObjectFind(0, name) < 0)
    {
        ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
        ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
        ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
        ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 24);
        ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
    }
    ObjectSetInteger(0, name, OBJPROP_COLOR, bridge_clr);
    ObjectSetString(0, name, OBJPROP_TEXT, txt);
}

//══════════════════════════════════════════════════════════════════
// OnInit / OnTick / OnDeinit
//══════════════════════════════════════════════════════════════════
int OnInit()
{
    g_pip = Pip();
    ZeroMemory(g_positions);
    g_last_m5_bar = 0;
    g_last_sell_signal = 0;
    g_last_buy_signal  = 0;
    g_signals_fired    = 0;
    g_bridge_down      = true;
    g_last_heartbeat_ts = 0;
    g_last_hb_check     = 0;

    // Purge any stale response file from a previous run so the first bar
    // doesn't pick up a leftover and misparse it.
    if(FileIsExist("vector003_response.json", FILE_COMMON))
        FileDelete("vector003_response.json", FILE_COMMON);

    // ── Single-EA enforcement ────────────────────────────────────
    if(!(bool)MQLInfoInteger(MQL_TESTER))
    {
        if(!ClaimEALock())
            return INIT_FAILED;
    }

    // ── Bridge watchdog: check heartbeat, launch if needed ───────
    if(!(bool)MQLInfoInteger(MQL_TESTER))
    {
        if(BridgeIsAlive(InpBridgeStaleSec))
        {
            g_bridge_down = false;
            Print("V3 BRIDGE: heartbeat OK on init");
        }
        else if(InpAutoStartBridge)
        {
            Print("V3 BRIDGE: no live heartbeat — launching start_bridge.bat");
            if(!(bool)MQLInfoInteger(MQL_DLLS_ALLOWED))
            {
                Print("V3 BRIDGE: DLL imports NOT allowed.  Enable in EA Common tab + Tools→Options→EAs.");
                Print("V3 BRIDGE: continuing in DOWN state — trading will be paused.");
            }
            else
            {
                LaunchBridge();
                if(WaitForBridge(InpBridgeStartWaitS))
                {
                    g_bridge_down = false;
                    Print("V3 BRIDGE: bridge came up after launch");
                }
                else
                {
                    PrintFormat("V3 BRIDGE: no heartbeat after %ds — DOWN state",
                                InpBridgeStartWaitS);
                }
            }
        }
        else
        {
            Print("V3 BRIDGE: auto-start disabled and no heartbeat — DOWN state");
        }
    }

    // Indicator handles
    g_h_rsi14   = iRSI(_Symbol, PERIOD_M5, 14, PRICE_CLOSE);
    g_h_atr5    = iATR(_Symbol, PERIOD_M5, 5);
    g_h_atr14   = iATR(_Symbol, PERIOD_M5, 14);
    g_h_atr50   = iATR(_Symbol, PERIOD_M5, 50);
    g_h_stoch   = iStochastic(_Symbol, PERIOD_M5, 14, 3, 3, MODE_SMA, STO_LOWHIGH);
    g_h_wpr14   = iWPR(_Symbol, PERIOD_M5, 14);
    g_h_macd    = iMACD(_Symbol, PERIOD_M5, 12, 26, 9, PRICE_CLOSE);
    g_h_bb      = iBands(_Symbol, PERIOD_M5, 20, 0, 2.0, PRICE_CLOSE);
    g_h_adx14   = iADX(_Symbol, PERIOD_M5, 14);
    g_h_ema20   = iMA(_Symbol, PERIOD_M5, 20, 0, MODE_EMA, PRICE_CLOSE);
    g_h_ema50   = iMA(_Symbol, PERIOD_M5, 50, 0, MODE_EMA, PRICE_CLOSE);
    g_h_ema200  = iMA(_Symbol, PERIOD_M5, 200, 0, MODE_EMA, PRICE_CLOSE);
    g_h_h1_ema20  = iMA(_Symbol, PERIOD_H1, 20, 0, MODE_EMA, PRICE_CLOSE);
    g_h_h1_ema50  = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
    g_h_h1_ema200 = iMA(_Symbol, PERIOD_H1, 200, 0, MODE_EMA, PRICE_CLOSE);
    g_h_h1_atr14  = iATR(_Symbol, PERIOD_H1, 14);
    g_h_h1_rsi14  = iRSI(_Symbol, PERIOD_H1, 14, PRICE_CLOSE);
    g_h_h1_bb     = iBands(_Symbol, PERIOD_H1, 20, 0, 2.0, PRICE_CLOSE);

    // ZigZag Lines MTF — same parameter order as VECTOR80_Prototype
    g_zz_handle = iCustom(_Symbol, PERIOD_M5, InpZZName,
                          IntegerToString(InpZZTmpMaxBars), InpZZIndPeriod,
                          InpZZDepth, InpZZDeviation, InpZZBackstep);
    if(g_zz_handle == INVALID_HANDLE)
    {
        Print("V3 ERROR: ZigZag Lines MTF indicator not found — install from Market");
        return INIT_FAILED;
    }
    g_last_zz_pivot_seen = 0;

    PrintFormat("VECTOR003 v2.31 ready  thr=%.2f cd=%dmin localN=%d  risk=%.1f%%  [bridge Stage-1 + local-N gate + immediate trail]",
        InpThreshold, InpCooldownMin, InpLocalN, InpRiskPct);
    PrintFormat("  Bridge state: %s  (last hb ts=%.1f  age=%.1fs)",
        g_bridge_down ? "DOWN" : "OK",
        g_last_heartbeat_ts,
        g_last_heartbeat_ts > 0 ? (double)TimeGMT() - g_last_heartbeat_ts : -1.0);
    return INIT_SUCCEEDED;
}

void OnTick()
{
    // Watchdog: refresh EA lock + check bridge heartbeat once per second.
    if(!(bool)MQLInfoInteger(MQL_TESTER))
    {
        if(TimeCurrent() - g_last_hb_check >= 1)
        {
            g_last_hb_check = TimeCurrent();
            RefreshEALock();
            bool alive = BridgeIsAlive(InpBridgeStaleSec);
            if(alive && g_bridge_down)
            {
                g_bridge_down = false;
                Print("V3 BRIDGE: heartbeat restored — trading resumed");
            }
            else if(!alive && !g_bridge_down)
            {
                g_bridge_down = true;
                Print("V3 BRIDGE: heartbeat lost — trading paused");
            }
        }
    }
    else
    {
        g_bridge_down = false;   // tester path: skip watchdog
    }

    datetime m5_now = (datetime)SeriesInfoInteger(_Symbol, PERIOD_M5, SERIES_LASTBAR_DATE);
    if(m5_now != g_last_m5_bar)
    {
        g_last_m5_bar = m5_now;
        CheckSignal();
    }
    ManagePositions();
    UpdatePanel();
}

void OnDeinit(const int reason)
{
    PrintFormat("V3 OnDeinit reason=%d  signals=%d  open=%d",
                reason, g_signals_fired, CountOpen());
    bool is_tester = (bool)MQLInfoInteger(MQL_TESTER);
    if(!is_tester)
    {
        DeleteEALock();
        // Clean visuals
        ObjectsDeleteAll(0, "V3_");
    }
    // Release indicator handles
    if(g_h_rsi14 != INVALID_HANDLE) IndicatorRelease(g_h_rsi14);
    if(g_h_atr5 != INVALID_HANDLE)  IndicatorRelease(g_h_atr5);
    if(g_h_atr14 != INVALID_HANDLE) IndicatorRelease(g_h_atr14);
    if(g_h_atr50 != INVALID_HANDLE) IndicatorRelease(g_h_atr50);
    if(g_h_stoch != INVALID_HANDLE) IndicatorRelease(g_h_stoch);
    if(g_h_wpr14 != INVALID_HANDLE) IndicatorRelease(g_h_wpr14);
    if(g_h_macd != INVALID_HANDLE)  IndicatorRelease(g_h_macd);
    if(g_h_bb != INVALID_HANDLE)    IndicatorRelease(g_h_bb);
    if(g_h_adx14 != INVALID_HANDLE) IndicatorRelease(g_h_adx14);
    if(g_h_ema20 != INVALID_HANDLE) IndicatorRelease(g_h_ema20);
    if(g_h_ema50 != INVALID_HANDLE) IndicatorRelease(g_h_ema50);
    if(g_h_ema200 != INVALID_HANDLE) IndicatorRelease(g_h_ema200);
    if(g_h_h1_ema20 != INVALID_HANDLE) IndicatorRelease(g_h_h1_ema20);
    if(g_h_h1_ema50 != INVALID_HANDLE) IndicatorRelease(g_h_h1_ema50);
    if(g_h_h1_ema200 != INVALID_HANDLE) IndicatorRelease(g_h_h1_ema200);
    if(g_h_h1_atr14 != INVALID_HANDLE) IndicatorRelease(g_h_h1_atr14);
    if(g_h_h1_rsi14 != INVALID_HANDLE) IndicatorRelease(g_h_h1_rsi14);
    if(g_h_h1_bb    != INVALID_HANDLE) IndicatorRelease(g_h_h1_bb);
    if(g_zz_handle  != INVALID_HANDLE) IndicatorRelease(g_zz_handle);
}
//+------------------------------------------------------------------+
