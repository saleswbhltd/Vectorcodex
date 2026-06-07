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
#include <MARKET_MAP/MarketMap.mqh>
#include <VECTOR_TIME/VectorTime.mqh>

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
input int     InpScoreTimeToleranceMin            = 5;
input bool    InpDebugShiftSweep                  = true;
input int     InpDebugShiftSweepFromMin           = -360;
input int     InpDebugShiftSweepToMin             = 360;
input int     InpDebugShiftSweepStepMin           = 30;
input bool    InpAllowTrading                     = false;
input bool    InpDrawArrows                       = true;
input int     InpSignalClusterCooldownMin         = 15;      // one trade per same side/group cluster
input int     InpSameSideCooldownMin              = 0;       // extra same-side cooldown after cluster de-dupe
input int     InpEntryWindowBars                  = 2;       // pivot bar + this many M5 bars

input group "=== Demo Exploration ==="
input bool    InpDemoExploreMode                  = false;   // DEMO ONLY: lower thresholds for faster trade/log loop
input double  InpDemoExploreMinScore              = 0.55;    // DEMO ONLY: effective threshold cap
input bool    InpDemoExploreFallbackHeuristic     = false;   // DEMO ONLY: heuristic score if CSV score missing

input group "=== Adaptive UTC Threshold Rule ==="
input bool    InpAdaptiveTimeRuleEnabled          = true;
input bool    InpAdaptiveAllowEntries             = true;    // disable rule trades without disabling research logging
input int     InpAdaptiveStartUtcMinutes          = 0;       // 00:00 UTC
input int     InpAdaptiveEndUtcMinutes            = 120;     // 02:00 UTC, end exclusive
input double  InpAdaptiveThresholdDelta           = 0.08;
input double  InpAdaptiveMinScore                 = 0.70;
input bool    InpAdaptiveShadowOutcomes           = true;
input double  InpAdaptiveResearchMaxDelta         = 0.15;    // log near-threshold candidates all day
input string  InpAdaptiveLogFile                  = "VECTOR80_adaptive_thresholds.csv";

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

input group "=== Retest Entry Test Mode ==="
input bool    InpUseSellRetestEntry               = false;   // queue SELL and wait for better price
input double  InpSellRetestPips                   = 2.0;
input int     InpRetestExpiryBars                 = 2;

input group "=== Heuristic Proxy Test Mode ==="
input double  InpHeuristicLLThreshold             = 0.88;
input double  InpHeuristicHLThreshold             = 0.90;
input double  InpHeuristicHHThreshold             = 0.90;

input group "=== Live Python Bridge ==="
input bool    InpRequireLiveBridge                 = true;
input bool    InpExportLiveTicks                   = true;
input string  InpBridgeHeartbeatFile               = "VECTOR80_bridge_heartbeat.csv";
input string  InpMt5HeartbeatFile                  = "VECTOR80_mt5_heartbeat.csv";
input string  InpScoreRequestFile                  = "VECTOR80_score_requests.csv";
input int     InpBridgeMaxAgeSec                   = 15;
input int     InpScoreWaitSec                      = 30;
input int     InpBridgeAlertCooldownSec            = 900;
input bool    InpBridgePushNotifications           = true;

input group "=== Logging ==="
input bool    InpUseCommonFiles                   = true;
input string  InpEventLogFile                     = "VECTOR80_events.csv";
input string  InpTradeLogFile                     = "VECTOR80_trades.csv";
input bool    InpDebugLogging                     = true;

input group "=== Time HUD ==="
input bool    InpTimeHudEnabled                   = true;
input ENUM_BASE_CORNER InpTimeHudCorner           = CORNER_LEFT_UPPER;
input int     InpTimeHudX                         = 10;
input int     InpTimeHudY                         = 20;
input int     InpTimeHudFontSize                  = 9;
input color   InpTimeHudColor                     = clrWhite;
input color   InpTimeHudOpenColor                 = clrLime;
input color   InpTimeHudClosedColor               = clrGray;

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
   double   validated_threshold;
   double   effective_threshold;
   bool     adaptive_rule;
   datetime utc_time;
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
   bool     adaptive_rule;
   double   score;
   double   validated_threshold;
   double   effective_threshold;
};

struct SPendingSignal
{
   bool     active;
   SSignal  signal;
   datetime expiry_time;
   double   trigger_price;
};

struct SShadowCandidate
{
   bool     active;
   string   candidate_id;
   datetime entry_time;
   datetime utc_time;
   datetime pivot_time;
   string   engine_id;
   string   side;
   double   score;
   double   validated_threshold;
   double   rule_threshold;
   double   entry_price;
   double   stop_price;
   double   target_price;
   datetime expiry_time;
   bool     in_rule_window;
   string   market_direction;
   string   market_structure;
   string   market_volatility;
   string   market_transition;
   double   market_confidence;
   double   market_strength;
   double   market_liquidity;
   double   market_exhaustion;
};

CTrade g_trade;
CMarketMap g_market_map;
MarketMapState g_market_state;
bool g_market_state_ready = false;
CVectorTime g_vector_time;
SEngine g_engines[ENGINE_COUNT];
SManagedPosition g_positions[32];
SPendingSignal g_pending_signals[32];
SShadowCandidate g_shadow_candidates[128];

double   g_pip = 0.0001;
int      g_zz_handle = INVALID_HANDLE;
datetime g_last_bar = 0;
datetime g_last_buy_signal = 0;
datetime g_last_sell_signal = 0;
datetime g_last_pivot_time_seen = 0;
string   g_last_cluster_keys[64];
datetime g_last_cluster_times[64];
int      g_last_cluster_count = 0;

int g_event_handle = INVALID_HANDLE;
int g_trade_handle = INVALID_HANDLE;
int g_live_tick_handle = INVALID_HANDLE;
int g_score_request_handle = INVALID_HANDLE;
int g_adaptive_handle = INVALID_HANDLE;
string g_live_tick_file = "";
datetime g_last_bridge_alert = 0;
datetime g_last_time_alert = 0;
bool g_pending_pivot_active = false;
SPivot g_pending_pivot;
datetime g_pending_score_bar = 0;
datetime g_pending_score_deadline = 0;

long g_dbg_bars = 0;
long g_dbg_latest_pivots = 0;
long g_dbg_pivot_too_old = 0;
long g_dbg_group_matches = 0;
long g_dbg_cooldown_blocks = 0;
long g_dbg_cluster_blocks = 0;
long g_dbg_score_missing = 0;
long g_dbg_threshold_blocks = 0;
long g_dbg_signals = 0;
long g_dbg_trade_attempts = 0;
long g_dbg_trades_opened = 0;
long g_dbg_retest_queued = 0;
long g_dbg_retest_filled = 0;
long g_dbg_retest_expired = 0;
long g_dbg_adaptive_signals = 0;
long g_dbg_shadow_candidates = 0;
long g_dbg_shadow_wins = 0;
long g_dbg_shadow_losses = 0;
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

int NormalizeDayMinute(int value)
{
   int result = value % 1440;
   if(result < 0)
      result += 1440;
   return result;
}

datetime AdaptiveUtcTime(datetime broker_time)
{
   if(MQLInfoInteger(MQL_TESTER))
      return MMBrokerToUtc(broker_time);
   if(g_vector_time.Ready())
      return g_vector_time.BrokerToUtc(broker_time);
   return MMBrokerToUtc(broker_time);
}

int UtcMinuteOfDay(datetime broker_time)
{
   MqlDateTime utc;
   TimeToStruct(AdaptiveUtcTime(broker_time), utc);
   return utc.hour * 60 + utc.min;
}

bool InAdaptiveTimeWindow(datetime broker_time)
{
   if(!InpAdaptiveTimeRuleEnabled)
      return false;
   int start = NormalizeDayMinute(InpAdaptiveStartUtcMinutes);
   int end = NormalizeDayMinute(InpAdaptiveEndUtcMinutes);
   int now = UtcMinuteOfDay(broker_time);
   if(start == end)
      return true;
   if(start < end)
      return now >= start && now < end;
   return now >= start || now < end;
}

double AdaptiveThreshold(double validated_threshold, datetime broker_time)
{
   if(!InAdaptiveTimeWindow(broker_time))
      return validated_threshold;
   double lowered = validated_threshold - MathMax(0.0, InpAdaptiveThresholdDelta);
   return MathMax(InpAdaptiveMinScore, lowered);
}

string UtcSlot(datetime broker_time)
{
   MqlDateTime utc;
   TimeToStruct(AdaptiveUtcTime(broker_time), utc);
   int minute = (utc.min / 15) * 15;
   return StringFormat("%02d:%02d", utc.hour, minute);
}

int ScoreTimeShiftMinutes(datetime broker_time)
{
   if(MQLInfoInteger(MQL_TESTER))
      return MMBrokerUtcOffsetHours(broker_time) * 60;
   if(g_vector_time.Healthy())
      return g_vector_time.BrokerUtcOffsetSeconds() / 60;
   return 0;
}

bool TimeHealthy(string &reason)
{
   reason = "";
   if(MQLInfoInteger(MQL_TESTER))
      return true;
   if(g_vector_time.Healthy())
      return true;
   reason = g_vector_time.HealthReason();
   if(reason == "")
      reason = "automatic broker/UTC synchronization unavailable";
   return false;
}

void TimeHealthAlert(string reason)
{
   datetime now = TimeLocal();
   if(g_last_time_alert > 0 && now - g_last_time_alert < 900)
      return;
   g_last_time_alert = now;
   string message = "VECTOR80 TIME ERROR: " + reason +
                    "; new entries blocked. Check the EA.";
   Alert(message);
   Print(message);
   SendNotification(message);
}

string DateTag(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d%02d%02d", dt.year, dt.mon, dt.day);
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
   TimeToStruct(AdaptiveUtcTime(t), dt);
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
   bool new_adaptive = !FileIsExist(InpAdaptiveLogFile, InpUseCommonFiles ? FILE_COMMON : 0);
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

   g_adaptive_handle = FileOpen(InpAdaptiveLogFile, FileFlags(), ',');
   if(g_adaptive_handle != INVALID_HANDLE)
   {
      if(new_adaptive)
      {
         FileWrite(g_adaptive_handle,
                   "event_time", "event", "candidate_id", "broker_time", "utc_time",
                   "utc_slot", "engine_id", "side", "pivot_time", "score",
                   "validated_threshold", "rule_threshold", "score_gap",
                   "in_rule_window", "adaptive_entries_enabled", "entry_price",
                   "stop_price", "target_price", "outcome", "outcome_pips",
                   "market_direction", "market_structure", "market_volatility",
                   "market_transition", "market_confidence", "market_strength",
                   "market_liquidity", "market_exhaustion", "note");
      }
      else FileSeek(g_adaptive_handle, 0, SEEK_END);
   }
}

void CloseLogs()
{
   if(g_event_handle != INVALID_HANDLE) { FileClose(g_event_handle); g_event_handle = INVALID_HANDLE; }
   if(g_trade_handle != INVALID_HANDLE) { FileClose(g_trade_handle); g_trade_handle = INVALID_HANDLE; }
   if(g_adaptive_handle != INVALID_HANDLE) { FileClose(g_adaptive_handle); g_adaptive_handle = INVALID_HANDLE; }
}

void LogAdaptive(const SShadowCandidate &candidate, string event_type,
                 string outcome, double outcome_pips, string note)
{
   if(g_adaptive_handle == INVALID_HANDLE)
      return;
   FileWrite(g_adaptive_handle,
             TS(TimeCurrent()), event_type, candidate.candidate_id,
             TS(candidate.entry_time), TS(candidate.utc_time),
             UtcSlot(candidate.entry_time), candidate.engine_id, candidate.side,
             TS(candidate.pivot_time), DoubleToString(candidate.score, 6),
             DoubleToString(candidate.validated_threshold, 3),
             DoubleToString(candidate.rule_threshold, 3),
             DoubleToString(candidate.validated_threshold - candidate.score, 6),
             candidate.in_rule_window ? 1 : 0,
             InpAdaptiveAllowEntries ? 1 : 0,
             DoubleToString(candidate.entry_price, _Digits),
             DoubleToString(candidate.stop_price, _Digits),
             DoubleToString(candidate.target_price, _Digits),
             outcome, DoubleToString(outcome_pips, 2),
             candidate.market_direction, candidate.market_structure,
             candidate.market_volatility, candidate.market_transition,
             DoubleToString(candidate.market_confidence, 2),
             DoubleToString(candidate.market_strength, 2),
             DoubleToString(candidate.market_liquidity, 2),
             DoubleToString(candidate.market_exhaustion, 2), note);
   FileFlush(g_adaptive_handle);
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

void BridgeAlert(string message)
{
   datetime now = TimeLocal();
   if(g_last_bridge_alert > 0 &&
      now - g_last_bridge_alert < MathMax(1, InpBridgeAlertCooldownSec))
      return;
   g_last_bridge_alert = now;
   string full = "VECTOR80 BRIDGE: " + message;
   Alert(full);
   Print(full);
   if(InpBridgePushNotifications)
      SendNotification(full);
}

void WriteMt5Heartbeat()
{
   int h = FileOpen(InpMt5HeartbeatFile,
                    FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ,
                    ',');
   if(h == INVALID_HANDLE)
      return;
   FileWrite(h, "epoch", "status", "account", "symbol", "timeframe", "trading");
   FileWrite(h, IntegerToString((long)TimeGMT()), "RUNNING",
             IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN)),
             _Symbol, EnumToString(InpSignalTF),
             (InpAllowTrading ? "true" : "false"));
   FileClose(h);
}

bool BridgeHealthy(string &reason)
{
   reason = "";
   if(!InpRequireLiveBridge)
      return true;

   int h = FileOpen(InpBridgeHeartbeatFile,
                    FILE_READ | FILE_CSV | FILE_ANSI | FILE_COMMON | FILE_SHARE_WRITE,
                    ',');
   if(h == INVALID_HANDLE)
   {
      reason = "heartbeat file missing";
      return false;
   }

   long epoch = 0;
   string status = "";
   string detail = "";
   while(!FileIsEnding(h))
   {
      string c_epoch = FileReadString(h);
      string c_status = FileReadString(h);
      FileReadString(h); // pid
      FileReadString(h); // last_scored_bar
      FileReadString(h); // score_rows
      string c_detail = FileReadString(h);
      if(c_epoch == "epoch" || c_epoch == "")
         continue;
      epoch = StringToInteger(c_epoch);
      status = c_status;
      detail = c_detail;
   }
   FileClose(h);

   if(epoch <= 0)
   {
      reason = "invalid heartbeat";
      return false;
   }
   long age = (long)TimeGMT() - epoch;
   if(age < 0)
      age = -age;
   if(age > MathMax(1, InpBridgeMaxAgeSec))
   {
      reason = StringFormat("heartbeat stale age=%d sec", (int)age);
      return false;
   }
   if(status != "RUNNING")
   {
      reason = "status=" + status + " detail=" + detail;
      return false;
   }
   return true;
}

void EnsureLiveTickFile()
{
   if(!InpExportLiveTicks)
      return;
   string wanted = StringFormat("VECTOR80_LIVE_TICKS_%s_%s.csv",
                                _Symbol, DateTag(TimeCurrent()));
   if(g_live_tick_handle != INVALID_HANDLE && wanted == g_live_tick_file)
      return;
   if(g_live_tick_handle != INVALID_HANDLE)
      FileClose(g_live_tick_handle);

   bool is_new = !FileIsExist(wanted, FILE_COMMON);
   g_live_tick_handle = FileOpen(
      wanted,
      FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON |
      FILE_SHARE_READ | FILE_SHARE_WRITE,
      ','
   );
   if(g_live_tick_handle == INVALID_HANDLE)
   {
      BridgeAlert("cannot open live tick file err=" + IntegerToString(GetLastError()));
      return;
   }
   g_live_tick_file = wanted;
   FileSeek(g_live_tick_handle, 0, SEEK_END);
   if(is_new)
      FileWrite(g_live_tick_handle, "datetime", "time_msc", "bid", "ask",
                "last", "volume", "flags", "mid");
}

void WriteLiveTick()
{
   if(!InpExportLiveTicks)
      return;
   EnsureLiveTickFile();
   if(g_live_tick_handle == INVALID_HANDLE)
      return;

   MqlTick tick;
   if(!SymbolInfoTick(_Symbol, tick))
      return;
   double mid = 0.0;
   if(tick.bid > 0.0 && tick.ask > 0.0)
      mid = (tick.bid + tick.ask) * 0.5;
   else if(tick.last > 0.0)
      mid = tick.last;
   FileWrite(g_live_tick_handle,
             TimeToString(tick.time, TIME_DATE | TIME_SECONDS),
             IntegerToString((long)tick.time_msc),
             DoubleToString(tick.bid, _Digits),
             DoubleToString(tick.ask, _Digits),
             DoubleToString(tick.last, _Digits),
             DoubleToString(tick.volume_real, 2),
             IntegerToString((long)tick.flags),
             DoubleToString(mid, _Digits));
}

bool OpenScoreRequests()
{
   bool is_new = !FileIsExist(InpScoreRequestFile, FILE_COMMON);
   g_score_request_handle = FileOpen(
      InpScoreRequestFile,
      FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON |
      FILE_SHARE_READ | FILE_SHARE_WRITE,
      ','
   );
   if(g_score_request_handle == INVALID_HANDLE)
      return false;
   FileSeek(g_score_request_handle, 0, SEEK_END);
   if(is_new)
      FileWrite(g_score_request_handle, "request_time", "bar_time", "engine_id",
                "pivot_time", "pivot_price", "label", "side");
   return true;
}

void QueueScoreRequests(const SPivot &pivot, datetime score_bar)
{
   if(g_score_request_handle == INVALID_HANDLE && !OpenScoreRequests())
   {
      BridgeAlert("cannot open score request file err=" + IntegerToString(GetLastError()));
      return;
   }
   for(int i = 0; i < ENGINE_COUNT; i++)
   {
      if(!GroupMatches(g_engines[i], pivot))
         continue;
      FileWrite(g_score_request_handle, TS(TimeCurrent()), TS(score_bar),
                g_engines[i].id, TS(pivot.time),
                DoubleToString(pivot.price, _Digits), pivot.label, pivot.side);
   }
   FileFlush(g_score_request_handle);
}

bool PendingScoresReady()
{
   for(int i = 0; i < ENGINE_COUNT; i++)
   {
      if(!GroupMatches(g_engines[i], g_pending_pivot))
         continue;
      double score = 0.0;
      datetime matched = 0;
      if(!ExternalScore(g_pending_score_bar, g_engines[i].id, score, matched))
         return false;
   }
   return true;
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
   int score_shift_min = ScoreTimeShiftMinutes(bar_time);
   int tolerance_sec = MathMax(0, InpScoreTimeToleranceMin) * 60;
   while(!FileIsEnding(h))
   {
      string t = FileReadString(h);
      string e = FileReadString(h);
      string s = FileReadString(h);
      if(t == "time" || t == "")
         continue;
      datetime row_time = StringToTime(t);
      datetime shifted_time = row_time + score_shift_min * 60;
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
         note = StringFormat(
            "external_score shifted_match=%s delta_min=%d automatic_shift_min=%d",
            TS(matched_time), delta_min, ScoreTimeShiftMinutes(bar_time));
         return true;
      }
      note = "missing_external_score";
      return false;
   }
   score = HeuristicScore(eng, pivot);
   note = "heuristic_proxy_not_validated";
   return true;
}

double EffectiveThreshold(double validatedThreshold)
{
   if(!InpDemoExploreMode)
      return validatedThreshold;
   if(InpDemoExploreMinScore <= 0.0)
      return validatedThreshold;
   return MathMin(validatedThreshold, InpDemoExploreMinScore);
}

string AppendNote(string base, string extra)
{
   if(base == "")
      return extra;
   return base + " | " + extra;
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
      g_positions[i].adaptive_rule = false;
      g_positions[i].score = 0.0;
      g_positions[i].validated_threshold = 0.0;
      g_positions[i].effective_threshold = 0.0;
   }
}

void InitPendingSignals()
{
   for(int i = 0; i < ArraySize(g_pending_signals); i++)
   {
      g_pending_signals[i].active = false;
      g_pending_signals[i].expiry_time = 0;
      g_pending_signals[i].trigger_price = 0.0;
   }
}

void InitShadowCandidates()
{
   for(int i = 0; i < ArraySize(g_shadow_candidates); i++)
      g_shadow_candidates[i].active = false;
}

void FillMarketSnapshot(SShadowCandidate &candidate)
{
   candidate.market_direction = "UNKNOWN";
   candidate.market_structure = "UNKNOWN";
   candidate.market_volatility = "UNKNOWN";
   candidate.market_transition = "UNKNOWN";
   candidate.market_confidence = 0.0;
   candidate.market_strength = 0.0;
   candidate.market_liquidity = 0.0;
   candidate.market_exhaustion = 0.0;
   if(!g_market_state_ready)
      return;
   candidate.market_direction = MarketMapDirectionName(g_market_state.direction);
   candidate.market_structure = MarketMapStructureName(g_market_state.structure);
   candidate.market_volatility =
      MarketMapVolatilityPhaseName(g_market_state.volatility_phase);
   candidate.market_transition = MarketMapTransitionName(g_market_state.transition);
   candidate.market_confidence = g_market_state.state_confidence;
   candidate.market_strength = g_market_state.strength_score;
   candidate.market_liquidity = g_market_state.liquidity_score;
   candidate.market_exhaustion = g_market_state.exhaustion_score;
}

bool ShadowCandidateExists(string candidate_id)
{
   for(int i = 0; i < ArraySize(g_shadow_candidates); i++)
      if(g_shadow_candidates[i].active &&
         g_shadow_candidates[i].candidate_id == candidate_id)
         return true;
   return false;
}

void QueueShadowCandidate(const SSignal &sig)
{
   if(!InpAdaptiveShadowOutcomes || sig.score >= sig.validated_threshold)
      return;
   double max_delta = MathMax(0.0, InpAdaptiveResearchMaxDelta);
   if(sig.score < sig.validated_threshold - max_delta)
      return;

   string candidate_id = sig.engine_id + "_" +
                         IntegerToString((int)sig.pivot_time) + "_" +
                         IntegerToString((int)sig.signal_time);
   if(ShadowCandidateExists(candidate_id))
      return;

   for(int i = 0; i < ArraySize(g_shadow_candidates); i++)
   {
      if(g_shadow_candidates[i].active)
         continue;
      SShadowCandidate candidate;
      ZeroMemory(candidate);
      candidate.active = true;
      candidate.candidate_id = candidate_id;
      candidate.entry_time = TimeCurrent();
      candidate.utc_time = AdaptiveUtcTime(candidate.entry_time);
      candidate.pivot_time = sig.pivot_time;
      candidate.engine_id = sig.engine_id;
      candidate.side = sig.side;
      candidate.score = sig.score;
      candidate.validated_threshold = sig.validated_threshold;
      candidate.rule_threshold =
         AdaptiveThreshold(sig.validated_threshold, candidate.entry_time);
      candidate.in_rule_window = InAdaptiveTimeWindow(candidate.entry_time);
      candidate.entry_price = sig.side == "BUY" ?
                              SymbolInfoDouble(_Symbol, SYMBOL_ASK) :
                              SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double risk = sig.stop_pips * g_pip;
      candidate.stop_price = sig.side == "BUY" ?
                             candidate.entry_price - risk :
                             candidate.entry_price + risk;
      candidate.target_price = sig.side == "BUY" ?
                               candidate.entry_price + risk * sig.target_r :
                               candidate.entry_price - risk * sig.target_r;
      candidate.expiry_time = candidate.entry_time +
                              MathMax(1, sig.timeout_min) * 60;
      FillMarketSnapshot(candidate);
      g_shadow_candidates[i] = candidate;
      g_dbg_shadow_candidates++;
      string note = sig.score >= candidate.rule_threshold &&
                    candidate.in_rule_window ?
                    "ADAPTIVE_ELIGIBLE" : "RESEARCH_ONLY";
      LogAdaptive(g_shadow_candidates[i], "CANDIDATE", "", 0.0, note);
      return;
   }
   LogDebug("ADAPTIVE_SHADOW_FULL", "shadow candidate queue full");
}

void FinishShadowCandidate(int index, string outcome, double exit_price)
{
   SShadowCandidate candidate = g_shadow_candidates[index];
   double pips = candidate.side == "BUY" ?
                 (exit_price - candidate.entry_price) / g_pip :
                 (candidate.entry_price - exit_price) / g_pip;
   if(outcome == "TARGET")
      g_dbg_shadow_wins++;
   else if(outcome == "STOP")
      g_dbg_shadow_losses++;
   LogAdaptive(candidate, "OUTCOME", outcome, pips, "");
   g_shadow_candidates[index].active = false;
}

void ManageShadowCandidates()
{
   if(!InpAdaptiveShadowOutcomes)
      return;
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   for(int i = 0; i < ArraySize(g_shadow_candidates); i++)
   {
      if(!g_shadow_candidates[i].active)
         continue;
      SShadowCandidate candidate = g_shadow_candidates[i];
      if(candidate.side == "BUY")
      {
         if(bid <= candidate.stop_price)
         {
            FinishShadowCandidate(i, "STOP", candidate.stop_price);
            continue;
         }
         if(bid >= candidate.target_price)
         {
            FinishShadowCandidate(i, "TARGET", candidate.target_price);
            continue;
         }
      }
      else
      {
         if(ask >= candidate.stop_price)
         {
            FinishShadowCandidate(i, "STOP", candidate.stop_price);
            continue;
         }
         if(ask <= candidate.target_price)
         {
            FinishShadowCandidate(i, "TARGET", candidate.target_price);
            continue;
         }
      }
      if(TimeCurrent() >= candidate.expiry_time)
         FinishShadowCandidate(i, "TIMEOUT", candidate.side == "BUY" ? bid : ask);
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
         g_positions[i].adaptive_rule = sig.adaptive_rule;
         g_positions[i].score = sig.score;
         g_positions[i].validated_threshold = sig.validated_threshold;
         g_positions[i].effective_threshold = sig.effective_threshold;
         return;
      }
   }
}

bool OpenTrade(const SSignal &sig)
{
   string time_reason = "";
   if(!TimeHealthy(time_reason))
   {
      LogEvent("BLOCK_TIME_SYNC", sig, sig.effective_threshold, time_reason);
      TimeHealthAlert(time_reason);
      return false;
   }
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
      return false;
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
   string note = StringFormat(
      "opened adaptive=%s score=%.6f validated_threshold=%.3f effective_threshold=%.3f utc=%s",
      sig.adaptive_rule ? "true" : "false", sig.score,
      sig.validated_threshold, sig.effective_threshold, TS(sig.utc_time));
   LogTrade("OPEN", ticket, sig.engine_id, sig.side, entry, sl, tp, lots, 0.0, note);
   return true;
}

bool QueueRetestSignal(const SSignal &sig)
{
   if(sig.side != "SELL" || !InpUseSellRetestEntry)
      return false;

   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double trigger = NormalizePrice(bid + InpSellRetestPips * g_pip);
   int expiry_sec = MathMax(1, InpRetestExpiryBars) * PeriodSeconds(InpSignalTF);

   for(int i = 0; i < ArraySize(g_pending_signals); i++)
   {
      if(!g_pending_signals[i].active)
      {
         g_pending_signals[i].active = true;
         g_pending_signals[i].signal = sig;
         g_pending_signals[i].trigger_price = trigger;
         g_pending_signals[i].expiry_time = TimeCurrent() + expiry_sec;
         g_dbg_retest_queued++;
         string note = StringFormat("sell retest queued trigger=%s expiry=%s",
                                    DoubleToString(trigger, _Digits),
                                    TS(g_pending_signals[i].expiry_time));
         LogEvent("PENDING_RETEST", sig, 0.0, note);
         return true;
      }
   }

   LogEvent("BLOCK_PENDING_FULL", sig, 0.0, "pending retest queue full");
   return false;
}

void ManagePendingSignals()
{
   for(int i = 0; i < ArraySize(g_pending_signals); i++)
   {
      if(!g_pending_signals[i].active)
         continue;

      SSignal sig = g_pending_signals[i].signal;
      if(TimeCurrent() > g_pending_signals[i].expiry_time)
      {
         g_pending_signals[i].active = false;
         g_dbg_retest_expired++;
         LogEvent("PENDING_RETEST_EXPIRED", sig, 0.0,
                  "sell retest trigger not reached");
         continue;
      }

      if(sig.side == "SELL")
      {
         double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
         if(bid >= g_pending_signals[i].trigger_price)
         {
            g_pending_signals[i].active = false;
            g_dbg_trade_attempts++;
            if(OpenTrade(sig))
            {
               g_dbg_trades_opened++;
               g_dbg_retest_filled++;
            }
            else
            {
               LogEvent("PENDING_RETEST_ORDER_FAIL", sig, 0.0,
                        "trigger reached but order failed");
            }
         }
      }
   }
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
   if(InpSameSideCooldownMin <= 0)
      return true;
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

bool ClusterOk(const SSignal &sig)
{
   if(InpSignalClusterCooldownMin <= 0)
      return true;

   string key = sig.side + "|" + sig.group_key;
   datetime now = TimeCurrent();
   for(int i = 0; i < g_last_cluster_count; i++)
   {
      if(g_last_cluster_keys[i] == key &&
         now - g_last_cluster_times[i] < InpSignalClusterCooldownMin * 60)
         return false;
   }
   return true;
}

void SetCluster(const SSignal &sig)
{
   if(InpSignalClusterCooldownMin <= 0)
      return;

   string key = sig.side + "|" + sig.group_key;
   datetime now = TimeCurrent();
   for(int i = 0; i < g_last_cluster_count; i++)
   {
      if(g_last_cluster_keys[i] == key)
      {
         g_last_cluster_times[i] = now;
         return;
      }
   }

   int slot = g_last_cluster_count;
   if(slot >= ArraySize(g_last_cluster_keys))
      slot = 0;
   else
      g_last_cluster_count++;
   g_last_cluster_keys[slot] = key;
   g_last_cluster_times[slot] = now;
}

void ProcessPivot(const SPivot &pivot, datetime score_bar_time)
{
   string time_reason = "";
   if(!TimeHealthy(time_reason))
   {
      LogDebug("BLOCK_TIME_SYNC", time_reason);
      TimeHealthAlert(time_reason);
      return;
   }
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
      DebugShiftSweep(eng.id, score_bar_time);
      if(!CooldownOk(eng.side))
      {
         g_dbg_cooldown_blocks++;
         continue;
      }

      double score = 0.0;
      string note = "";
      bool have_score = GetEngineScore(eng, pivot, score_bar_time, score, note);
      double baseThreshold = EffectiveThreshold(eng.threshold);
      double researchedThreshold = AdaptiveThreshold(eng.threshold, TimeCurrent());
      double effectiveThreshold = baseThreshold;
      if(InpAdaptiveAllowEntries && InAdaptiveTimeWindow(TimeCurrent()))
         effectiveThreshold = MathMin(baseThreshold, researchedThreshold);

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
      sig.validated_threshold = eng.threshold;
      sig.effective_threshold = effectiveThreshold;
      sig.adaptive_rule = false;
      sig.utc_time = AdaptiveUtcTime(TimeCurrent());

      if(!have_score && InpDemoExploreMode && InpDemoExploreFallbackHeuristic)
      {
         score = HeuristicScore(eng, pivot);
         sig.score = score;
         have_score = true;
         note = AppendNote(note, "DEMO_EXPLORE heuristic_fallback_not_validated");
      }
      if(InpDemoExploreMode)
      {
         note = AppendNote(note, StringFormat("DEMO_EXPLORE original_threshold=%.3f effective_threshold=%.3f",
                                             eng.threshold, effectiveThreshold));
      }

      if(!have_score)
      {
         g_dbg_score_missing++;
         LogEvent("BLOCK_MODEL_SCORE", sig, effectiveThreshold, note);
         continue;
      }
      sig.score = score;
      sig.adaptive_rule = InpAdaptiveAllowEntries &&
                          InAdaptiveTimeWindow(TimeCurrent()) &&
                          effectiveThreshold < baseThreshold &&
                          score >= effectiveThreshold &&
                          score < baseThreshold;
      QueueShadowCandidate(sig);
      if(sig.adaptive_rule)
      {
         note = AppendNote(note, StringFormat(
            "ADAPTIVE_TIME_RULE utc_slot=%s validated_threshold=%.3f adaptive_threshold=%.3f delta=%.3f",
            UtcSlot(TimeCurrent()), eng.threshold, effectiveThreshold,
            eng.threshold - effectiveThreshold));
      }
      if(score < effectiveThreshold)
      {
         g_dbg_threshold_blocks++;
         LogEvent("BLOCK_THRESHOLD", sig, effectiveThreshold, note);
         continue;
      }
      if(!ClusterOk(sig))
      {
         g_dbg_cluster_blocks++;
         LogEvent("BLOCK_SIGNAL_CLUSTER", sig, effectiveThreshold, note);
         continue;
      }

      g_dbg_signals++;
      if(sig.adaptive_rule)
         g_dbg_adaptive_signals++;
      LogEvent("SIGNAL", sig, effectiveThreshold, note);
      DrawSignal(sig);
      SetCluster(sig);
      if(!QueueRetestSignal(sig))
      {
         g_dbg_trade_attempts++;
         if(OpenTrade(sig))
            g_dbg_trades_opened++;
      }
      SetCooldown(eng.side);
      break; // one engine per pivot after dedupe/router
   }
}

//──────────────────────────────────────────────────────────────────
// MT5 lifecycle
//──────────────────────────────────────────────────────────────────

int OnInit()
{
   if(InpAdaptiveThresholdDelta < 0.0 ||
      InpAdaptiveResearchMaxDelta < 0.0 ||
      InpAdaptiveMinScore < 0.0 ||
      InpAdaptiveMinScore > 1.0)
   {
      Print("VECTOR80: invalid adaptive threshold inputs");
      return INIT_PARAMETERS_INCORRECT;
   }
   g_pip = Pip();
   g_vector_time.Update(true);
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
   if(!g_market_map.Init(_Symbol, PERIOD_M5, MM_MODE_NATIVE))
   {
      Print("VECTOR80: failed to initialize MARKET_MAP");
      return INIT_FAILED;
   }
   if(MQLInfoInteger(MQL_TESTER))
      g_market_map.UseHistoricalBrokerTime();
   else
      g_market_map.SetLiveBrokerUtcOffset(
         g_vector_time.BrokerUtcOffsetSeconds());

   InitPositions();
   InitPendingSignals();
   InitShadowCandidates();
   if(InpRequireLiveBridge)
   {
      OpenScoreRequests();
      WriteMt5Heartbeat();
   }
   if(InpExportLiveTicks)
      EnsureLiveTickFile();
   if(InpRequireLiveBridge || InpExportLiveTicks || InpTimeHudEnabled)
      EventSetTimer(1);
   if(InpTimeHudEnabled)
      g_vector_time.DrawHud(InpTimeHudCorner, InpTimeHudX, InpTimeHudY,
                            InpTimeHudFontSize, InpTimeHudColor,
                            InpTimeHudOpenColor, InpTimeHudClosedColor);
   Print("VECTOR80 prototype initialized. ScoreMode=", EnumToString(InpScoreMode),
         " Trading=", (InpAllowTrading ? "true" : "false"),
         " AdaptiveRule=", (InpAdaptiveTimeRuleEnabled ? "true" : "false"),
         " AdaptiveEntries=", (InpAdaptiveAllowEntries ? "true" : "false"),
         " UTCWindow=", IntegerToString(InpAdaptiveStartUtcMinutes), "-",
         IntegerToString(InpAdaptiveEndUtcMinutes),
         " Delta=", DoubleToString(InpAdaptiveThresholdDelta, 3),
         " Time=", g_vector_time.Diagnostic());
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   g_vector_time.RemoveHud();
   int min_shift = g_dbg_min_pivot_shift == 999999 ? -1 : g_dbg_min_pivot_shift;
   string summary = StringFormat(
      "bars=%I64d latest_pivots=%I64d pivot_too_old=%I64d min_shift=%d max_shift=%d group_matches=%I64d cluster_blocks=%I64d cooldown_blocks=%I64d score_missing=%I64d threshold_blocks=%I64d signals=%I64d adaptive_signals=%I64d shadow_candidates=%I64d shadow_wins=%I64d shadow_losses=%I64d trade_attempts=%I64d trades_opened=%I64d retest_queued=%I64d retest_filled=%I64d retest_expired=%I64d",
      g_dbg_bars, g_dbg_latest_pivots, g_dbg_pivot_too_old, min_shift, g_dbg_max_pivot_shift,
      g_dbg_group_matches, g_dbg_cluster_blocks, g_dbg_cooldown_blocks, g_dbg_score_missing,
      g_dbg_threshold_blocks, g_dbg_signals, g_dbg_adaptive_signals,
      g_dbg_shadow_candidates, g_dbg_shadow_wins, g_dbg_shadow_losses,
      g_dbg_trade_attempts, g_dbg_trades_opened,
      g_dbg_retest_queued, g_dbg_retest_filled, g_dbg_retest_expired
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
   g_market_map.Release();
   if(g_live_tick_handle != INVALID_HANDLE) FileClose(g_live_tick_handle);
   if(g_score_request_handle != INVALID_HANDLE) FileClose(g_score_request_handle);
   CloseLogs();
}

void OnTimer()
{
   g_vector_time.Update();
   if(!MQLInfoInteger(MQL_TESTER) && g_vector_time.Ready())
      g_market_map.SetLiveBrokerUtcOffset(
         g_vector_time.BrokerUtcOffsetSeconds());
   if(InpTimeHudEnabled)
      g_vector_time.DrawHud(InpTimeHudCorner, InpTimeHudX, InpTimeHudY,
                            InpTimeHudFontSize, InpTimeHudColor,
                            InpTimeHudOpenColor, InpTimeHudClosedColor);
   string time_reason = "";
   if(!TimeHealthy(time_reason))
      TimeHealthAlert(time_reason);
   if(InpRequireLiveBridge)
      WriteMt5Heartbeat();
   if(g_live_tick_handle != INVALID_HANDLE)
      FileFlush(g_live_tick_handle);

   string bridge_reason = "";
   if(!BridgeHealthy(bridge_reason))
   {
      BridgeAlert(bridge_reason + "; new trades blocked");
      if(g_pending_pivot_active && TimeLocal() >= g_pending_score_deadline)
      {
         LogDebug("BLOCK_BRIDGE_SCORE_TIMEOUT",
                  "bridge unavailable while score request was pending");
         g_pending_pivot_active = false;
      }
      return;
   }

   if(!g_pending_pivot_active)
      return;
   if(PendingScoresReady())
   {
      SPivot pivot = g_pending_pivot;
      datetime score_bar = g_pending_score_bar;
      g_pending_pivot_active = false;
      ProcessPivot(pivot, score_bar);
      return;
   }
   if(TimeLocal() >= g_pending_score_deadline)
   {
      string note = StringFormat("score timeout bar=%s pivot=%s label=%s",
                                 TS(g_pending_score_bar), TS(g_pending_pivot.time),
                                 g_pending_pivot.label);
      LogDebug("BLOCK_BRIDGE_SCORE_TIMEOUT", note);
      BridgeAlert(note + "; new trade blocked");
      g_pending_pivot_active = false;
   }
}

void OnTick()
{
   WriteLiveTick();
   ManagePositions();
   ManagePendingSignals();
   ManageShadowCandidates();
   if(!IsNewBar())
      return;
   g_dbg_bars++;
   g_market_state_ready = g_market_map.Update() &&
                          g_market_map.GetState(g_market_state);

   SPivot p;
   if(LatestNewPivot(p))
   {
      g_dbg_latest_pivots++;
      if(!InpRequireLiveBridge)
      {
         ProcessPivot(p, iTime(_Symbol, InpSignalTF, 0));
         return;
      }
      if(g_pending_pivot_active)
         LogDebug("BLOCK_BRIDGE_PENDING_REPLACED", "previous score request did not complete");
      g_pending_pivot = p;
      g_pending_score_bar = iTime(_Symbol, InpSignalTF, 1);
      g_pending_score_deadline = TimeLocal() + MathMax(1, InpScoreWaitSec);
      g_pending_pivot_active = true;
      QueueScoreRequests(p, g_pending_score_bar);
   }
}
