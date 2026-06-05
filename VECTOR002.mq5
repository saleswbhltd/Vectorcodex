//+------------------------------------------------------------------+
//|                                                  VECTOR002.mq5   |
//|                                                                  |
//|  M5 pivot quality filter + M1 early-execution entry              |
//|                                                                  |
//|  Research basis: /home/cmake/Vector/research/                    |
//|  2026 OOS (Jan-Jun): 108 trades, +11.5 pips/trade, 74% WR        |
//|                                                                  |
//|  Architecture:                                                   |
//|    1. M5 20-pip ZigZag detects pivots                            |
//|    2. Quality filter at pivot bar (G1+G3+G6 must all pass):      |
//|         atr14_pips ∈ [6,11]                                      |
//|         dist_to_today_low_pips ≤ 80                              |
//|         confirm_lag ≤ 8 M5 bars                                  |
//|    3. M1 monitoring: enter market when retracement = +5 pips     |
//|       from pivot extreme. Max wait 60 M1 bars.                   |
//|    4. SL=10pip initial, trail=10pip behind max-favorable,        |
//|       time stop +60 min.                                         |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property copyright "VECTOR research 2026-06"
#property description "M5 quality + M1 early entry — research-validated pivot EA"

//══════════════════════════════════════════════════════════════════
// INPUTS
//══════════════════════════════════════════════════════════════════

input group "=== Risk ==="
input double  InpRiskPct           = 1.0;         // % equity per trade
input int     InpMaxOpenTrades     = 4;           // Max simultaneous positions
input int     InpMagic             = 20020001;

input group "=== M5 Pivot Detection ==="
input double  InpM5ThreshPips      = 20.0;        // M5 ZigZag flip threshold (pips)

input group "=== Quality Filter (at pivot bar) ==="
input double  InpATRMin            = 6.0;         // G1: atr14_pips min
input double  InpATRMax            = 11.0;        // G1: atr14_pips max
input double  InpMaxDistTodayLow   = 80.0;        // G3: pips above today's low
input int     InpMaxConfirmLagM5   = 8;           // G6: max M5 bars to confirm

input group "=== M1 Entry Trigger ==="
input double  InpM1TriggerPips     = 5.0;         // M1 retracement for entry
input int     InpMaxWaitM1Bars     = 60;          // Max M1 bars to wait

input group "=== Trade Management ==="
input double  InpSLPips            = 10.0;        // Initial stop loss
input double  InpTrailPips         = 10.0;        // Trail distance
input int     InpTimeoutMin        = 60;          // Position timeout (minutes)

input group "=== Visual / Debug ==="
input bool    InpDrawArrows        = true;
input bool    InpShowPanel         = true;
input bool    InpArrowsOnly        = false;       // Draw only, don't trade

//══════════════════════════════════════════════════════════════════
// GLOBALS
//══════════════════════════════════════════════════════════════════
double    g_pip;
int       g_atrM5_handle = INVALID_HANDLE;
datetime  g_last_m5_bar  = 0;
datetime  g_last_m1_bar  = 0;
int       g_signals_drawn = 0;

#define MAX_MONITORS  16
#define MAX_POSITIONS 16

//──────────────────────────────────────────────────────────────────
// SMonitor — one active M1-entry monitor per filtered pivot
//──────────────────────────────────────────────────────────────────
struct SMonitor
{
    bool      active;
    datetime  monitor_start;     // when we started watching M1
    datetime  pivot_time;
    double    pivot_price;
    bool      is_high;           // true → SELL pivot, false → BUY pivot
    double    trigger_price;     // pivot ± InpM1TriggerPips
    int       m1_bars_waited;
    // Filter context — carried to position record on entry
    datetime  confirm_time;
    int       confirm_lag;
    double    atr_at_pivot;
    double    d2low_at_pivot;
};
SMonitor  g_monitors[MAX_MONITORS];

//──────────────────────────────────────────────────────────────────
// SPosition — one record per open managed position
//──────────────────────────────────────────────────────────────────
struct SPosition
{
    bool      active;
    ulong     ticket;
    datetime  entry_time;
    double    entry_price;
    double    current_sl;
    double    initial_sl;
    bool      is_buy;
    double    max_favorable_pips;
    int       trail_moves;
    bool      sl_was_moved;
    double    lots;
    string    tag;

    // Journal context — captured at OpenPosition so we can write a full trade record on close
    datetime  pivot_time;
    double    pivot_price;
    datetime  confirm_time;
    int       confirm_lag;
    double    atr_at_pivot;
    double    d2low_at_pivot;
    datetime  monitor_start;
    double    trigger_price;
    int       m1_bars_to_trigger;
};
SPosition g_positions[MAX_POSITIONS];

//──────────────────────────────────────────────────────────────────
// CJournal — per-run CSV logging (trades + events)
//──────────────────────────────────────────────────────────────────
class CJournal
{
private:
    bool    m_enabled;
    int     m_hTrades;
    int     m_hEvents;
    string  m_trades_file;
    string  m_events_file;

public:
    void Init(string trades_file, string events_file, bool enabled);
    void Deinit();
    void Flush();
    void WriteEvent(string event_type, ulong ticket, string direction,
                    double price, string note);
    void WriteTrade(const SPosition &p, double close_price, datetime close_time,
                    string close_reason, double pips, double usd);
};

void CJournal::Init(string trades_file, string events_file, bool enabled)
{
    m_enabled     = enabled;
    m_trades_file = trades_file;
    m_events_file = events_file;
    m_hTrades = INVALID_HANDLE;
    m_hEvents = INVALID_HANDLE;
    if(!enabled) return;

    // Per-run files: in tester (single test) start fresh; in live keep appending.
    bool is_tester = (bool)MQLInfoInteger(MQL_TESTER);
    bool is_optim  = (bool)MQLInfoInteger(MQL_OPTIMIZATION);
    if(is_tester && !is_optim)
    {
        if(FileIsExist(trades_file, FILE_COMMON)) FileDelete(trades_file, FILE_COMMON);
        if(FileIsExist(events_file, FILE_COMMON)) FileDelete(events_file, FILE_COMMON);
    }

    // Open/create with header.  Append behaviour: seek to end if file already exists.
    bool trades_new = !FileIsExist(trades_file, FILE_COMMON);
    bool events_new = !FileIsExist(events_file, FILE_COMMON);
    m_hTrades = FileOpen(trades_file,
        FILE_READ | FILE_WRITE | FILE_CSV | FILE_SHARE_READ | FILE_COMMON | FILE_UNICODE, '|');
    if(m_hTrades != INVALID_HANDLE)
    {
        if(trades_new)
        {
            FileWrite(m_hTrades, "ticket","symbol","direction",
                "pivot_time","pivot_price","confirm_time","confirm_lag_m5",
                "atr_at_pivot","d2low_at_pivot",
                "monitor_start","trigger_price","m1_bars_to_trigger",
                "entry_time","entry_price","initial_sl",
                "close_time","close_price","close_reason",
                "lots","pips","usd",
                "max_favorable_pips","trail_moves","hold_minutes");
        }
        else FileSeek(m_hTrades, 0, SEEK_END);
        FileFlush(m_hTrades);
    }
    m_hEvents = FileOpen(events_file,
        FILE_READ | FILE_WRITE | FILE_CSV | FILE_SHARE_READ | FILE_COMMON | FILE_UNICODE, '|');
    if(m_hEvents != INVALID_HANDLE)
    {
        if(events_new)
            FileWrite(m_hEvents, "timestamp","event","ticket","direction","price","note");
        else FileSeek(m_hEvents, 0, SEEK_END);
        FileFlush(m_hEvents);
    }
    PrintFormat("V2 Journal: trades=%s events=%s  (UTF-16 LE | separated)",
                trades_file, events_file);
}

void CJournal::Deinit()
{
    if(m_hTrades != INVALID_HANDLE) { FileClose(m_hTrades); m_hTrades = INVALID_HANDLE; }
    if(m_hEvents != INVALID_HANDLE) { FileClose(m_hEvents); m_hEvents = INVALID_HANDLE; }
}

void CJournal::Flush()
{
    if(m_hTrades != INVALID_HANDLE) FileFlush(m_hTrades);
    if(m_hEvents != INVALID_HANDLE) FileFlush(m_hEvents);
}

void CJournal::WriteEvent(string event_type, ulong ticket, string direction,
                          double price, string note)
{
    if(!m_enabled || m_hEvents == INVALID_HANDLE) return;
    FileWrite(m_hEvents,
        TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
        event_type,
        IntegerToString((long)ticket),
        direction,
        DoubleToString(price, _Digits),
        note);
    FileFlush(m_hEvents);
}

void CJournal::WriteTrade(const SPosition &p, double close_price, datetime close_time,
                          string close_reason, double pips, double usd)
{
    if(!m_enabled || m_hTrades == INVALID_HANDLE) return;
    int hold_min = (int)((close_time - p.entry_time) / 60);
    FileWrite(m_hTrades,
        IntegerToString((long)p.ticket),
        _Symbol,
        p.is_buy ? "BUY" : "SELL",
        TimeToString(p.pivot_time,    TIME_DATE | TIME_SECONDS),
        DoubleToString(p.pivot_price, _Digits),
        TimeToString(p.confirm_time,  TIME_DATE | TIME_SECONDS),
        IntegerToString(p.confirm_lag),
        DoubleToString(p.atr_at_pivot, 2),
        DoubleToString(p.d2low_at_pivot, 1),
        TimeToString(p.monitor_start, TIME_DATE | TIME_SECONDS),
        DoubleToString(p.trigger_price, _Digits),
        IntegerToString(p.m1_bars_to_trigger),
        TimeToString(p.entry_time,    TIME_DATE | TIME_SECONDS),
        DoubleToString(p.entry_price, _Digits),
        DoubleToString(p.initial_sl,  _Digits),
        TimeToString(close_time,      TIME_DATE | TIME_SECONDS),
        DoubleToString(close_price,   _Digits),
        close_reason,
        DoubleToString(p.lots, 2),
        DoubleToString(pips, 1),
        DoubleToString(usd, 2),
        DoubleToString(p.max_favorable_pips, 1),
        IntegerToString(p.trail_moves),
        IntegerToString(hold_min));
    FileFlush(m_hTrades);
}

CJournal g_journal;

//──────────────────────────────────────────────────────────────────
// CM5ZigZag — pip-threshold ZigZag on M5
// Maintains state across ticks; processes one new bar at a time.
//──────────────────────────────────────────────────────────────────
class CM5ZigZag
{
private:
    double    m_thresh;             // in price units
    bool      m_initialized;
    bool      m_dir_up;             // true = tracking running HIGH
    double    m_ext;                // current extreme price
    datetime  m_ext_time;
    double    m_last_high;
    datetime  m_last_high_time;
    double    m_last_low;
    datetime  m_last_low_time;
    datetime  m_last_processed_bar;

    // Latest confirmed pivot — Consume() resets these
    bool      m_have_pivot;
    datetime  m_pivot_time;
    double    m_pivot_price;
    bool      m_pivot_is_high;
    datetime  m_confirm_time;
    int       m_confirm_lag_bars;

    void ProcessBar(const MqlRates &r);

public:
    void Init(double thresh_pips);
    bool ProcessNewBar();    // returns true if a new pivot is ready
    bool Consume(datetime &t, double &px, bool &is_high,
                 datetime &confirm, int &lag);
};

void CM5ZigZag::Init(double thresh_pips)
{
    m_thresh = thresh_pips * g_pip;
    m_initialized = false;
    m_dir_up = true;
    m_ext = 0;
    m_ext_time = 0;
    m_last_high = 0; m_last_low = 0;
    m_last_high_time = 0; m_last_low_time = 0;
    m_last_processed_bar = 0;
    m_have_pivot = false;
    m_pivot_time = 0; m_pivot_price = 0; m_pivot_is_high = false;
    m_confirm_time = 0; m_confirm_lag_bars = 0;

    // Initialise from history — replay last 500 M5 bars to warm up state
    MqlRates rates[];
    int n = CopyRates(_Symbol, PERIOD_M5, 0, 500, rates);
    if(n < 3) return;
    // CopyRates returns oldest→newest by default in MQL5
    // Initialise direction from first two bars
    m_dir_up  = rates[1].high >= rates[0].high;
    m_ext     = m_dir_up ? rates[1].high : rates[1].low;
    m_ext_time = rates[1].time;
    m_last_processed_bar = 0;   // we'll process inside loop

    for(int i = 2; i < n; i++)
    {
        // Suppress pivot emission during warm-up; reset flag at end
        ProcessBar(rates[i]);
    }
    m_have_pivot = false;
    m_initialized = true;
    PrintFormat("V2 ZZ init complete: %d bars replayed  dir_up=%d  ext=%.5f",
                n, (int)m_dir_up, m_ext);
}

void CM5ZigZag::ProcessBar(const MqlRates &r)
{
    if(m_dir_up)
    {
        if(r.high > m_ext)
        {
            m_ext = r.high;
            m_ext_time = r.time;
        }
        else if(r.low <= m_ext - m_thresh)
        {
            // ZZ flips DOWN → swing HIGH confirmed at m_ext_time
            m_pivot_time   = m_ext_time;
            m_pivot_price  = m_ext;
            m_pivot_is_high = true;
            m_confirm_time = r.time;
            m_confirm_lag_bars = (int)((r.time - m_ext_time) / 300);
            m_have_pivot = true;

            m_last_high = m_ext;
            m_last_high_time = m_ext_time;
            m_dir_up = false;
            m_ext = r.low;
            m_ext_time = r.time;
        }
    }
    else
    {
        if(r.low < m_ext)
        {
            m_ext = r.low;
            m_ext_time = r.time;
        }
        else if(r.high >= m_ext + m_thresh)
        {
            // ZZ flips UP → swing LOW confirmed
            m_pivot_time   = m_ext_time;
            m_pivot_price  = m_ext;
            m_pivot_is_high = false;
            m_confirm_time = r.time;
            m_confirm_lag_bars = (int)((r.time - m_ext_time) / 300);
            m_have_pivot = true;

            m_last_low = m_ext;
            m_last_low_time = m_ext_time;
            m_dir_up = true;
            m_ext = r.high;
            m_ext_time = r.time;
        }
    }
}

bool CM5ZigZag::ProcessNewBar()
{
    if(!m_initialized) return false;
    // Read the just-closed M5 bar (index 1 in series order)
    MqlRates rates[];
    if(CopyRates(_Symbol, PERIOD_M5, 1, 1, rates) < 1) return false;
    if(rates[0].time == m_last_processed_bar) return m_have_pivot;
    m_last_processed_bar = rates[0].time;
    m_have_pivot = false;
    ProcessBar(rates[0]);
    return m_have_pivot;
}

bool CM5ZigZag::Consume(datetime &t, double &px, bool &is_high,
                        datetime &confirm, int &lag)
{
    if(!m_have_pivot) return false;
    t = m_pivot_time; px = m_pivot_price; is_high = m_pivot_is_high;
    confirm = m_confirm_time; lag = m_confirm_lag_bars;
    m_have_pivot = false;
    return true;
}

CM5ZigZag g_zz;

//══════════════════════════════════════════════════════════════════
// HELPERS
//══════════════════════════════════════════════════════════════════

double Pip()
{
    int d = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
    return (d == 5 || d == 3) ? 10.0 * _Point : _Point;
}

double GetATR_M5()
{
    if(g_atrM5_handle == INVALID_HANDLE) return 0.0;
    double buf[];
    if(CopyBuffer(g_atrM5_handle, 0, 1, 1, buf) < 1) return 0.0;
    return buf[0] / g_pip;        // ATR in pips
}

double GetTodayLow()
{
    // Current day's running low
    MqlRates daily[];
    if(CopyRates(_Symbol, PERIOD_D1, 0, 1, daily) < 1) return 0.0;
    return daily[0].low;
}

double DistanceToTodayLowPips()
{
    double today_low = GetTodayLow();
    if(today_low <= 0) return 999;
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    return (bid - today_low) / g_pip;
}

double Normalize(double price)
{
    return NormalizeDouble(price, (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS));
}

double CalcLots(double sl_pips)
{
    double equity      = AccountInfoDouble(ACCOUNT_EQUITY);
    double risk_amount = equity * InpRiskPct / 100.0;
    double tick_size   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double tick_value  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    if(tick_size <= 0 || tick_value <= 0) return 0;
    double pip_value   = (tick_value / tick_size) * g_pip;   // $ per pip per lot
    if(pip_value <= 0) return 0;
    double raw_lots    = risk_amount / (sl_pips * pip_value);
    double step        = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double min_lot     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    double max_lot     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
    double lots        = MathFloor(raw_lots / step) * step;
    if(lots < min_lot) lots = min_lot;
    if(lots > max_lot) lots = max_lot;
    return lots;
}

int CountOpenByDirection(bool is_buy)
{
    int n = 0;
    for(int i = 0; i < MAX_POSITIONS; i++)
        if(g_positions[i].active && g_positions[i].is_buy == is_buy) n++;
    return n;
}

int CountOpen()
{
    int n = 0;
    for(int i = 0; i < MAX_POSITIONS; i++)
        if(g_positions[i].active) n++;
    return n;
}

//══════════════════════════════════════════════════════════════════
// FILTER — apply G1+G3+G6 at the pivot bar
//══════════════════════════════════════════════════════════════════
bool PassesQualityFilter(int confirm_lag_bars, string &reason)
{
    double atr = GetATR_M5();
    if(atr < InpATRMin)
    {
        reason = StringFormat("G1 fail: atr=%.1f < %.1f", atr, InpATRMin);
        return false;
    }
    if(atr > InpATRMax)
    {
        reason = StringFormat("G1 fail: atr=%.1f > %.1f", atr, InpATRMax);
        return false;
    }
    double d2low = DistanceToTodayLowPips();
    if(d2low > InpMaxDistTodayLow)
    {
        reason = StringFormat("G3 fail: d2low=%.0f > %.0f", d2low, InpMaxDistTodayLow);
        return false;
    }
    if(confirm_lag_bars > InpMaxConfirmLagM5)
    {
        reason = StringFormat("G6 fail: confirm_lag=%d > %d", confirm_lag_bars, InpMaxConfirmLagM5);
        return false;
    }
    reason = StringFormat("PASS atr=%.1f d2low=%.0f lag=%d", atr, d2low, confirm_lag_bars);
    return true;
}

//══════════════════════════════════════════════════════════════════
// MONITOR — start watching M1 for entry trigger
//══════════════════════════════════════════════════════════════════
int FindFreeMonitor()
{
    for(int i = 0; i < MAX_MONITORS; i++) if(!g_monitors[i].active) return i;
    return -1;
}

void AddMonitor(datetime pivot_time, double pivot_price, bool is_high,
                datetime confirm_time, int confirm_lag,
                double atr_at_pivot, double d2low_at_pivot)
{
    int idx = FindFreeMonitor();
    if(idx < 0)
    {
        Print("V2 AddMonitor: no free slot — skipping pivot");
        g_journal.WriteEvent("MONITOR_FULL", 0, is_high ? "SELL" : "BUY",
                             pivot_price, "max monitors reached");
        return;
    }
    SMonitor m;
    ZeroMemory(m);          // critical — see mql5-struct-zero-init memory
    m.active           = true;
    m.monitor_start    = TimeCurrent();
    m.pivot_time       = pivot_time;
    m.pivot_price      = pivot_price;
    m.is_high          = is_high;
    m.trigger_price    = is_high ? pivot_price - InpM1TriggerPips * g_pip
                                  : pivot_price + InpM1TriggerPips * g_pip;
    m.m1_bars_waited   = 0;
    m.confirm_time     = confirm_time;
    m.confirm_lag      = confirm_lag;
    m.atr_at_pivot     = atr_at_pivot;
    m.d2low_at_pivot   = d2low_at_pivot;
    g_monitors[idx]    = m;

    PrintFormat("V2 Monitor[%d] %s pivot=%.5f trigger=%.5f",
                idx, is_high ? "SELL" : "BUY", pivot_price, m.trigger_price);
    g_journal.WriteEvent("MONITOR_ADDED", 0, is_high ? "SELL" : "BUY", pivot_price,
        StringFormat("trigger=%.5f atr=%.1f d2low=%.0f lag=%d",
                     m.trigger_price, atr_at_pivot, d2low_at_pivot, confirm_lag));
}

//══════════════════════════════════════════════════════════════════
// ENTRY — fire when M1 crosses the trigger price
//══════════════════════════════════════════════════════════════════
void CheckMonitor(int idx)
{
    SMonitor m = g_monitors[idx];
    if(!m.active) return;

    // Read the last closed M1 bar
    MqlRates m1[];
    if(CopyRates(_Symbol, PERIOD_M1, 1, 1, m1) < 1) return;

    bool triggered = false;
    if(m.is_high)
        triggered = (m1[0].low <= m.trigger_price);
    else
        triggered = (m1[0].high >= m.trigger_price);

    if(triggered)
    {
        if(!InpArrowsOnly)
            OpenPosition(m);
        g_monitors[idx].active = false;
        return;
    }

    g_monitors[idx].m1_bars_waited++;
    if(g_monitors[idx].m1_bars_waited >= InpMaxWaitM1Bars)
    {
        PrintFormat("V2 Monitor[%d] timeout (%d M1 bars) — abort",
                    idx, g_monitors[idx].m1_bars_waited);
        g_journal.WriteEvent("MONITOR_TIMEOUT", 0,
                             m.is_high ? "SELL" : "BUY", m.pivot_price,
                             StringFormat("waited %d M1 bars", g_monitors[idx].m1_bars_waited));
        g_monitors[idx].active = false;
    }
}

void OpenPosition(const SMonitor &m)
{
    bool is_buy = !m.is_high;
    string dir = is_buy ? "BUY" : "SELL";
    if(CountOpen() >= InpMaxOpenTrades)
    {
        PrintFormat("V2 OpenPosition: max %d positions — skip", InpMaxOpenTrades);
        g_journal.WriteEvent("ENTRY_SKIP_MAX", 0, dir, m.pivot_price,
                             StringFormat("max_open=%d reached", InpMaxOpenTrades));
        return;
    }

    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double entry = is_buy ? ask : bid;
    double sl    = is_buy ? entry - InpSLPips * g_pip
                          : entry + InpSLPips * g_pip;
    sl = Normalize(sl);

    double lots = CalcLots(InpSLPips);
    if(lots <= 0)
    {
        PrintFormat("V2 OpenPosition: lots=%.2f invalid — skip", lots);
        g_journal.WriteEvent("ENTRY_SKIP_LOTS", 0, dir, m.pivot_price, "lots calc failed");
        return;
    }

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
    req.comment   = "V2|" + dir;

    if(!OrderSend(req, res))
    {
        PrintFormat("V2 OrderSend FAILED ret=%d", res.retcode);
        g_journal.WriteEvent("ORDER_SEND_FAIL", 0, dir, entry,
                             StringFormat("retcode=%d", res.retcode));
        return;
    }
    if(res.retcode != TRADE_RETCODE_DONE && res.retcode != TRADE_RETCODE_PLACED)
    {
        PrintFormat("V2 OrderSend not done ret=%d", res.retcode);
        g_journal.WriteEvent("ORDER_NOT_DONE", res.order, dir, entry,
                             StringFormat("retcode=%d", res.retcode));
        return;
    }

    // Track position
    int idx = -1;
    for(int i = 0; i < MAX_POSITIONS; i++)
        if(!g_positions[i].active) { idx = i; break; }
    if(idx < 0)
    {
        Print("V2 OpenPosition: no free position slot — order placed but untracked");
        g_journal.WriteEvent("POSITION_UNTRACKED", res.order, dir, entry, "no free slot");
        return;
    }
    SPosition p;
    ZeroMemory(p);
    p.active            = true;
    p.ticket            = res.order;
    p.entry_time        = TimeCurrent();
    p.entry_price       = res.price > 0 ? res.price : entry;
    p.current_sl        = sl;
    p.initial_sl        = sl;
    p.is_buy            = is_buy;
    p.max_favorable_pips = 0;
    p.trail_moves       = 0;
    p.sl_was_moved      = false;
    p.lots              = lots;
    p.tag               = req.comment;
    // Journal context from monitor
    p.pivot_time         = m.pivot_time;
    p.pivot_price        = m.pivot_price;
    p.confirm_time       = m.confirm_time;
    p.confirm_lag        = m.confirm_lag;
    p.atr_at_pivot       = m.atr_at_pivot;
    p.d2low_at_pivot     = m.d2low_at_pivot;
    p.monitor_start      = m.monitor_start;
    p.trigger_price      = m.trigger_price;
    p.m1_bars_to_trigger = m.m1_bars_waited;
    g_positions[idx] = p;

    PrintFormat("V2 ENTRY %s ticket=%I64u entry=%.5f sl=%.5f lots=%.2f",
                dir, p.ticket, p.entry_price, sl, lots);
    g_journal.WriteEvent("ENTRY", p.ticket, dir, p.entry_price,
        StringFormat("sl=%.5f lots=%.2f m1_wait=%d trigger=%.5f",
                     sl, lots, m.m1_bars_waited, m.trigger_price));
}

//══════════════════════════════════════════════════════════════════
// POSITION MANAGEMENT — trail + time stop
//══════════════════════════════════════════════════════════════════
void ManagePositions()
{
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    datetime now = TimeCurrent();

    for(int i = 0; i < MAX_POSITIONS; i++)
    {
        if(!g_positions[i].active) continue;
        ulong tk = g_positions[i].ticket;

        if(!PositionSelectByTicket(tk))
        {
            // Position no longer open — record close from history.
            RecordExternalClose(i);
            continue;
        }

        // Timeout?
        int held_min = (int)((now - g_positions[i].entry_time) / 60);
        if(held_min >= InpTimeoutMin)
        {
            ClosePosition(i, "timeout");
            continue;
        }

        // Trail
        bool is_buy = g_positions[i].is_buy;
        double cur  = is_buy ? bid : ask;
        double entry = g_positions[i].entry_price;
        double fav_pips = is_buy ? (cur - entry) / g_pip : (entry - cur) / g_pip;
        if(fav_pips > g_positions[i].max_favorable_pips)
            g_positions[i].max_favorable_pips = fav_pips;

        // Trail kicks in only once we're in profit by > trail distance
        if(g_positions[i].max_favorable_pips > InpTrailPips)
        {
            double peak = is_buy ? entry + g_positions[i].max_favorable_pips * g_pip
                                  : entry - g_positions[i].max_favorable_pips * g_pip;
            double new_sl = is_buy ? peak - InpTrailPips * g_pip
                                    : peak + InpTrailPips * g_pip;
            new_sl = Normalize(new_sl);
            bool better = is_buy ? new_sl > g_positions[i].current_sl + g_pip * 0.5
                                  : new_sl < g_positions[i].current_sl - g_pip * 0.5;
            if(better) ModifySL(i, new_sl);
        }
    }
}

// Record a close that we DIDN'T initiate (SL hit, trail hit, manual).
// Looks up history for the actual close price/time and writes the trade record.
void RecordExternalClose(int idx)
{
    ulong tk = g_positions[idx].ticket;
    double close_price = 0; datetime close_time = 0;
    if(HistorySelectByPosition((long)tk))
    {
        int n = HistoryDealsTotal();
        for(int k = n - 1; k >= 0; k--)
        {
            ulong dt = HistoryDealGetTicket(k);
            if(HistoryDealGetInteger(dt, DEAL_POSITION_ID) != (long)tk) continue;
            int entry_type = (int)HistoryDealGetInteger(dt, DEAL_ENTRY);
            if(entry_type == DEAL_ENTRY_OUT || entry_type == DEAL_ENTRY_OUT_BY)
            {
                close_price = HistoryDealGetDouble(dt, DEAL_PRICE);
                close_time  = (datetime)HistoryDealGetInteger(dt, DEAL_TIME);
                break;
            }
        }
    }
    if(close_price <= 0)
    {
        close_price = g_positions[idx].is_buy
                      ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                      : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        close_time = TimeCurrent();
    }
    string reason = g_positions[idx].sl_was_moved ? "TRAIL_HIT" : "SL_HIT";
    double pips = g_positions[idx].is_buy
                  ? (close_price - g_positions[idx].entry_price) / g_pip
                  : (g_positions[idx].entry_price - close_price) / g_pip;
    double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double pip_value  = (tick_size > 0) ? (tick_value / tick_size) * g_pip : 0;
    double usd = pips * pip_value * g_positions[idx].lots;

    g_journal.WriteEvent("CLOSED", tk, g_positions[idx].is_buy ? "BUY" : "SELL",
                         close_price, StringFormat("reason=%s pips=%.1f", reason, pips));
    g_journal.WriteTrade(g_positions[idx], close_price, close_time, reason, pips, usd);
    PrintFormat("V2 CLOSED[%d] ticket=%I64u reason=%s pips=%+.1f", idx, tk, reason, pips);
    g_positions[idx].active = false;
}

void ModifySL(int idx, double new_sl)
{
    MqlTradeRequest req; MqlTradeResult res;
    ZeroMemory(req); ZeroMemory(res);
    req.action   = TRADE_ACTION_SLTP;
    req.position = g_positions[idx].ticket;
    req.symbol   = _Symbol;
    req.sl       = new_sl;
    req.tp       = 0;
    if(!OrderSend(req, res))
    {
        PrintFormat("V2 ModifySL[%d] failed ret=%d", idx, res.retcode);
        g_journal.WriteEvent("SL_MOVE_FAIL", g_positions[idx].ticket,
                             g_positions[idx].is_buy ? "BUY" : "SELL",
                             new_sl, StringFormat("retcode=%d", res.retcode));
        return;
    }
    g_positions[idx].current_sl = new_sl;
    g_positions[idx].trail_moves++;
    g_positions[idx].sl_was_moved = true;
    PrintFormat("V2 Trail[%d] sl→%.5f  max_fav=%.1f", idx, new_sl,
                g_positions[idx].max_favorable_pips);
    g_journal.WriteEvent("SL_TRAIL", g_positions[idx].ticket,
                         g_positions[idx].is_buy ? "BUY" : "SELL",
                         new_sl,
                         StringFormat("max_fav=%.1f move#=%d",
                                      g_positions[idx].max_favorable_pips,
                                      g_positions[idx].trail_moves));
}

void ClosePosition(int idx, string reason)
{
    ulong tk = g_positions[idx].ticket;
    if(!PositionSelectByTicket(tk))
    {
        // Already closed by broker — record via the external-close path instead
        RecordExternalClose(idx);
        return;
    }
    double lots  = PositionGetDouble(POSITION_VOLUME);
    bool is_buy  = g_positions[idx].is_buy;
    double price = is_buy ? SymbolInfoDouble(_Symbol, SYMBOL_BID)
                          : SymbolInfoDouble(_Symbol, SYMBOL_ASK);

    MqlTradeRequest req; MqlTradeResult res;
    ZeroMemory(req); ZeroMemory(res);
    req.action    = TRADE_ACTION_DEAL;
    req.position  = tk;
    req.symbol    = _Symbol;
    req.volume    = lots;
    req.type      = is_buy ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
    req.price     = price;
    req.deviation = 10;
    req.magic     = InpMagic;
    req.comment   = "V2 close: " + reason;
    if(!OrderSend(req, res))
    {
        PrintFormat("V2 ClosePosition[%d] failed ret=%d", idx, res.retcode);
        g_journal.WriteEvent("CLOSE_FAIL", tk, is_buy ? "BUY" : "SELL", price,
                             StringFormat("reason=%s retcode=%d", reason, res.retcode));
        return;
    }
    PrintFormat("V2 CLOSE[%d] ticket=%I64u reason=%s price=%.5f",
                idx, tk, reason, price);
    // Use actual fill price from result if available
    double close_price = res.price > 0 ? res.price : price;
    datetime close_time = TimeCurrent();
    double pips = is_buy ? (close_price - g_positions[idx].entry_price) / g_pip
                          : (g_positions[idx].entry_price - close_price) / g_pip;
    double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
    double tick_size  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
    double pip_value  = (tick_size > 0) ? (tick_value / tick_size) * g_pip : 0;
    double usd = pips * pip_value * g_positions[idx].lots;
    g_journal.WriteEvent("CLOSED", tk, is_buy ? "BUY" : "SELL", close_price,
                         StringFormat("reason=%s pips=%.1f", reason, pips));
    g_journal.WriteTrade(g_positions[idx], close_price, close_time, reason, pips, usd);
    g_positions[idx].active = false;
}

//══════════════════════════════════════════════════════════════════
// VISUAL — draw pivot arrow when a filtered pivot fires
//══════════════════════════════════════════════════════════════════
void DrawArrow(datetime t, double price, bool is_high)
{
    if(!InpDrawArrows) return;
    long cid = ChartID();
    string name = StringFormat("V2_arr_%d_%s", (int)t, is_high ? "S" : "B");
    ObjectDelete(cid, name);
    double pip2 = 2.0 * g_pip;
    double y = is_high ? price + pip2 : price - pip2;
    int code = is_high ? 234 : 233;            // down / up arrow
    color clr = is_high ? clrRed : clrDodgerBlue;
    if(!ObjectCreate(cid, name, OBJ_ARROW, 0, t, y))
    {
        PrintFormat("V2 DrawArrow failed err=%d", GetLastError());
        return;
    }
    ObjectSetInteger(cid, name, OBJPROP_ARROWCODE, code);
    ObjectSetInteger(cid, name, OBJPROP_COLOR,     clr);
    ObjectSetInteger(cid, name, OBJPROP_WIDTH,     3);
    ObjectSetInteger(cid, name, OBJPROP_ANCHOR,
                     is_high ? ANCHOR_BOTTOM : ANCHOR_TOP);
    g_signals_drawn++;
}

//══════════════════════════════════════════════════════════════════
// PANEL
//══════════════════════════════════════════════════════════════════
void UpdatePanel()
{
    if(!InpShowPanel) return;
    int active_monitors = 0;
    for(int i = 0; i < MAX_MONITORS; i++) if(g_monitors[i].active) active_monitors++;

    string txt = StringFormat(
        "VECTOR002  |  M5 thresh=%.0f  M1 trigger=%.0f  SL=%.0f  Trail=%.0f\n"
        "ATR(M5)=%.1f  d2low=%.0f  monitors=%d  open=%d (B=%d S=%d)  signals=%d",
        InpM5ThreshPips, InpM1TriggerPips, InpSLPips, InpTrailPips,
        GetATR_M5(), DistanceToTodayLowPips(),
        active_monitors, CountOpen(),
        CountOpenByDirection(true), CountOpenByDirection(false),
        g_signals_drawn);
    string name = "V2_panel";
    if(ObjectFind(0, name) < 0)
    {
        ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
        ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
        ObjectSetInteger(0, name, OBJPROP_XDISTANCE, 12);
        ObjectSetInteger(0, name, OBJPROP_YDISTANCE, 24);
        ObjectSetInteger(0, name, OBJPROP_COLOR, clrSilver);
        ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 9);
    }
    ObjectSetString(0, name, OBJPROP_TEXT, txt);
}

//══════════════════════════════════════════════════════════════════
// OnInit / OnTick / OnDeinit
//══════════════════════════════════════════════════════════════════
int OnInit()
{
    g_pip = Pip();
    g_atrM5_handle = iATR(_Symbol, PERIOD_M5, 14);
    if(g_atrM5_handle == INVALID_HANDLE)
    {
        Print("V2 ERROR: iATR handle failed");
        return INIT_FAILED;
    }
    // Wait for ATR warm-up
    Sleep(50);
    ZeroMemory(g_monitors);
    ZeroMemory(g_positions);

    g_zz.Init(InpM5ThreshPips);

    // Journal: per-run timestamped filenames in tester mode (avoid mixing runs),
    // single fixed file in live mode.
    bool is_tester = (bool)MQLInfoInteger(MQL_TESTER);
    bool is_optim  = (bool)MQLInfoInteger(MQL_OPTIMIZATION);
    string trades_file = "VECTOR002_trades.csv";
    string events_file = "VECTOR002_events.csv";
    if(is_tester && !is_optim)
    {
        MqlDateTime dt; TimeToStruct(TimeCurrent(), dt);
        string ts = StringFormat("%04d%02d%02d_%02d%02d",
                                 dt.year, dt.mon, dt.day, dt.hour, dt.min);
        trades_file = "VECTOR002_trades_" + ts + ".csv";
        events_file = "VECTOR002_events_" + ts + ".csv";
    }
    g_journal.Init(trades_file, events_file, !is_optim);
    g_journal.WriteEvent("EA_START", 0, "-", 0,
        StringFormat("M5=%.0f M1trig=%.0f atr[%.1f-%.1f] d2low<=%.0f lag<=%d "
                     "SL=%.0f trail=%.0f timeout=%d risk=%.1f%%",
                     InpM5ThreshPips, InpM1TriggerPips, InpATRMin, InpATRMax,
                     InpMaxDistTodayLow, InpMaxConfirmLagM5,
                     InpSLPips, InpTrailPips, InpTimeoutMin, InpRiskPct));

    PrintFormat("VECTOR002 ready — M5 thresh=%.0f pip, M1 trigger=%.0f pip, "
                "filter ATR[%.1f,%.1f] d2low≤%.0f lag≤%d, "
                "SL=%.0f trail=%.0f timeout=%dmin, risk=%.1f%%",
                InpM5ThreshPips, InpM1TriggerPips,
                InpATRMin, InpATRMax, InpMaxDistTodayLow, InpMaxConfirmLagM5,
                InpSLPips, InpTrailPips, InpTimeoutMin, InpRiskPct);
    return INIT_SUCCEEDED;
}

void OnTick()
{
    // Detect new M5 bar (trigger pivot detection + filter)
    datetime m5_now = (datetime)SeriesInfoInteger(_Symbol, PERIOD_M5, SERIES_LASTBAR_DATE);
    if(m5_now != g_last_m5_bar)
    {
        g_last_m5_bar = m5_now;
        if(g_zz.ProcessNewBar())
        {
            datetime pt, ct; double pp; bool ih; int lag;
            if(g_zz.Consume(pt, pp, ih, ct, lag))
            {
                double atr_now   = GetATR_M5();
                double d2low_now = DistanceToTodayLowPips();
                string why;
                bool passes = PassesQualityFilter(lag, why);
                PrintFormat("V2 PIVOT %s pivot_time=%s price=%.5f confirm_lag=%d → %s",
                            ih ? "SELL" : "BUY", TimeToString(pt), pp, lag, why);
                g_journal.WriteEvent("PIVOT", 0, ih ? "SELL" : "BUY", pp,
                    StringFormat("pivot_time=%s confirm_lag=%d atr=%.1f d2low=%.0f",
                                 TimeToString(pt, TIME_DATE | TIME_SECONDS),
                                 lag, atr_now, d2low_now));
                if(passes)
                {
                    DrawArrow(pt, pp, ih);
                    AddMonitor(pt, pp, ih, ct, lag, atr_now, d2low_now);
                    g_journal.WriteEvent("FILTER_PASS", 0, ih ? "SELL" : "BUY", pp, why);
                }
                else
                {
                    g_journal.WriteEvent("FILTER_FAIL", 0, ih ? "SELL" : "BUY", pp, why);
                }
            }
        }
    }

    // Process M1 entry monitors on each new M1 bar
    datetime m1_now = (datetime)SeriesInfoInteger(_Symbol, PERIOD_M1, SERIES_LASTBAR_DATE);
    if(m1_now != g_last_m1_bar)
    {
        g_last_m1_bar = m1_now;
        for(int i = 0; i < MAX_MONITORS; i++) CheckMonitor(i);
    }

    // Manage open positions on every tick
    ManagePositions();

    // Refresh panel periodically (every M1 bar is enough)
    if(m1_now == g_last_m1_bar) UpdatePanel();
}

void OnDeinit(const int reason)
{
    g_journal.WriteEvent("EA_STOP", 0, "-", 0,
        StringFormat("signals=%d open=%d reason=%d",
                     g_signals_drawn, CountOpen(), reason));
    g_journal.Flush();
    g_journal.Deinit();

    if(g_atrM5_handle != INVALID_HANDLE)
        IndicatorRelease(g_atrM5_handle);

    bool is_tester = (bool)MQLInfoInteger(MQL_TESTER);
    if(!is_tester)
    {
        // Clean up visuals on live chart
        ObjectsDeleteAll(0, "V2_");
    }
    PrintFormat("V2 OnDeinit: drew %d signals, open positions=%d",
                g_signals_drawn, CountOpen());
}
//+------------------------------------------------------------------+
