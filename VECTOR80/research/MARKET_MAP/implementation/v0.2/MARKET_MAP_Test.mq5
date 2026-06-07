//+------------------------------------------------------------------+
//|                                              MARKET_MAP_Test.mq5 |
//| Non-trading Strategy Tester harness for MARKET_MAP v0.2.         |
//+------------------------------------------------------------------+
#property strict
#property version "1.000"
#property description "Logs MARKET_MAP current states without placing trades"

#include <MARKET_MAP/MarketMap.mqh>

input bool   InpWriteCsv = true;
input bool   InpUseCommonFiles = false;
input string InpCsvFile = "MARKET_MAP_test_states.csv";
input double InpMinStateConfidence = 60.0;
input double InpMinLiquidity = 50.0;
input double InpMaxExhaustion = 60.0;

CMarketMap g_map;
datetime g_last_bar = 0;
int g_file = INVALID_HANDLE;
int g_states = 0;
int g_bull = 0;
int g_bear = 0;
int g_neutral = 0;
int g_trend = 0;
int g_chop = 0;
int g_range = 0;
int g_tradeable_trend = 0;

bool IsTradeableTrend(const MarketMapState &state)
{
   return state.valid &&
          state.structure == MM_STRUCTURE_TREND &&
          state.direction != MM_DIRECTION_NEUTRAL &&
          state.transition != MM_TRANSITION_CHANGING &&
          state.state_confidence >= InpMinStateConfidence &&
          state.liquidity_score >= InpMinLiquidity &&
          state.exhaustion_score <= InpMaxExhaustion;
}

void WriteHeader()
{
   FileWrite(g_file,
             "broker_time", "direction", "structure", "volatility_phase",
             "transition", "regime", "feel", "state_confidence", "strength",
             "liquidity", "exhaustion", "net_atr", "path_efficiency",
             "range_expansion", "volume_ratio", "atr_pips", "spread_pips",
             "tradeable_trend");
}

void WriteState(const MarketMapState &state, bool tradeable)
{
   if(g_file == INVALID_HANDLE)
      return;
   FileWrite(g_file,
             TimeToString(state.timestamp, TIME_DATE | TIME_MINUTES),
             MarketMapDirectionName(state.direction),
             MarketMapStructureName(state.structure),
             MarketMapVolatilityPhaseName(state.volatility_phase),
             MarketMapTransitionName(state.transition),
             MarketMapRegimeName(state.regime),
             DoubleToString(state.feel, 2),
             DoubleToString(state.state_confidence, 2),
             DoubleToString(state.strength_score, 2),
             DoubleToString(state.liquidity_score, 2),
             DoubleToString(state.exhaustion_score, 2),
             DoubleToString(state.net_atr, 4),
             DoubleToString(state.path_efficiency, 4),
             DoubleToString(state.range_expansion, 4),
             DoubleToString(state.volume_ratio, 4),
             DoubleToString(state.atr_pips, 2),
             DoubleToString(state.spread_pips, 2),
             tradeable ? 1 : 0);
}

int OnInit()
{
   if(!g_map.Init(_Symbol, PERIOD_M5, MM_MODE_NATIVE))
      return INIT_FAILED;

   if(InpWriteCsv)
   {
      int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
      if(InpUseCommonFiles)
         flags |= FILE_COMMON;
      g_file = FileOpen(InpCsvFile, flags, ',');
      if(g_file == INVALID_HANDLE)
      {
         Print("MARKET_MAP test could not open CSV: ", InpCsvFile,
               " error=", GetLastError());
         return INIT_FAILED;
      }
      WriteHeader();
   }
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   g_map.Release();
   if(g_file != INVALID_HANDLE)
      FileClose(g_file);

   PrintFormat("MARKET_MAP TEST SUMMARY states=%d bull=%d bear=%d neutral=%d "
               "trend=%d chop=%d range=%d tradeable_trend=%d",
               g_states, g_bull, g_bear, g_neutral,
               g_trend, g_chop, g_range, g_tradeable_trend);
}

void OnTick()
{
   datetime bar_time = iTime(_Symbol, PERIOD_M5, 0);
   if(bar_time <= 0 || bar_time == g_last_bar)
      return;
   g_last_bar = bar_time;

   if(!g_map.Update())
      return;

   MarketMapState state;
   if(!g_map.GetState(state))
      return;

   bool tradeable = IsTradeableTrend(state);
   g_states++;
   if(state.direction == MM_DIRECTION_BULL) g_bull++;
   else if(state.direction == MM_DIRECTION_BEAR) g_bear++;
   else g_neutral++;

   if(state.structure == MM_STRUCTURE_TREND) g_trend++;
   else if(state.structure == MM_STRUCTURE_CHOP) g_chop++;
   else g_range++;
   if(tradeable) g_tradeable_trend++;

   WriteState(state, tradeable);
   if(tradeable)
      PrintFormat("MARKET_MAP FILTER %s %s confidence=%.1f strength=%.1f "
                  "liquidity=%.1f exhaustion=%.1f",
                  MarketMapDirectionName(state.direction),
                  MarketMapRegimeName(state.regime),
                  state.state_confidence, state.strength_score,
                  state.liquidity_score, state.exhaustion_score);
}

double OnTester()
{
   if(g_states <= 0)
      return 0.0;
   return 100.0 * g_tradeable_trend / g_states;
}
