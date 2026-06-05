//+------------------------------------------------------------------+
//|                                             VECTOR80_Prototype.mq5 |
//|                                                                  |
//|  VECTOR80 ZZLines model-backed pivot EA prototype                |
//|                                                                  |
//|  Research basis:                                                 |
//|    research/vector80_sell_expanded_engine_config.json            |
//|    research/ZZLINES_CODE_READY_SELL_EXPANDED.md                  |
//|                                                                  |
//|  Validated OOS profile:                                          |
//|    2026-03-01 -> 2026-06-01                                      |
//|    42 signals, 36 hits, 85.7% precision                          |
//|    BUY  21 signals, 17 hits, 81.0%                               |
//|    SELL 21 signals, 19 hits, 90.5%                               |
//|                                                                  |
//|  Important: production inference requires exported model scores. |
//|  The EA supports external score CSV input. The heuristic mode is |
//|  only a plumbing/test fallback, not the validated model.          |
//+------------------------------------------------------------------+
#property strict
#property version   "1.000"
#property copyright "VECTOR research 2026-06"
#property description "VECTOR80 ZZLines model-backed pivot EA prototype"

#include <Trade/Trade.mqh>

//──────────────────────────────────────────────────────────────────
// Inputs
//──────────────────────────────────────────────────────────────────

enum ENUM_VECTOR80_SCORE_MODE
{
   SCORE_EXTERNAL_CSV = 0,
   SCORE_HEURISTIC_PROXY = 1
};

input group "=== Model / Signal ==="
input ENUM_VECTOR80_SCORE_MODE InpScoreMode       = SCORE_EXTERNAL_CSV;
input string  InpScoreFileCommon                  = "VECTOR80_model_scores.csv";
input int     InpScoreTimeShiftMin                = 180;     // broker time = research score time + this shift
input int     InpScoreTimeToleranceMin            = 5;       // small tolerance after fixed shift
input bool    InpDebugShiftSweep                  = true;
input int     InpDebugShiftSweepFromMin           = -360;
input int     InpDebugShiftSweepToMin             = 360;
input int     InpDebugShiftSweepStepMin           = 30;
input bool    InpAllowTrading                     = false;
input bool    InpDrawArrows                       = true;
input int     InpSameSideCooldownMin              = 30;
input int     InpEntryWindowBars                  = 2;       // pivot bar + this many M5 bars

input group "=== ZigZag Lines MTF ==="
input string          InpZZIndicatorName          = "Market\\ZigZag Lines MTF for MT5";
input ENUM_TIMEFRAMES InpSignalTF                 = PERIOD_M5;
input int             InpZZDepth                  = 12;
input int             InpZZDeviation              = 5;
input int             InpZZBackstep               = 3;
input int             InpZZTmpMaxBars             = 20000;
input int             InpZZIndPeriod              = 0;
input int             InpZZScanBars               = 300;

input group "=== Risk ==="
input double  InpRiskPct                          = 1.0;
input int     InpMagic                            = 20800080;
input int     InpMaxOpenPositions                 = 4;
input double  InpMaxSpreadPips                    = 2.5;
input int     InpSlippagePoints                   = 20;

input group "=== Engine Risk ==="
input double  InpBuyStopPips                      = 5.0;
input double  InpSellStopPips                     = 8.0;
input double  InpTargetR                          = 1.0;
input int     InpTimeoutMinutes                   = 120;

input group "=== Heuristic Proxy Test Mode ==="
input double  InpHeuristicLLThreshold             = 0.88;
input double  InpHeuristicHLThreshold             = 0.90;
input double  InpHeuristicHHThreshold             = 0.90;

input group "=== Logging ==="
input bool    InpUseCommonFiles                   = true;
input string  InpEventLogFile                     = "VECTOR80_events.csv";
input string  InpTradeLogFile                     = "VECTOR80_trades.csv";
input bool    InpDebugLogging                     = true;

//──────────────────────────────────────────────────────────────────
// Constants / globals
//──────────────────────────────────────────────────────────────────

#define ENGINE_COUNT 8

struct SEngine
{
   string id;
   string side;
   string label;
   string group_type;
   string group_key;
   string model_type;
   double threshold;
   double stop_pips;
   double target_r;
   int    timeout_min;
};

struct SPivot
{
   datetime time;
   double   price;
   string   side;     // HIGH / LOW
   string   label;    // HH / HL / LH / LL
};

struct SSignal
{
   bool     active;
   datetime signal_time;
   datetime pivot_time;
   string   engine_id;
   string   side;
   string   label;
   string   group_key;
   double   pivot_price;
   double   score;
   double   stop_pips;
   double   target_r;
   int      timeout_min;
};

struct SManagedPosition
{
   bool     active;
   ulong    ticket;
   string   engine_id;
   string   side;
   datetime entry_time;
   datetime pivot_time;
   double   entry_price;
   double   sl;
   double   tp;
   double   lots;
   int      timeout_min;
};

CTrade g_trade;
SEngine g_engines[ENGINE_COUNT];
SManagedPosition g_positions[32];

double   g_pip = 0.0001;
int      g_zz_handle = INVALID_HANDLE;
datetime g_last_bar = 0;
datetime g_last_buy_signal = 0;
datetime g_last_sell_signal = 0;
datetime g_last_pivot_time_seen = 0;

int g_event_handle = INVALID_HANDLE;
int g_trade_handle = INVALID_HANDLE;

long g_dbg_bars = 0;
long g_dbg_latest_pivots = 0;
long g_dbg_pivot_too_old = 0;
long g_dbg_group_matches = 0;
long g_dbg_cooldown_blocks = 0;
long g_dbg_score_missing = 0;
long g_dbg_threshold_blocks = 0;
long g_dbg_signals = 0;
int  g_dbg_min_pivot_shift = 999999;
int  g_dbg_max_pivot_shift = -1;

int  g_shift_values[];
long g_shift_matches[];

// Indicator handles for heuristic/context features.
int g_rsi_m5 = INVALID_HANDLE;
int g_stoch_m5 = INVALID_HANDLE;
int g_atr_m5 = INVALID_HANDLE;
int g_ema50_h1 = INVALID_HANDLE;
int g_ema200_h1 = INVALID_HANDLE;

//──────────────────────────────────────────────────────────────────
// Utility
//──────────────────────────────────────────────────────────────────

double Pip()
{
   if(_Digits == 3 || _Digits == 5)
      return _Point * 10.0;
   return _Point;
}

string TS(datetime t)
{
   return TimeToString(t, TIME_DATE | TIME_SECONDS);
}

bool IsNewBar()
{
   datetime t[1];
   if(CopyTime(_Symbol, InpSignalTF, 0, 1, t) != 1)
      return false;
   if(t[0] == g_last_bar)
      return false;
   g_last_bar = t[0];
   return true;
}

double SpreadPips()
{
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   return (ask - bid) / g_pip;
}

double NormalizePrice(double p)
{
   return NormalizeDouble(p, _Digits);
}

string SessionOf(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   int h = dt.hour;
   if(h >= 22 || h < 7) return "ASIAN";
   if(h >= 7 && h < 12) return "LONDON";
   if(h >= 12 && h < 17) return "LONDON_NY";
   if(h >= 17 && h < 22) return "NY";
   return "OFF";
}

double BufferValue(int handle, int buffer, int shift)
{
   double v[1];
   if(handle == INVALID_HANDLE)
      return 0.0;
   if(CopyBuffer(handle, buffer, shift, 1, v) != 1)
      return 0.0;
   return v[0];
}

double CloseValue(ENUM_TIMEFRAMES tf, int shift)
{
   double c[1];
   if(CopyClose(_Symbol, tf, shift, 1, c) != 1)
      return 0.0;
   return c[0];
}

int H1TrendDir()
{
   double ema50_now = BufferValue(g_ema50_h1, 0, 1);
   double ema50_old = BufferValue(g_ema50_h1, 0, 7);
   double close_h1 = CloseValue(PERIOD_H1, 1);
   if(ema50_now == 0.0 || ema50_old == 0.0 || close_h1 == 0.0)
      return 0;
   double slope_pips = (ema50_now - ema50_old) / g_pip;
   if(close_h1 > ema50_now && slope_pips > 1.0)
      return 1;
   if(close_h1 < ema50_now && slope_pips < -1.0)
      return -1;
   return 0;
}

string TradeContext(string label, datetime t)
{
   int trend = H1TrendDir();
   if(trend == 0)
      return "RANGE";
   if(trend > 0)
   {
      if(label == "HL") return "BUY_PULLBACK_UPTREND";
      if(label == "HH") return "BULL_CONTINUATION_HIGH";
      if(label == "LL") return "BULL_TREND_BREAK_LOW";
      if(label == "LH") return "WEAK_HIGH_IN_UPTREND";
   }
   if(label == "LH") return "SELL_PULLBACK_DOWNTREND";
   if(label == "LL") return "BEAR_CONTINUATION_LOW";
   if(label == "HH") return "BEAR_TREND_BREAK_HIGH";
   if(label == "HL") return "WEAK_LOW_IN_DOWNTREND";
   return "UNKNOWN";
}

string VolRegime()
{
   double atr = BufferValue(g_atr_m5, 0, 1) / g_pip;
   if(atr <= 0.0)
      return "UNKNOWN";

   int n = 100;
   double atrs[];
   ArraySetAsSeries(atrs, true);
   if(CopyBuffer(g_atr_m5, 0, 1, n, atrs) < n)
      return "UNKNOWN";

   int below = 0;
   for(int i = 0; i < n; i++)
      if(atrs[i] / g_pip <= atr)
         below++;
   double pct = (double)below / (double)n;
   if(pct < 0.33) return "LOW";
   if(pct < 0.67) return "NORMAL";
   return "HIGH";
}

//──────────────────────────────────────────────────────────────────
// Logging
//──────────────────────────────────────────────────────────────────

int FileFlags()
{
   int flags = FILE_READ | FILE_WRITE | FILE_CSV | FILE_SHARE_READ | FILE_ANSI;
   if(InpUseCommonFiles)
      flags |= FILE_COMMON;
   return flags;
}

void OpenLogs()
{
   bool new_events = !FileIsExist(InpEventLogFile, InpUseCommonFiles ? FILE_COMMON : 0);
   bool new_trades = !FileIsExist(InpTradeLogFile, InpUseCommonFiles ? FILE_COMMON : 0);
   g_event_handle = FileOpen(InpEventLogFile, FileFlags(), ',');
   if(g_event_handle != INVALID_HANDLE)
   {
      if(new_events)
      {
         FileWrite(g_event_handle, "time", "event", "engine_id", "side", "label", "group_key",
                   "pivot_time", "pivot_price", "score", "threshold", "note");
      }
      else FileSeek(g_event_handle, 0, SEEK_END);
   }

   g_trade_handle = FileOpen(InpTradeLogFile, FileFlags(), ',');
   if(g_trade_handle != INVALID_HANDLE)
   {
      if(new_trades)
      {
         FileWrite(g_trade_handle, "time", "event", "ticket", "engine_id", "side",
                   "entry_time", "entry_price", "sl", "tp", "lots", "pips", "note");
      }
      else FileSeek(g_trade_handle, 0, SEEK_END);
   }
}

void CloseLogs()
{
   if(g_event_handle != INVALID_HANDLE) { FileClose(g_event_handle); g_event_handle = INVALID_HANDLE; }
   if(g_trade_handle != INVALID_HANDLE) { FileClose(g_trade_handle); g_trade_handle = INVALID_HANDLE; }
}

void LogEvent(string event_type, const SSignal &sig, double threshold, string note)
{
   if(g_event_handle == INVALID_HANDLE)
      return;
   FileWrite(g_event_handle, TS(TimeCurrent()), event_type, sig.engine_id, sig.side, sig.label,
             sig.group_key, TS(sig.pivot_time), DoubleToString(sig.pivot_price, _Digits),
             DoubleToString(sig.score, 6), DoubleToString(threshold, 3), note);
   FileFlush(g_event_handle);
}

void LogDebug(string event_type, string note)
{
   if(!InpDebugLogging || g_event_handle == INVALID_HANDLE)
      return;
   FileWrite(g_event_handle, TS(TimeCurrent()), event_type, "", "", "", "",
             "", "", "", "", note);
   FileFlush(g_event_handle);
}

void InitShiftSweep()
{
   ArrayResize(g_shift_values, 0);
   ArrayResize(g_shift_matches, 0);
   if(!InpDebugShiftSweep || InpDebugShiftSweepStepMin <= 0)
      return;

   int from_min = InpDebugShiftSweepFromMin;
   int to_min = InpDebugShiftSweepToMin;
   if(to_min < from_min)
   {
      int tmp = from_min;
      from_min = to_min;
      to_min = tmp;
   }

   for(int s = from_min; s <= to_min; s += InpDebugShiftSweepStepMin)
   {
      int n = ArraySize(g_shift_values);
      ArrayResize(g_shift_values, n + 1);
      ArrayResize(g_shift_matches, n + 1);
      g_shift_values[n] = s;
      g_shift_matches[n] = 0;
   }
}

void DebugShiftSweep(string engine_id, datetime bar_time)
{
   if(!InpDebugShiftSweep || ArraySize(g_shift_values) <= 0)
      return;

   int flags = FILE_READ | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles)
      flags |= FILE_COMMON;
   int h = FileOpen(InpScoreFileCommon, flags, ',');
   if(h == INVALID_HANDLE)
      return;

   int tolerance_sec = MathMax(0, InpScoreTimeToleranceMin) * 60;
   while(!FileIsEnding(h))
   {
      string t = FileReadString(h);
      string e = FileReadString(h);
      string s = FileReadString(h);
      if(t == "time" || t == "" || e != engine_id)
         continue;
      datetime row_time = StringToTime(t);
      for(int i = 0; i < ArraySize(g_shift_values); i++)
      {
         datetime shifted_time = row_time + g_shift_values[i] * 60;
         int delta = (int)MathAbs((long)(shifted_time - bar_time));
         if(delta <= tolerance_sec)
            g_shift_matches[i]++;
      }
   }
   FileClose(h);
}

void LogTrade(string event_type, ulong ticket, string engine_id, string side, double entry,
              double sl, double tp, double lots, double pips, string note)
{
   if(g_trade_handle == INVALID_HANDLE)
      return;
   FileWrite(g_trade_handle, TS(TimeCurrent()), event_type, IntegerToString((long)ticket),
             engine_id, side, TS(TimeCurrent()), DoubleToString(entry, _Digits),
             DoubleToString(sl, _Digits), DoubleToString(tp, _Digits),
             DoubleToString(lots, 2), DoubleToString(pips, 1), note);
   FileFlush(g_trade_handle);
}

//──────────────────────────────────────────────────────────────────
// Engine config
//──────────────────────────────────────────────────────────────────

void SetEngine(int i, string id, string side, string label, string group_type,
               string group_key, string model_type, double threshold,
               double stop_pips, double target_r, int timeout_min)
{
   g_engines[i].id = id;
   g_engines[i].side = side;
   g_engines[i].label = label;
   g_engines[i].group_type = group_type;
   g_engines[i].group_key = group_key;
   g_engines[i].model_type = model_type;
   g_engines[i].threshold = threshold;
   g_engines[i].stop_pips = stop_pips;
   g_engines[i].target_r = target_r;
   g_engines[i].timeout_min = timeout_min;
}

void InitEngines()
{
   SetEngine(0, "BUY_LL_HGB_088", "BUY", "LL", "label", "LL",
             "HistGradientBoostingClassifier", 0.88, InpBuyStopPips, InpTargetR, InpTimeoutMinutes);
   SetEngine(1, "BUY_LL_HIGHVOL_RF_085", "BUY", "LL", "label_vol", "LL|HIGH",
             "RandomForestClassifier", 0.85, InpBuyStopPips, InpTargetR, InpTimeoutMinutes);
   SetEngine(2, "BUY_HL_HGB_090", "BUY", "HL", "label", "HL",
             "HistGradientBoostingClassifier", 0.90, InpBuyStopPips, InpTargetR, InpTimeoutMinutes);
   SetEngine(3, "SELL_label_session_vol_HH_LONDON_HIGH_rf_075", "SELL", "HH",
             "label_session_vol", "HH|LONDON|HIGH", "RandomForestClassifier",
             0.75, InpSellStopPips, InpTargetR, InpTimeoutMinutes);
   SetEngine(4, "SELL_label_HH_hgb_09", "SELL", "HH", "label", "HH",
             "HistGradientBoostingClassifier", 0.90, InpSellStopPips, InpTargetR, InpTimeoutMinutes);
   SetEngine(5, "SELL_label_trade_context_session_HH_BULL_CONTINUATION_HIGH_LONDON_hgb_096",
             "SELL", "HH", "label_trade_context_session", "HH|BULL_CONTINUATION_HIGH|LONDON",
             "HistGradientBoostingClassifier", 0.96, InpSellStopPips, InpTargetR, InpTimeoutMinutes);
   SetEngine(6, "SELL_label_trade_context_session_vol_HH_BULL_CONTINUATION_HIGH_LONDON_HIGH_rf_07",
             "SELL", "HH", "label_trade_context_session_vol",
             "HH|BULL_CONTINUATION_HIGH|LONDON|HIGH", "RandomForestClassifier",
             0.70, InpSellStopPips, InpTargetR, InpTimeoutMinutes);
   SetEngine(7, "SELL_label_trade_context_HH_BEAR_TREND_BREAK_HIGH_extra_07",
             "SELL", "HH", "label_trade_context", "HH|BEAR_TREND_BREAK_HIGH",
             "ExtraTreesClassifier", 0.70, InpSellStopPips, InpTargetR, InpTimeoutMinutes);
}

//──────────────────────────────────────────────────────────────────
// Score provider
//──────────────────────────────────────────────────────────────────

bool ExternalScore(datetime bar_time, string engine_id, double &score, datetime &matched_time)
{
   int flags = FILE_READ | FILE_CSV | FILE_ANSI;
   if(InpUseCommonFiles)
      flags |= FILE_COMMON;
   int h = FileOpen(InpScoreFileCommon, flags, ',');
   if(h == INVALID_HANDLE)
      return false;

   bool found = false;
   int best_delta = 2147483647;
   double best_score = 0.0;
   datetime best_time = 0;
   int tolerance_sec = MathMax(0, InpScoreTimeToleranceMin) * 60;
   while(!FileIsEnding(h))
   {
      string t = FileReadString(h);
      string e = FileReadString(h);
      string s = FileReadString(h);
      if(t == "time" || t == "")
         continue;
      datetime row_time = StringToTime(t);
      datetime shifted_time = row_time + InpScoreTimeShiftMin * 60;
      if(e != engine_id)
         continue;
      int delta = (int)MathAbs((long)(shifted_time - bar_time));
      if(delta == 0)
      {
         score = StringToDouble(s);
         matched_time = shifted_time;
         found = true;
         break;
      }
      if(tolerance_sec > 0 && delta <= tolerance_sec && delta < best_delta)
      {
         best_delta = delta;
         best_score = StringToDouble(s);
         best_time = shifted_time;
      }
   }
   if(!found && best_time > 0)
   {
      score = best_score;
      matched_time = best_time;
      found = true;
   }
   FileClose(h);
   return found;
}

double HeuristicScore(const SEngine &eng, const SPivot &pivot)
{
   double rsi = BufferValue(g_rsi_m5, 0, 1);
   double stoch_main = BufferValue(g_stoch_m5, 0, 1);
   double atr = BufferValue(g_atr_m5, 0, 1) / g_pip;
   string session = SessionOf(pivot.time);
   string vol = VolRegime();
   string ctx = TradeContext(pivot.label, pivot.time);

   double score = 0.50;
   if(eng.side == "BUY")
   {
      if(rsi < 35.0) score += 0.18;
      if(stoch_main < 25.0) score += 0.14;
      if(pivot.label == "LL") score += 0.10;
      if(vol == "HIGH" && eng.group_key == "LL|HIGH") score += 0.18;
      if(pivot.label == "HL" && rsi < 45.0) score += 0.12;
   }
   else
   {
      if(rsi > 65.0) score += 0.18;
      if(stoch_main > 75.0) score += 0.14;
      if(pivot.label == "HH") score += 0.10;
      if(session == "LONDON" && StringFind(eng.group_key, "LONDON") >= 0) score += 0.14;
      if(vol == "HIGH" && StringFind(eng.group_key, "HIGH") >= 0) score += 0.14;
      if(ctx == "BULL_CONTINUATION_HIGH" && StringFind(eng.group_key, "BULL_CONTINUATION_HIGH") >= 0) score += 0.18;
      if(ctx == "BEAR_TREND_BREAK_HIGH" && StringFind(eng.group_key, "BEAR_TREND_BREAK_HIGH") >= 0) score += 0.18;
   }
   if(atr <= 0.0) score -= 0.20;
   return MathMax(0.0, MathMin(0.99, score));
}

bool GetEngineScore(const SEngine &eng, const SPivot &pivot, datetime bar_time, double &score, string &note)
{
   score = 0.0;
   note = "";
   if(InpScoreMode == SCORE_EXTERNAL_CSV)
   {
      datetime matched_time = 0;
      if(ExternalScore(bar_time, eng.id, score, matched_time))
      {
         int delta_min = (int)MathAbs((long)(matched_time - bar_time)) / 60;
         note = StringFormat("external_score shifted_match=%s delta_min=%d shift_min=%d",
                             TS(matched_time), delta_min, InpScoreTimeShiftMin);
         return true;
      }
      note = "missing_external_score";
      return false;
   }
   score = HeuristicScore(eng, pivot);
   note = "heuristic_proxy_not_validated";
   return true;
}

//──────────────────────────────────────────────────────────────────
// Pivot intake
//──────────────────────────────────────────────────────────────────

bool IsTimestampLike(double v)
{
   return (v > 1500000000.0 && v < 2100000000.0);
}

bool LoadRecentPivots(SPivot &pivots[], int &count)
{
   count = 0;
   ArrayResize(pivots, 0);
   int n = MathMin(InpZZScanBars, Bars(_Symbol, InpSignalTF));
   if(n < 50 || g_zz_handle == INVALID_HANDLE)
      return false;

   double b0[], b1[], b4[];
   datetime times[];
   ArraySetAsSeries(b0, true);
   ArraySetAsSeries(b1, true);
   ArraySetAsSeries(b4, true);
   ArraySetAsSeries(times, true);
   if(CopyBuffer(g_zz_handle, 0, 0, n, b0) <= 0 ||
      CopyBuffer(g_zz_handle, 1, 0, n, b1) <= 0 ||
      CopyBuffer(g_zz_handle, 4, 0, n, b4) <= 0 ||
      CopyTime(_Symbol, InpSignalTF, 0, n, times) <= 0)
      return false;

   double last_high = 0.0;
   double last_low = 0.0;
   for(int i = n - 1; i >= 0; i--)
   {
      if(b0[i] == 0.0 || b4[i] == 0.0)
         continue;

      datetime pt = times[i];
      if(IsTimestampLike(b1[i]))
         pt = (datetime)b1[i];

      SPivot p;
      p.time = pt;
      p.price = b0[i];
      p.side = (b4[i] > 0.0) ? "HIGH" : "LOW";
      p.label = "";

      if(p.side == "HIGH")
      {
         p.label = (last_high > 0.0 && p.price > last_high) ? "HH" : "LH";
         last_high = p.price;
      }
      else
      {
         p.label = (last_low > 0.0 && p.price > last_low) ? "HL" : "LL";
         last_low = p.price;
      }

      int sz = ArraySize(pivots);
      ArrayResize(pivots, sz + 1);
      pivots[sz] = p;
      count++;
   }
   return count > 0;
}

bool LatestNewPivot(SPivot &pivot)
{
   SPivot pivots[];
   int count = 0;
   if(!LoadRecentPivots(pivots, count))
      return false;
   if(count <= 0)
      return false;
   pivot = pivots[count - 1];
   if(pivot.time <= g_last_pivot_time_seen)
      return false;
   g_last_pivot_time_seen = pivot.time;
   return true;
}

bool GroupMatches(const SEngine &eng, const SPivot &pivot)
{
   if(eng.label != pivot.label)
      return false;

   string session = SessionOf(pivot.time);
   string vol = VolRegime();
   string ctx = TradeContext(pivot.label, pivot.time);
   string key = pivot.label;

   if(eng.group_type == "label")
      key = pivot.label;
   else if(eng.group_type == "label_vol")
      key = pivot.label + "|" + vol;
   else if(eng.group_type == "label_session_vol")
      key = pivot.label + "|" + session + "|" + vol;
   else if(eng.group_type == "label_trade_context")
      key = pivot.label + "|" + ctx;
   else if(eng.group_type == "label_trade_context_session")
      key = pivot.label + "|" + ctx + "|" + session;
   else if(eng.group_type == "label_trade_context_session_vol")
      key = pivot.label + "|" + ctx + "|" + session + "|" + vol;

   return key == eng.group_key;
}

//──────────────────────────────────────────────────────────────────
// Trading
//──────────────────────────────────────────────────────────────────

int CountOpenPositions()
{
   int total = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol &&
         PositionGetInteger(POSITION_MAGIC) == InpMagic)
         total++;
   }
   return total;
}

double CalcLots(double stop_pips)
{
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   double risk_money = equity * InpRiskPct / 100.0;
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(tick_value <= 0.0 || tick_size <= 0.0 || stop_pips <= 0.0)
      return 0.0;

   double money_per_lot = (stop_pips * g_pip / tick_size) * tick_value;
   if(money_per_lot <= 0.0)
      return 0.0;

   double lots = risk_money / money_per_lot;
   double min_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   lots = MathMax(min_lot, MathMin(max_lot, lots));
   lots = MathFloor(lots / step) * step;
   return NormalizeDouble(lots, 2);
}

void InitPositions()
{
   for(int i = 0; i < ArraySize(g_positions); i++)
   {
      g_positions[i].active = false;
      g_positions[i].ticket = 0;
      g_positions[i].engine_id = "";
      g_positions[i].side = "";
      g_positions[i].entry_time = 0;
      g_positions[i].pivot_time = 0;
      g_positions[i].entry_price = 0.0;
      g_positions[i].sl = 0.0;
      g_positions[i].tp = 0.0;
      g_positions[i].lots = 0.0;
      g_positions[i].timeout_min = 0;
   }
}

ulong FindNewestPositionTicket()
{
   ulong newest_ticket = 0;
   datetime newest_time = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != _Symbol ||
         PositionGetInteger(POSITION_MAGIC) != InpMagic)
         continue;
      datetime pos_time = (datetime)PositionGetInteger(POSITION_TIME);
      if(pos_time >= newest_time)
      {
         newest_time = pos_time;
         newest_ticket = ticket;
      }
   }
   return newest_ticket;
}

void RegisterPosition(ulong ticket, const SSignal &sig, double entry, double sl, double tp, double lots)
{
   for(int i = 0; i < ArraySize(g_positions); i++)
   {
      if(!g_positions[i].active)
      {
         g_positions[i].active = true;
         g_positions[i].ticket = ticket;
         g_positions[i].engine_id = sig.engine_id;
         g_positions[i].side = sig.side;
         g_positions[i].entry_time = TimeCurrent();
         g_positions[i].pivot_time = sig.pivot_time;
         g_positions[i].entry_price = entry;
         g_positions[i].sl = sl;
         g_positions[i].tp = tp;
         g_positions[i].lots = lots;
         g_positions[i].timeout_min = sig.timeout_min;
         return;
      }
   }
}

bool OpenTrade(const SSignal &sig)
{
   if(SpreadPips() > InpMaxSpreadPips)
   {
      LogEvent("BLOCK_SPREAD", sig, 0.0, "spread too wide");
      return false;
   }
   if(CountOpenPositions() >= InpMaxOpenPositions)
   {
      LogEvent("BLOCK_MAX_POSITIONS", sig, 0.0, "max positions reached");
      return false;
   }

   bool is_buy = sig.side == "BUY";
   double entry = is_buy ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double risk = sig.stop_pips * g_pip;
   double sl = is_buy ? entry - risk : entry + risk;
   double tp = is_buy ? entry + risk * sig.target_r : entry - risk * sig.target_r;
   entry = NormalizePrice(entry);
   sl = NormalizePrice(sl);
   tp = NormalizePrice(tp);
   double lots = CalcLots(sig.stop_pips);
   if(lots <= 0.0)
   {
      LogEvent("BLOCK_LOTS", sig, 0.0, "lot calculation failed");
      return false;
   }

   if(!InpAllowTrading)
   {
      LogEvent("SIGNAL_DRY_RUN", sig, 0.0, "trading disabled");
      return true;
   }

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);
   bool ok = is_buy
      ? g_trade.Buy(lots, _Symbol, entry, sl, tp, sig.engine_id)
      : g_trade.Sell(lots, _Symbol, entry, sl, tp, sig.engine_id);
   if(!ok)
   {
      LogEvent("ORDER_FAIL", sig, 0.0, IntegerToString(GetLastError()));
      return false;
   }

   ulong ticket = FindNewestPositionTicket();
   if(ticket == 0)
      ticket = g_trade.ResultOrder();
   RegisterPosition(ticket, sig, entry, sl, tp, lots);
   LogTrade("OPEN", ticket, sig.engine_id, sig.side, entry, sl, tp, lots, 0.0, "opened");
   return true;
}

void ManagePositions()
{
   for(int i = 0; i < ArraySize(g_positions); i++)
   {
      if(!g_positions[i].active)
         continue;
      if(!PositionSelectByTicket(g_positions[i].ticket))
      {
         g_positions[i].active = false;
         continue;
      }
      datetime entry_time = g_positions[i].entry_time;
      int timeout_min = g_positions[i].timeout_min > 0 ? g_positions[i].timeout_min : InpTimeoutMinutes;
      if(TimeCurrent() - entry_time < timeout_min * 60)
         continue;

      bool is_buy = g_positions[i].side == "BUY";
      double close_price = is_buy ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double pips = is_buy
         ? (close_price - g_positions[i].entry_price) / g_pip
         : (g_positions[i].entry_price - close_price) / g_pip;
      if(InpAllowTrading)
         g_trade.PositionClose(g_positions[i].ticket);
      LogTrade("TIMEOUT_CLOSE", g_positions[i].ticket, g_positions[i].engine_id,
               g_positions[i].side, g_positions[i].entry_price, g_positions[i].sl,
               g_positions[i].tp, g_positions[i].lots, pips, "timeout");
      g_positions[i].active = false;
   }
}

void DrawSignal(const SSignal &sig)
{
   if(!InpDrawArrows)
      return;
   string name = "VECTOR80_" + sig.engine_id + "_" + IntegerToString((int)sig.signal_time);
   int arrow = sig.side == "BUY" ? 233 : 234;
   color c = sig.side == "BUY" ? clrLime : clrTomato;
   ObjectCreate(0, name, OBJ_ARROW, 0, sig.signal_time, sig.pivot_price);
   ObjectSetInteger(0, name, OBJPROP_ARROWCODE, arrow);
   ObjectSetInteger(0, name, OBJPROP_COLOR, c);
   ObjectSetInteger(0, name, OBJPROP_WIDTH, 2);
}

bool CooldownOk(string side)
{
   datetime last = side == "BUY" ? g_last_buy_signal : g_last_sell_signal;
   return last == 0 || (TimeCurrent() - last) >= InpSameSideCooldownMin * 60;
}

void SetCooldown(string side)
{
   if(side == "BUY")
      g_last_buy_signal = TimeCurrent();
   else
      g_last_sell_signal = TimeCurrent();
}

void ProcessPivot(const SPivot &pivot)
{
   int shift = iBarShift(_Symbol, InpSignalTF, pivot.time, false);
   if(shift >= 0)
   {
      if(shift < g_dbg_min_pivot_shift) g_dbg_min_pivot_shift = shift;
      if(shift > g_dbg_max_pivot_shift) g_dbg_max_pivot_shift = shift;
   }
   if(shift < 0 || shift > InpEntryWindowBars)
   {
      g_dbg_pivot_too_old++;
      if(InpDebugLogging && g_dbg_pivot_too_old <= 25)
      {
         string note = StringFormat("pivot_time=%s label=%s side=%s shift=%d price=%s",
                                    TS(pivot.time), pivot.label, pivot.side, shift,
                                    DoubleToString(pivot.price, _Digits));
         LogDebug("PIVOT_OUTSIDE_ENTRY_WINDOW", note);
      }
      return;
   }

   for(int i = 0; i < ENGINE_COUNT; i++)
   {
      SEngine eng = g_engines[i];
      if(!GroupMatches(eng, pivot))
         continue;
      g_dbg_group_matches++;
      DebugShiftSweep(eng.id, iTime(_Symbol, InpSignalTF, 0));
      if(!CooldownOk(eng.side))
      {
         g_dbg_cooldown_blocks++;
         continue;
      }

      double score = 0.0;
      string note = "";
      datetime bar_time = iTime(_Symbol, InpSignalTF, 0);
      bool have_score = GetEngineScore(eng, pivot, bar_time, score, note);

      SSignal sig;
      sig.active = true;
      sig.signal_time = TimeCurrent();
      sig.pivot_time = pivot.time;
      sig.engine_id = eng.id;
      sig.side = eng.side;
      sig.label = pivot.label;
      sig.group_key = eng.group_key;
      sig.pivot_price = pivot.price;
      sig.score = score;
      sig.stop_pips = eng.stop_pips;
      sig.target_r = eng.target_r;
      sig.timeout_min = eng.timeout_min;

      if(!have_score)
      {
         g_dbg_score_missing++;
         LogEvent("BLOCK_MODEL_SCORE", sig, eng.threshold, note);
         continue;
      }
      if(score < eng.threshold)
      {
         g_dbg_threshold_blocks++;
         LogEvent("BLOCK_THRESHOLD", sig, eng.threshold, note);
         continue;
      }

      g_dbg_signals++;
      LogEvent("SIGNAL", sig, eng.threshold, note);
      DrawSignal(sig);
      OpenTrade(sig);
      SetCooldown(eng.side);
      break; // one engine per pivot after dedupe/router
   }
}

//──────────────────────────────────────────────────────────────────
// MT5 lifecycle
//──────────────────────────────────────────────────────────────────

int OnInit()
{
   g_pip = Pip();
   InitEngines();
   InitShiftSweep();
   OpenLogs();

   g_trade.SetExpertMagicNumber(InpMagic);
   g_trade.SetDeviationInPoints(InpSlippagePoints);

   g_zz_handle = iCustom(_Symbol, InpSignalTF, InpZZIndicatorName,
                         IntegerToString(InpZZTmpMaxBars), InpZZIndPeriod,
                         InpZZDepth, InpZZDeviation, InpZZBackstep);
   if(g_zz_handle == INVALID_HANDLE)
   {
      Print("VECTOR80: failed to load ZigZag Lines MTF. err=", GetLastError());
      return INIT_FAILED;
   }

   g_rsi_m5 = iRSI(_Symbol, InpSignalTF, 14, PRICE_CLOSE);
   g_stoch_m5 = iStochastic(_Symbol, InpSignalTF, 5, 3, 3, MODE_SMA, STO_LOWHIGH);
   g_atr_m5 = iATR(_Symbol, InpSignalTF, 14);
   g_ema50_h1 = iMA(_Symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
   g_ema200_h1 = iMA(_Symbol, PERIOD_H1, 200, 0, MODE_EMA, PRICE_CLOSE);

   InitPositions();
   Print("VECTOR80 prototype initialized. ScoreMode=", EnumToString(InpScoreMode),
         " Trading=", (InpAllowTrading ? "true" : "false"));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   int min_shift = g_dbg_min_pivot_shift == 999999 ? -1 : g_dbg_min_pivot_shift;
   string summary = StringFormat(
      "bars=%I64d latest_pivots=%I64d pivot_too_old=%I64d min_shift=%d max_shift=%d group_matches=%I64d cooldown_blocks=%I64d score_missing=%I64d threshold_blocks=%I64d signals=%I64d",
      g_dbg_bars, g_dbg_latest_pivots, g_dbg_pivot_too_old, min_shift, g_dbg_max_pivot_shift,
      g_dbg_group_matches, g_dbg_cooldown_blocks, g_dbg_score_missing,
      g_dbg_threshold_blocks, g_dbg_signals
   );
   LogDebug("SUMMARY", summary);
   Print("VECTOR80 debug summary: ", summary);

   if(InpDebugShiftSweep && ArraySize(g_shift_values) > 0)
   {
      string sweep = "";
      for(int i = 0; i < ArraySize(g_shift_values); i++)
      {
         if(i > 0) sweep += "; ";
         sweep += IntegerToString(g_shift_values[i]) + "=" + IntegerToString((int)g_shift_matches[i]);
      }
      LogDebug("SHIFT_SWEEP", sweep);
      Print("VECTOR80 shift sweep matches: ", sweep);
   }

   if(g_zz_handle != INVALID_HANDLE) IndicatorRelease(g_zz_handle);
   if(g_rsi_m5 != INVALID_HANDLE) IndicatorRelease(g_rsi_m5);
   if(g_stoch_m5 != INVALID_HANDLE) IndicatorRelease(g_stoch_m5);
   if(g_atr_m5 != INVALID_HANDLE) IndicatorRelease(g_atr_m5);
   if(g_ema50_h1 != INVALID_HANDLE) IndicatorRelease(g_ema50_h1);
   if(g_ema200_h1 != INVALID_HANDLE) IndicatorRelease(g_ema200_h1);
   CloseLogs();
}

void OnTick()
{
   ManagePositions();
   if(!IsNewBar())
      return;
   g_dbg_bars++;

   SPivot p;
   if(LatestNewPivot(p))
   {
      g_dbg_latest_pivots++;
      ProcessPivot(p);
   }
}
