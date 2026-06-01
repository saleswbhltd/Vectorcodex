//+------------------------------------------------------------------+
//| VECTOR001.mq5 — SMC Structural EA v1.0                          |
//|                                                                  |
//| Flow:                                                            |
//|   H4 structure → major bias                                     |
//|   H1 BOS or ChoCh → entry signal (both directions)             |
//|   OB limit order → market fallback after InpFallbackBars H1     |
//|   SL = beyond OB edge + buffer                                  |
//|   TP1 = nearest H1 swing  TP2 = H4 swing (2 slots)             |
//|                                                                  |
//|   With-trend  : standard risk, min 1.5 RR                       |
//|   Counter-trend: half risk,    min 2.5 RR                       |
//+------------------------------------------------------------------+
#property copyright   "VECTOR"
#property version     "1.00"
#property description "VECTOR001 — H4 bias + H1 BOS/ChoCh"
#property strict

#define SMC_PFX "V1_"

// .mqh files live in Experts/SMCEA/ — one folder up then into SMCEA/
#include "../SMCEA/SMCEA_Risk.mqh"       // SMCEA_NormalizePrice, SMCEA_CheckMinStops, CalcLots helpers
#include "../SMCEA/SMCEA_Manager.mqh"    // CTradeManager, SSetup — also pulls in SMCEA_Defs + Journal
#include "../SMCEA/MTF.mqh"              // CMTFEngine (H1/H4 structure + OBs)

//──────────────────────────────────────────────────────────────────
//  Inputs
//──────────────────────────────────────────────────────────────────

input group "=== Risk ==="
input double InpRiskPct         = 1.0;   // % equity per trade — with-trend
input double InpCounterRiskPct  = 0.5;   // % equity per trade — counter-trend
input double InpMinRR           = 1.5;   // Min RR to open — with-trend
input double InpCounterMinRR    = 2.5;   // Min RR to open — counter-trend
input int    InpMaxBuys         = 3;     // Max simultaneous BUY trades
input int    InpMaxSells        = 3;     // Max simultaneous SELL trades
input int    InpMagic           = 20010001;

input group "=== Entry ==="
input int    InpFallbackBars    = 3;     // H1 bars before limit → market fallback
input double InpOBBufferPips    = 2.0;   // Extra pips inside OB zone for limit price
input double InpSLBufferPips    = 3.0;   // Pips beyond OB edge for SL
input double InpMinSLPips       = 2.0;   // Reject trade if SL < this (pips)
input int    InpOBLookback      = 20;    // Max H1 bars to scan back for OB candle
input double InpMaxSpreadPips   = 2.5;   // Block entry if spread wider (pips)

input group "=== Signal Debug ==="
input bool   InpArrowsOnly      = false; // Draw arrows only — no trades (visual signal test)
input double InpH1ThreshPips    = 30.0;  // H1 ZigZag threshold — pips to flip direction

input group "=== Trade Management ==="
input double InpBEBufferPips    = 7.0;   // Pips profit before breakeven
input bool   InpUseTrailing     = true;
input double InpTrailPips       = 20.0;  // Trail distance in pips

input group "=== TP ==="
input double InpMinTP2Pips      = 30.0;  // TP2 minimum distance — skip if closer
input int    InpPendingExpiryH  = 24;    // Pending order expiry (hours)

input group "=== Display ==="
input bool   InpShowPanel       = true;
input bool   InpShowH1OBs       = true;
input bool   InpShowH4OBs       = false;

//──────────────────────────────────────────────────────────────────
//  Per-direction break slot
//──────────────────────────────────────────────────────────────────

struct SBreakSlot
{
    bool     active;
    bool     isBull;
    bool     isCounterTrend;
    bool     isBOS;

    datetime breakTime;     // H1 bar close that caused the break
    double   breakLevel;    // swing level that was broken
    datetime oppTime;       // opposite pivot time (impulse origin)

    double   obTop;         // OB zone top
    double   obBottom;      // OB zone bottom
    bool     hasOB;         // true = real OB; false = estimated Fib zone

    int      h1BarsAtDetect;  // Bars(H1) snapshot when we processed this break
    bool     limitPlaced;     // a limit order is alive for this break
    ulong    limitTicket;     // the pending order ticket

    void Reset() { active=false; limitPlaced=false; limitTicket=0; h1BarsAtDetect=0; }
};

//══════════════════════════════════════════════════════════════════
//  CH1PivotTracker — pip-threshold ZigZag on H1
//
//  Matches the Step 1 research algorithm exactly:
//    direction flips when price moves >= threshPips from the last extreme.
//  Every flip fires a signal:
//    ZZ turns UP   → BULL signal  (swing LOW confirmed, price rose >= thresh)
//    ZZ turns DOWN → BEAR signal  (swing HIGH confirmed, price fell >= thresh)
//  isBOS  = flip continues the ZZ sequence (Higher Low / Lower High)
//  ChoCh  = flip reverses   the ZZ sequence (Lower  Low / Higher High)
//══════════════════════════════════════════════════════════════════

struct SZZBreak
{
    datetime swingTime;   // time the pivot extreme formed
    double   price;       // pivot extreme price (swing LOW for BULL, swing HIGH for BEAR)
    datetime breakTime;   // H1 bar that triggered the ZZ flip
    bool     isUp;        // true = BULL signal, false = BEAR signal
    bool     isBOS;       // true = BOS (continuation), false = ChoCh (reversal)
    datetime oppTime;     // opposing pivot time (for OB scan)
};

class CH1PivotTracker
{
private:
    double      m_thresh;        // flip threshold in price points
    bool        m_dirUp;         // true = currently tracking upward move
    double      m_ext;           // current extreme price
    datetime    m_extTime;       // time of current extreme

    double      m_lastHigh;      // last confirmed ZZ swing HIGH price
    datetime    m_lastHighTime;
    double      m_lastLow;       // last confirmed ZZ swing LOW price
    datetime    m_lastLowTime;

    SZZBreak    m_breaks[];
    int         m_breakCount;
    datetime    m_lastBar;       // most-recent H1 bar processed

    void        ProcessBar(const MqlRates &r);
    void        AddBreak(datetime swingTime, double price, datetime breakTime,
                         bool isUp, bool isBOS, datetime oppTime);

public:
    void    Init(double threshPips, int maxBreaks = 5000);
    void    ScanAll();
    void    Update();

    int     GetBreakCount()  const { return m_breakCount; }
    bool    GetBreakAt(int idx,
                       datetime &swingTime, double &price,
                       datetime &breakTime, bool &isUp,  bool &isBOS,
                       datetime &oppTime) const;

    // Nearest/furthest swing levels — used by FindTPs
    double  GetNearestSwingAbove (double p) const;
    double  GetNearestSwingBelow (double p) const;
    double  GetFurthestSwingAbove(double p) const;
    double  GetFurthestSwingBelow(double p) const;
};

//──────────────────────────────────────────────────────────────────

void CH1PivotTracker::Init(double threshPips, int maxBreaks)
{
    m_thresh      = threshPips * PipSz();
    m_breakCount  = 0;
    m_lastBar     = 0;
    m_dirUp       = true;
    m_ext         = 0;
    m_extTime     = 0;
    m_lastHigh    = 0; m_lastHighTime = 0;
    m_lastLow     = 0; m_lastLowTime  = 0;
    ArrayResize(m_breaks, maxBreaks);
}

void CH1PivotTracker::AddBreak(datetime swingTime, double price, datetime breakTime,
                                bool isUp, bool isBOS, datetime oppTime)
{
    int cap = ArraySize(m_breaks);
    if(m_breakCount >= cap) ArrayResize(m_breaks, cap + 1000);
    m_breaks[m_breakCount].swingTime = swingTime;
    m_breaks[m_breakCount].price     = price;
    m_breaks[m_breakCount].breakTime = breakTime;
    m_breaks[m_breakCount].isUp      = isUp;
    m_breaks[m_breakCount].isBOS     = isBOS;
    m_breaks[m_breakCount].oppTime   = oppTime;
    m_breakCount++;
}

void CH1PivotTracker::ProcessBar(const MqlRates &r)
{
    // Bootstrap on very first bar
    if(m_ext == 0)
    {
        m_dirUp        = true;
        m_ext          = r.high;
        m_extTime      = r.time;
        m_lastHigh     = r.high; m_lastHighTime = r.time;
        m_lastLow      = r.low;  m_lastLowTime  = r.time;
        return;
    }

    if(m_dirUp)
    {
        if(r.high > m_ext) { m_ext = r.high; m_extTime = r.time; }
        else if(r.low <= m_ext - m_thresh)
        {
            // ZZ flips DOWN → swing HIGH confirmed at (m_ext, m_extTime)  →  BEAR signal
            // BOS  = Lower High (bearish continuation):  m_ext < m_lastHigh
            // ChoCh = Higher High (bull structure, flip = reversal): m_ext >= m_lastHigh
            bool isBOS = (m_lastHigh > 0 && m_ext < m_lastHigh);
            AddBreak(m_extTime, m_ext, r.time, false, isBOS, m_lastLowTime);
            m_lastHigh = m_ext; m_lastHighTime = m_extTime;
            m_dirUp    = false;
            m_ext      = r.low; m_extTime = r.time;
        }
    }
    else
    {
        if(r.low < m_ext) { m_ext = r.low; m_extTime = r.time; }
        else if(r.high >= m_ext + m_thresh)
        {
            // ZZ flips UP → swing LOW confirmed at (m_ext, m_extTime)  →  BULL signal
            // BOS  = Higher Low (bullish continuation): m_ext > m_lastLow
            // ChoCh = Lower  Low (bear structure, flip = reversal): m_ext <= m_lastLow
            bool isBOS = (m_lastLow > 0 && m_ext > m_lastLow);
            AddBreak(m_extTime, m_ext, r.time, true, isBOS, m_lastHighTime);
            m_lastLow = m_ext; m_lastLowTime = m_extTime;
            m_dirUp   = true;
            m_ext     = r.high; m_extTime = r.time;
        }
    }
}

void CH1PivotTracker::ScanAll()
{
    m_breakCount = 0;
    m_ext        = 0;
    m_lastHigh   = 0;
    m_lastLow    = 0;

    int bars = Bars(_Symbol, PERIOD_H1);
    if(bars <= 0) return;

    MqlRates h1[];
    ArraySetAsSeries(h1, true);
    int copied = CopyRates(_Symbol, PERIOD_H1, 0, bars, h1);
    if(copied <= 0) return;

    for(int i = copied - 1; i >= 0; i--)   // oldest → newest
        ProcessBar(h1[i]);

    m_lastBar = (copied > 0) ? h1[0].time : 0;
}

void CH1PivotTracker::Update()
{
    datetime now[];
    if(CopyTime(_Symbol, PERIOD_H1, 0, 1, now) <= 0) return;
    if(now[0] == m_lastBar) return;

    MqlRates h1[];
    ArraySetAsSeries(h1, true);
    int copied = CopyRates(_Symbol, PERIOD_H1, 0, 30, h1);
    if(copied <= 0) return;

    // Find first bar newer than m_lastBar (oldest-to-newest scan)
    for(int i = copied - 1; i >= 0; i--)
    {
        if(h1[i].time > m_lastBar)
            ProcessBar(h1[i]);
    }
    m_lastBar = h1[0].time;
}

bool CH1PivotTracker::GetBreakAt(int idx,
                                  datetime &swingTime, double &price,
                                  datetime &breakTime, bool &isUp, bool &isBOS,
                                  datetime &oppTime) const
{
    if(idx < 0 || idx >= m_breakCount) return false;
    swingTime = m_breaks[idx].swingTime;
    price     = m_breaks[idx].price;
    breakTime = m_breaks[idx].breakTime;
    isUp      = m_breaks[idx].isUp;
    isBOS     = m_breaks[idx].isBOS;
    oppTime   = m_breaks[idx].oppTime;
    return true;
}

// Swing HIGHS are stored where isUp==false (BEAR signals = price peaked there)
double CH1PivotTracker::GetNearestSwingAbove(double p) const
{
    double best = 0;
    for(int i = m_breakCount - 1; i >= 0 && i >= m_breakCount - 300; i--)
        if(!m_breaks[i].isUp && m_breaks[i].price > p)
            if(best == 0 || m_breaks[i].price < best) best = m_breaks[i].price;
    return best;
}

// Swing LOWS are stored where isUp==true (BULL signals = price bottomed there)
double CH1PivotTracker::GetNearestSwingBelow(double p) const
{
    double best = 0;
    for(int i = m_breakCount - 1; i >= 0 && i >= m_breakCount - 300; i--)
        if(m_breaks[i].isUp && m_breaks[i].price < p)
            if(best == 0 || m_breaks[i].price > best) best = m_breaks[i].price;
    return best;
}

double CH1PivotTracker::GetFurthestSwingAbove(double p) const
{
    double best = 0;
    for(int i = m_breakCount - 1; i >= 0 && i >= m_breakCount - 300; i--)
        if(!m_breaks[i].isUp && m_breaks[i].price > p)
            if(best == 0 || m_breaks[i].price > best) best = m_breaks[i].price;
    return best;
}

double CH1PivotTracker::GetFurthestSwingBelow(double p) const
{
    double best = 0;
    for(int i = m_breakCount - 1; i >= 0 && i >= m_breakCount - 300; i--)
        if(m_breaks[i].isUp && m_breaks[i].price < p)
            if(best == 0 || m_breaks[i].price < best) best = m_breaks[i].price;
    return best;
}

//──────────────────────────────────────────────────────────────────
//  Signal record — for post-test chart repaint
//──────────────────────────────────────────────────────────────────

struct SSignalRec
{
    datetime t;
    double   price;
    double   obTop;
    double   obBottom;
    bool     isUp;
    bool     isBOS;
    bool     isCTR;
};

//──────────────────────────────────────────────────────────────────
//  Globals
//──────────────────────────────────────────────────────────────────

CMTFEngine      g_mtf;       // H4 bias + H4 swing TP targets + OB display
CH1PivotTracker g_h1zz;      // H1 pip-threshold ZigZag — entry signal source
CTradeManager   g_mgr;
CJournal        g_journal;

SBreakSlot    g_bull;
SBreakSlot    g_bear;

int         g_lastBreakIdx = 0;    // last H1 ZZ break we processed
datetime    g_lastH1Bar    = 0;    // new-H1-bar detection
SSignalRec  g_sigs[];              // stored signals for post-test chart
int         g_sigCount     = 0;

//──────────────────────────────────────────────────────────────────
//  Pip helpers
//──────────────────────────────────────────────────────────────────

double PipSz()  { return EA_PipSize(); }
double Sprd()   { return EA_Spread(); }

//──────────────────────────────────────────────────────────────────
//  FindOBZone
//  Scan H1 bars between oppTime and breakTime for the last candle
//  in the opposing direction — that is the Order Block candle.
//  Populates obTop/obBottom as the body (open/close range).
//──────────────────────────────────────────────────────────────────

bool FindOBZone(bool isBull, datetime oppTime, datetime breakTime,
                double &obTop, double &obBottom)
{
    MqlRates r[];
    ArraySetAsSeries(r, true);
    // Copy bars from oppTime up to breakTime on H1
    int n = CopyRates(_Symbol, PERIOD_H1, oppTime, breakTime, r);
    if(n < 2) return false;

    for(int i = 0; i < n && i < InpOBLookback; i++)
    {
        double body = r[i].close - r[i].open;
        if(isBull && body < 0)           // bull entry → last bearish candle
        {
            obTop    = MathMax(r[i].open, r[i].close);
            obBottom = MathMin(r[i].open, r[i].close);
            return true;
        }
        if(!isBull && body > 0)          // bear entry → last bullish candle
        {
            obTop    = MathMax(r[i].open, r[i].close);
            obBottom = MathMin(r[i].open, r[i].close);
            return true;
        }
    }
    return false;
}

//──────────────────────────────────────────────────────────────────
//  EstimateOBZone
//  No textbook OB → use Fib 38.2–50% retrace of the impulse
//──────────────────────────────────────────────────────────────────

void EstimateOBZone(bool isBull, double impulseLow, double impulseHigh,
                    double &obTop, double &obBottom)
{
    double rng = impulseHigh - impulseLow;
    if(isBull)
    {
        obTop    = impulseHigh - rng * 0.382;
        obBottom = impulseHigh - rng * 0.500;
    }
    else
    {
        obTop    = impulseLow  + rng * 0.500;
        obBottom = impulseLow  + rng * 0.382;
    }
}

//──────────────────────────────────────────────────────────────────
//  FindTPs
//  TP1 = nearest H1 swing in break direction beyond entry + minRR×SL
//  TP2 = H4 swing (or furthest H1 if H4 not found)
//  Returns false if no qualifying TP found.
//──────────────────────────────────────────────────────────────────

bool FindTPs(bool isBull, double entry, double sl, double minRR,
             double &tp1, double &tp2)
{
    double slDist = MathAbs(entry - sl);
    if(slDist < _Point) return false;

    double minTP = isBull ? entry + minRR * slDist
                          : entry - minRR * slDist;

    // TP1: nearest H1 ZZ swing beyond minRR distance
    tp1 = isBull ? g_h1zz.GetNearestSwingAbove(minTP)
                 : g_h1zz.GetNearestSwingBelow(minTP);

    // Fallback: nearest H4 structural swing
    if(tp1 == 0)
        tp1 = isBull ? g_mtf.GetH4NearestSwingAbove(minTP)
                     : g_mtf.GetH4NearestSwingBelow(minTP);

    if(tp1 == 0) return false;

    // Validate TP1 RR
    if(MathAbs(tp1 - entry) / slDist < minRR) return false;

    // Validate TP1 absolute distance
    if(MathAbs(tp1 - entry) / PipSz() < InpMinTP2Pips) return false;

    // TP2: furthest H4 swing beyond TP1
    tp2 = isBull ? g_mtf.GetH4FurthestSwingAbove(tp1)
                 : g_mtf.GetH4FurthestSwingBelow(tp1);

    // Fallback: furthest H1 ZZ swing beyond TP1
    if(tp2 == 0 || (isBull && tp2 <= tp1) || (!isBull && tp2 >= tp1))
        tp2 = isBull ? g_h1zz.GetFurthestSwingAbove(tp1)
                     : g_h1zz.GetFurthestSwingBelow(tp1);

    // If still nothing, TP2 = TP1 (single-target mode)
    if(tp2 == 0 || (isBull && tp2 <= tp1) || (!isBull && tp2 >= tp1))
        tp2 = tp1;

    return true;
}

//──────────────────────────────────────────────────────────────────
//  SendOrder
//  Sends a limit or market order. Returns ticket on success, 0 on fail.
//──────────────────────────────────────────────────────────────────

ulong SendOrder(bool isBull, bool market,
                double entry, double sl, double tp, double lots,
                datetime expiry, string comment)
{
    MqlTradeRequest req = {};
    MqlTradeResult  res = {};
    req.symbol    = _Symbol;
    req.volume    = lots;
    req.price     = SMCEA_NormalizePrice(entry);
    req.sl        = SMCEA_NormalizePrice(sl);
    req.tp        = SMCEA_NormalizePrice(tp);
    req.magic     = InpMagic;
    req.comment   = comment;
    req.deviation = 10;

    if(market)
    {
        req.action = TRADE_ACTION_DEAL;
        req.type   = isBull ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
    }
    else
    {
        req.action     = TRADE_ACTION_PENDING;
        req.type       = isBull ? ORDER_TYPE_BUY_LIMIT : ORDER_TYPE_SELL_LIMIT;
        req.type_time  = ORDER_TIME_SPECIFIED;
        req.expiration = expiry;
    }

    if(!SMCEA_CheckMinStops(req.price, req.sl, req.tp))
    {
        PrintFormat("V1 SendOrder: min stops not met  entry=%.5f sl=%.5f tp=%.5f",
                    entry, sl, tp);
        return 0;
    }

    if(!OrderSend(req, res))
    {
        PrintFormat("V1 SendOrder FAILED  retcode=%d  err=%d", res.retcode, GetLastError());
        return 0;
    }
    if(res.retcode != TRADE_RETCODE_PLACED && res.retcode != TRADE_RETCODE_DONE)
    {
        PrintFormat("V1 SendOrder retcode=%d (not placed/done)", res.retcode);
        return 0;
    }
    return res.order;
}

//──────────────────────────────────────────────────────────────────
//  PlaceOrder
//  Builds entry geometry, validates RR, sends order,
//  registers with CTradeManager.
//  marketMode=true  → market order at current price
//  marketMode=false → limit at OB midpoint
//──────────────────────────────────────────────────────────────────

bool PlaceOrder(SBreakSlot &slot, bool marketMode)
{
    if(Sprd() > InpMaxSpreadPips)
    {
        PrintFormat("V1 PlaceOrder: spread %.1f > max %.1f  skipping",
                    Sprd(), InpMaxSpreadPips);
        return false;
    }

    bool isBull = slot.isBull;

    // Entry price
    double entry;
    if(marketMode)
    {
        entry = isBull ? SymbolInfoDouble(_Symbol, SYMBOL_ASK)
                       : SymbolInfoDouble(_Symbol, SYMBOL_BID);
    }
    else
    {
        // Limit inside OB — add buffer from the far edge inward
        double obMid = (slot.obTop + slot.obBottom) * 0.5;
        entry = SMCEA_NormalizePrice(obMid);

        // Verify price hasn't already moved past the OB zone
        double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
        double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
        if(isBull && ask <= entry + InpOBBufferPips * PipSz())
        {
            // Price already at/below our limit — use market
            entry      = ask;
            marketMode = true;
        }
        else if(!isBull && bid >= entry - InpOBBufferPips * PipSz())
        {
            entry      = bid;
            marketMode = true;
        }
    }
    entry = SMCEA_NormalizePrice(entry);

    // SL: beyond OB edge + buffer
    double slRaw = isBull ? slot.obBottom - InpSLBufferPips * PipSz()
                          : slot.obTop    + InpSLBufferPips * PipSz();
    double sl    = SMCEA_NormalizePrice(slRaw);

    double slPips = MathAbs(entry - sl) / PipSz();
    if(slPips < InpMinSLPips)
    {
        PrintFormat("V1 PlaceOrder: SL %.1f pips < min %.1f  skipping", slPips, InpMinSLPips);
        return false;
    }
    // Enforce broker minimum stop level
    double brokerMinPips = (double)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL)
                           * _Point / PipSz();
    if(slPips < brokerMinPips)
    {
        PrintFormat("V1 PlaceOrder: SL %.1f pips < broker min %.1f", slPips, brokerMinPips);
        return false;
    }

    // Risk params
    double riskPct = slot.isCounterTrend ? InpCounterRiskPct : InpRiskPct;
    double minRR   = slot.isCounterTrend ? InpCounterMinRR   : InpMinRR;

    // TPs
    double tp1, tp2;
    if(!FindTPs(isBull, entry, sl, minRR, tp1, tp2))
    {
        PrintFormat("V1 PlaceOrder: no valid TP at minRR=%.1f  skipping", minRR);
        return false;
    }

    // Position size and capacity checks
    if(isBull  && g_mgr.CountByDirection(true)  >= InpMaxBuys)  return false;
    if(!isBull && g_mgr.CountByDirection(false) >= InpMaxSells) return false;
    if(g_mgr.IsOBAlreadyTraded(slot.breakTime))                 return false;

    // 2-slot lots split: 60% to TP1, 40% to TP2
    double totalLots = SMCEA_CalcLots(riskPct, slPips);
    if(totalLots <= 0) return false;

    double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
    double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
    int    lsDig   = (int)MathRound(-MathLog10(lotStep));
    double lot1    = NormalizeDouble(MathFloor(totalLots * 0.60 / lotStep) * lotStep, lsDig);
    double lot2    = NormalizeDouble(MathMax(totalLots - lot1, minLot), lsDig);
    lot1           = MathMax(lot1, minLot);

    datetime expiry = TimeCurrent() + (datetime)(InpPendingExpiryH * 3600);
    string   dir    = isBull ? "BUY" : "SELL";
    string   sig    = StringFormat("%s%s %s",
                          slot.isBOS ? "BOS" : "ChoCh",
                          slot.isCounterTrend ? "[CTR]" : "",
                          marketMode ? "MKT" : "LMT");

    bool anyPlaced = false;

    // Build common SSetup fields once — shared across both slots
    SSetup s1;
    s1.obTime      = slot.breakTime;
    s1.obTF        = PERIOD_H1;
    s1.isBull      = isBull;
    s1.type        = marketMode ? SETUP_CHOCH_MKT : SETUP_OB_LIMIT;
    s1.entryPrice  = entry;
    s1.sl          = sl;
    s1.lots        = lot1;
    s1.slotId      = 1;
    s1.score       = slot.isCounterTrend ? 40 : 70;
    s1.placed      = TimeCurrent();
    s1.expiry      = expiry;
    s1.marketEntry = marketMode;
    s1.detected    = slot.breakTime;
    s1.h4Bias      = g_mtf.GetH4Trend();
    s1.h1Trend     = g_mtf.GetH1Trend();
    s1.htfBias     = s1.h4Bias;
    s1.session     = EA_SessionName();
    s1.obHigh      = slot.obTop;
    s1.obLow       = slot.obBottom;
    s1.spreadPips  = Sprd();
    s1.reason      = sig;
    s1.tp1         = tp1;
    s1.tp2         = tp1;   // slot 1 exits fully at TP1
    s1.tp3         = tp1;

    // Slot 1 → TP1
    ulong t1 = SendOrder(isBull, marketMode, entry, sl, tp1, lot1, expiry, "V1|s1|" + sig);
    if(t1 > 0)
    {
        s1.ticket = t1;
        if(marketMode) s1.filled = TimeCurrent();
        g_mgr.AddSetup(s1);
        g_journal.LogOrderPlaced(s1);
        anyPlaced        = true;
        slot.limitTicket = t1;
        slot.limitPlaced = true;
    }

    // Slot 2 → TP2 (only if TP2 is meaningfully further than TP1)
    if(MathAbs(tp2 - tp1) / PipSz() > 10.0)
    {
        ulong t2 = SendOrder(isBull, marketMode, entry, sl, tp2, lot2, expiry, "V1|s2|" + sig);
        if(t2 > 0)
        {
            SSetup s2  = s1;    // copy all common fields from s1
            s2.ticket  = t2;
            s2.lots    = lot2;
            s2.slotId  = 2;
            s2.tp1     = tp1;
            s2.tp2     = tp2;
            s2.tp3     = tp2;
            if(marketMode) s2.filled = TimeCurrent();
            g_mgr.AddSetup(s2);
            g_journal.LogOrderPlaced(s2);
        }
    }

    if(anyPlaced)
        PrintFormat("V1 %s %s  entry=%.5f  sl=%.5f  TP1=%.5f  TP2=%.5f  lots=%.2f+%.2f",
                    dir, sig, entry, sl, tp1, tp2, lot1, lot2);

    return anyPlaced;
}

//──────────────────────────────────────────────────────────────────
//  _DrawArrowOnChart — paint one signal on a specific chart ID.
//  Called live (cid = ChartID()) and post-test (cid = new chart).
//──────────────────────────────────────────────────────────────────

void _DrawArrowOnChart(long cid, const SSignalRec &s)
{
    string name = StringFormat("V1_arr_%d_%s", (int)s.t, s.isUp ? "U" : "D");
    string lbl  = StringFormat("V1_lbl_%d_%s", (int)s.t, s.isUp ? "U" : "D");
    ObjectDelete(cid, name);
    ObjectDelete(cid, lbl);

    double pip = PipSz();

    // Arrow anchors to the OB entry level on the M5 candle at breakTime.
    // For a bull limit: entry approaches obTop from below → arrow just below obBottom.
    // For a bear limit: entry approaches obBottom from above → arrow just above obTop.
    // This shows exactly where the limit order will sit on the M5 chart.
    double obMid   = (s.obTop + s.obBottom) * 0.5;
    double entryLvl = (s.obTop > 0 && s.obBottom > 0)
                    ? (s.isUp ? s.obBottom - 2.0 * pip   // bull arrow below OB
                              : s.obTop    + 2.0 * pip)  // bear arrow above OB
                    : s.price;   // fallback: no OB stored

    // Find the M5 candle closest to breakTime for time accuracy
    MqlRates bar[];
    ArraySetAsSeries(bar, true);
    datetime barTime = s.t;
    if(CopyRates(_Symbol, _Period, s.t, s.t + PeriodSeconds(_Period), bar) > 0)
        barTime = bar[0].time;   // snap to exact M5 bar open time

    double arrowPrice = entryLvl;
    double textPrice  = s.isUp ? arrowPrice - 2.0 * pip : arrowPrice + 2.0 * pip;

    color clr = s.isUp
              ? (s.isCTR ? clrDodgerBlue : clrBlue)
              : (s.isCTR ? clrOrangeRed  : clrRed);

    ObjectCreate(cid, name, s.isUp ? OBJ_ARROW_UP : OBJ_ARROW_DOWN,
                 0, barTime, arrowPrice);
    ObjectSetInteger(cid, name, OBJPROP_COLOR,      clr);
    ObjectSetInteger(cid, name, OBJPROP_WIDTH,      4);
    ObjectSetInteger(cid, name, OBJPROP_SELECTABLE, false);

    string txt = StringFormat("%s%s",
                              s.isBOS ? "BOS" : "ChoCh",
                              s.isCTR ? "[C]" : "");
    ObjectCreate(cid, lbl, OBJ_TEXT, 0, barTime, textPrice);
    ObjectSetString (cid, lbl, OBJPROP_TEXT,      txt);
    ObjectSetInteger(cid, lbl, OBJPROP_COLOR,     clr);
    ObjectSetInteger(cid, lbl, OBJPROP_FONTSIZE,  8);
    ObjectSetInteger(cid, lbl, OBJPROP_ANCHOR,
                     s.isUp ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
    ObjectSetInteger(cid, lbl, OBJPROP_SELECTABLE, false);
}

//──────────────────────────────────────────────────────────────────
//  DrawSignalArrow — store signal + draw on live/visual chart.
//  Uses ChartID() so it works in both visual tester and live charts.
//──────────────────────────────────────────────────────────────────

void DrawSignalArrow(bool isUp, bool isBOS, bool isCounterTrend,
                     datetime breakTime, double breakLevel,
                     double obTop, double obBottom)
{
    // Store for post-test repaint
    int cap = ArraySize(g_sigs);
    if(g_sigCount >= cap)
        ArrayResize(g_sigs, cap + 200);

    g_sigs[g_sigCount].t         = breakTime;
    g_sigs[g_sigCount].price     = breakLevel;
    g_sigs[g_sigCount].obTop     = obTop;
    g_sigs[g_sigCount].obBottom  = obBottom;
    g_sigs[g_sigCount].isUp      = isUp;
    g_sigs[g_sigCount].isBOS     = isBOS;
    g_sigs[g_sigCount].isCTR     = isCounterTrend;
    g_sigCount++;

    // Draw on the REAL chart — ChartID() works in visual tester;
    // in non-visual tester it returns 0 which is the tester chart
    // (visible in the Charts tab after the run).
    _DrawArrowOnChart(ChartID(), g_sigs[g_sigCount - 1]);
    ChartRedraw(ChartID());

    PrintFormat("V1 Signal #%d: %s %s%s  at %s  price=%.5f",
                g_sigCount,
                isUp ? "BULL" : "BEAR",
                isBOS ? "BOS" : "ChoCh",
                isCounterTrend ? "[CTR]" : "",
                TimeToString(breakTime, TIME_DATE|TIME_MINUTES),
                breakLevel);
}

//──────────────────────────────────────────────────────────────────
//  _SlotFill — fills a break slot and fires the first order.
//  Called from ProcessBreak via if/else to avoid ternary reference.
//──────────────────────────────────────────────────────────────────

void _SlotFill(SBreakSlot &slot,
               bool isUp, bool isBOS, bool isCounterTrend,
               datetime breakTime, double breakLevel, datetime oppTime,
               double obTop, double obBottom, bool hasOB)
{
    // Cancel any still-pending limit from a previous break on this side
    if(slot.active && slot.limitPlaced && slot.limitTicket > 0)
    {
        if(OrderSelect(slot.limitTicket))
        {
            MqlTradeRequest rq = {}; MqlTradeResult rs = {};
            rq.action = TRADE_ACTION_REMOVE;
            rq.order  = slot.limitTicket;
            if(!OrderSend(rq, rs))
                PrintFormat("V1 ProcessBreak: cancel limit failed ret=%d", rs.retcode);
            else
                PrintFormat("V1 ProcessBreak: superseded old limit ticket=%d", slot.limitTicket);
        }
    }

    slot.Reset();
    slot.active          = true;
    slot.isBull          = isUp;
    slot.isCounterTrend  = isCounterTrend;
    slot.isBOS           = isBOS;
    slot.breakTime       = breakTime;
    slot.breakLevel      = breakLevel;
    slot.oppTime         = oppTime;
    slot.obTop           = obTop;
    slot.obBottom        = obBottom;
    slot.hasOB           = hasOB;
    slot.h1BarsAtDetect  = Bars(_Symbol, PERIOD_H1);

    PrintFormat("V1 %s %s %s  break=%.5f  OB %.5f–%.5f (%s)",
                isUp ? "BULL" : "BEAR",
                isBOS ? "BOS" : "ChoCh",
                isCounterTrend ? "[CTR]" : "[WITH]",
                breakLevel, obBottom, obTop,
                hasOB ? "real" : "est");

    // Try limit first; auto-switches to market inside PlaceOrder if price is past zone
    PlaceOrder(slot, false);
}

//──────────────────────────────────────────────────────────────────
//  ProcessBreak
//  New H1 BOS/ChoCh detected. Find OB zone and place first order.
//──────────────────────────────────────────────────────────────────

void ProcessBreak(bool isUp, bool isBOS,
                  datetime breakTime, double breakLevel, datetime oppTime)
{
    int  h4             = g_mtf.GetH4Trend();
    bool isCounterTrend = (h4 != 0 &&
                          ((isUp && h4 == -1) || (!isUp && h4 == 1)));

    // Impulse origin price: low of opposite pivot bar (bull) or high (bear)
    double oppPrice = 0;
    MqlRates opp[];
    ArraySetAsSeries(opp, true);
    if(CopyRates(_Symbol, PERIOD_H1, oppTime,
                 oppTime + PeriodSeconds(PERIOD_H1), opp) > 0)
        oppPrice = isUp ? opp[0].low : opp[0].high;
    if(oppPrice == 0)
        oppPrice = isUp ? breakLevel * 0.995 : breakLevel * 1.005;

    // Find OB zone
    double obTop, obBottom;
    bool hasOB = FindOBZone(isUp, oppTime, breakTime, obTop, obBottom);
    if(!hasOB)
    {
        if(isUp) EstimateOBZone(isUp, oppPrice, breakLevel, obTop, obBottom);
        else     EstimateOBZone(isUp, breakLevel, oppPrice, obTop, obBottom);
    }

    // ── Arrows-only mode: just mark the signal on the chart, no order ──
    if(InpArrowsOnly)
    {
        DrawSignalArrow(isUp, isBOS, isCounterTrend,
                        breakTime, breakLevel, obTop, obBottom);
        return;
    }

    // Fill the appropriate directional slot (MQL5 forbids reference-to-ternary)
    if(isUp) _SlotFill(g_bull, isUp, isBOS, isCounterTrend,
                       breakTime, breakLevel, oppTime, obTop, obBottom, hasOB);
    else     _SlotFill(g_bear, isUp, isBOS, isCounterTrend,
                       breakTime, breakLevel, oppTime, obTop, obBottom, hasOB);
}

//──────────────────────────────────────────────────────────────────
//  CheckNewBreaks
//──────────────────────────────────────────────────────────────────

void CheckNewBreaks()
{
    int total = g_h1zz.GetBreakCount();
    if(total <= g_lastBreakIdx) return;

    for(int i = g_lastBreakIdx; i < total; i++)
    {
        datetime swingTime, breakTime, oppTime;
        double   price;
        bool     isUp, isBOS;
        if(!g_h1zz.GetBreakAt(i, swingTime, price, breakTime, isUp, isBOS, oppTime))
            continue;
        ProcessBreak(isUp, isBOS, breakTime, price, oppTime);
    }

    g_lastBreakIdx = total;
}

//──────────────────────────────────────────────────────────────────
//  CheckFallback
//  If a pending limit hasn't filled after InpFallbackBars H1 bars,
//  cancel it and switch to a market order.
//──────────────────────────────────────────────────────────────────

void CheckFallback(SBreakSlot &slot)
{
    if(!slot.active || !slot.limitPlaced || slot.limitTicket == 0) return;

    int currentH1 = Bars(_Symbol, PERIOD_H1);
    int elapsed   = slot.h1BarsAtDetect - currentH1;   // negative = bars since detect
    if(elapsed > -InpFallbackBars) return;              // not enough time yet

    // Check the limit is still pending (not filled, not expired)
    if(!OrderSelect(slot.limitTicket))
    {
        // Already gone (filled or expired) — deactivate slot
        slot.active = false;
        return;
    }

    // Still pending — cancel and go market
    MqlTradeRequest rq = {}; MqlTradeResult rs = {};
    rq.action = TRADE_ACTION_REMOVE;
    rq.order  = slot.limitTicket;
    if(!OrderSend(rq, rs))
        PrintFormat("V1 Fallback: cancel limit %d failed ret=%d", slot.limitTicket, rs.retcode);
    else
        PrintFormat("V1 Fallback: cancelled limit %d after %d H1 bars — trying market",
                    slot.limitTicket, -elapsed);

    slot.limitPlaced = false;
    slot.limitTicket = 0;

    // Attempt market entry — validate price is still on the right side of break level
    double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
    double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
    bool stillValid = slot.isBull ? (bid > slot.breakLevel)
                                  : (ask < slot.breakLevel);
    if(!stillValid)
    {
        PrintFormat("V1 Fallback: price reversed through break level — aborting");
        slot.active = false;
        return;
    }

    PlaceOrder(slot, true);   // true = market mode
}

//──────────────────────────────────────────────────────────────────
//  OnInit
//──────────────────────────────────────────────────────────────────

int OnInit()
{
    g_mtf.Init(10, 30);
    g_mtf.SetH1OBDisplayLimit(3);
    g_mgr.Init(InpMagic, &g_journal);
    g_journal.Init("VECTOR001_trades.csv", "VECTOR001_events.csv", true);

    g_bull.Reset();
    g_bear.Reset();
    g_lastBreakIdx = 0;
    g_lastH1Bar    = 0;
    g_sigCount     = 0;
    ArrayResize(g_sigs, 500);

    // Full initial calculation
    int total = Bars(_Symbol, _Period);
    g_mtf.Calculate(total, 0);        // H4 bias + OBs

    g_h1zz.Init(InpH1ThreshPips);    // pip-threshold ZZ — must match Step 1 research
    g_h1zz.ScanAll();                 // scan all H1 history
    g_lastBreakIdx = g_h1zz.GetBreakCount();   // skip historical signals

    PrintFormat("VECTOR001 v1.0 ready  H4=%+d  thresh=%.0fpip  H1signals(hist)=%d",
                g_mtf.GetH4Trend(), InpH1ThreshPips, g_lastBreakIdx);
    return INIT_SUCCEEDED;
}

//──────────────────────────────────────────────────────────────────
//  OnDeinit
//──────────────────────────────────────────────────────────────────

void OnDeinit(const int reason)
{
    g_journal.Flush();

    bool isTester = (bool)MQLInfoInteger(MQL_TESTER);
    bool isOptim  = (bool)MQLInfoInteger(MQL_OPTIMIZATION);

    // Non-visual tester: arrows on ChartID()=0 are visible in the
    // Strategy Tester "Charts" tab after the run — no extra work needed.
    // ChartOpen() cannot be called from the tester core thread (err 4202).
    if(InpArrowsOnly && isTester && !isOptim)
        PrintFormat("V1 OnDeinit: %d signals drawn — open the Charts tab in Strategy Tester to view",
                    g_sigCount);

    // Live chart: clean up arrow objects when EA is removed
    if(!isTester)
        ObjectsDeleteAll(0, "V1_arr");
}

//──────────────────────────────────────────────────────────────────
//  OnTick
//──────────────────────────────────────────────────────────────────

void OnTick()
{
    int total = Bars(_Symbol, _Period);

    // New H1 bar detection
    datetime h1t[];
    bool newH1 = false;
    if(CopyTime(_Symbol, PERIOD_H1, 0, 1, h1t) > 0 && h1t[0] != g_lastH1Bar)
    {
        newH1       = true;
        g_lastH1Bar = h1t[0];
    }

    if(newH1)
    {
        g_mtf.Calculate(total, 1);   // H4 bias + OB incremental update
        g_h1zz.Update();             // H1 ZZ incremental — fires new break signals
        CheckNewBreaks();
        CheckFallback(g_bull);
        CheckFallback(g_bear);
    }

    // Trade management runs every tick (precise TP/BE/trail execution)
    g_mgr.ManagePendingOrders();
    g_mgr.ManageOpenPositions(InpBEBufferPips, InpUseTrailing, InpTrailPips);

    // Redraw chart on new H1 bar only
    if(newH1 && InpShowPanel)
        g_mtf.Draw(InpShowPanel, false, InpShowH1OBs, InpShowH4OBs, false);
}

//──────────────────────────────────────────────────────────────────
//  OnTradeTransaction — journal fills and deactivate slot
//──────────────────────────────────────────────────────────────────

void OnTradeTransaction(const MqlTradeTransaction &trans,
                        const MqlTradeRequest     &req,
                        const MqlTradeResult      &res)
{
    if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
    if(trans.deal_type != DEAL_TYPE_BUY &&
       trans.deal_type != DEAL_TYPE_SELL) return;

    for(int i = 0; i < g_mgr.Count(); i++)
    {
        SSetup s;
        if(!g_mgr.GetSetup(i, s)) continue;
        if(s.ticket != trans.order)  continue;
        g_mgr.SetFilled(i, TimeCurrent());
        g_journal.LogOrderFilled(s.ticket, s.isBull, trans.price, 0);
        // Clear the break slot so direction is free for a new signal
        if(s.isBull) { g_bull.limitPlaced = false; g_bull.active = false; }
        else         { g_bear.limitPlaced = false; g_bear.active = false; }
        break;
    }
}
//+------------------------------------------------------------------+
