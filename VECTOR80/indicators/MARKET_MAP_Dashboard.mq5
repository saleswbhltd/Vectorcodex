#property indicator_chart_window
#property indicator_plots 0

#include <MARKET_MAP/MarketMap.mqh>

input ENUM_MARKET_MAP_MODE InpMode = MM_MODE_NATIVE;
input int InpUpdateSeconds = 2;

CMarketMap g_map;

int OnInit()
{
   if(!g_map.Init(_Symbol, PERIOD_M5, InpMode))
      return INIT_FAILED;
   EventSetTimer(MathMax(1, InpUpdateSeconds));
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   g_map.Release();
   Comment("");
}

void OnTimer()
{
   if(!g_map.Update())
   {
      Comment("MARKET_MAP: waiting for indicator data");
      return;
   }

   MarketMapState state;
   if(!g_map.GetState(state))
      return;

   Comment(
      "MARKET_MAP ", state.version, "\n",
      "CURRENT STATE (completed M5 bars)\n",
      "Direction: ", MarketMapDirectionName(state.direction),
      "  Structure: ", MarketMapStructureName(state.structure), "\n",
      "Vol phase: ", MarketMapVolatilityPhaseName(state.volatility_phase),
      "  Transition: ", MarketMapTransitionName(state.transition), "\n",
      "Regime: ", MarketMapRegimeName(state.regime),
      "  State confidence: ", DoubleToString(state.state_confidence, 1), "\n",
      "Feel: ", DoubleToString(state.feel, 1),
      "  Strength: ", DoubleToString(state.strength_score, 1),
      "  Exhaustion: ", DoubleToString(state.exhaustion_score, 1), "\n",
      "Trend: ", DoubleToString(state.trend_score, 1),
      "  Momentum: ", DoubleToString(state.momentum_score, 1),
      "  Pressure: ", DoubleToString(state.pressure_score, 1), "\n",
      "Net: ", DoubleToString(state.net_atr, 2), " ATR",
      "  Efficiency: ", DoubleToString(state.path_efficiency, 2),
      "  Expansion: ", DoubleToString(state.range_expansion, 2), "\n",
      "Liquidity: ", DoubleToString(state.liquidity_score, 1),
      "  Volume ratio: ", DoubleToString(state.volume_ratio, 2),
      "  Data quality: ", DoubleToString(state.data_quality, 1), "\n",
      "ATR: ", DoubleToString(state.atr_pips, 1),
      " pips  Spread: ", DoubleToString(state.spread_pips, 1),
      " pips  Historical range: ",
      DoubleToString(state.historical_range_pips, 1), "\n",
      "Forecast: ",
      state.forecast_available ? state.forecast_source : "UNAVAILABLE - RESERVED",
      "\n",
      "Source: ", state.source,
      "  Bar: ", TimeToString(state.timestamp, TIME_DATE | TIME_MINUTES)
   );
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime &time[],
                const double &open[],
                const double &high[],
                const double &low[],
                const double &close[],
                const long &tick_volume[],
                const long &volume[],
                const int &spread[])
{
   return rates_total;
}
