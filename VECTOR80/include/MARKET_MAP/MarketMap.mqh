#ifndef MARKET_MAP_MQH
#define MARKET_MAP_MQH

#include "MarketMapTypes.mqh"
#include "MarketMapTime.mqh"
#include "MarketMapHeatmap.mqh"

class CMarketMap
{
private:
   string m_symbol;
   ENUM_TIMEFRAMES m_tf;
   ENUM_MARKET_MAP_MODE m_mode;
   double m_pip;
   int m_ema20_m5;
   int m_ema50_m5;
   int m_ema200_m5;
   int m_rsi_m5;
   int m_atr_m5;
   int m_adx_m5;
   int m_ema20_m15;
   int m_ema50_m15;
   int m_ema50_h1;
   int m_ema200_h1;
   bool m_use_live_broker_offset;
   int m_live_broker_offset_seconds;
   MarketMapState m_state;

   datetime BrokerToUtc(datetime broker_time)
   {
      if(m_use_live_broker_offset)
         return broker_time - m_live_broker_offset_seconds;
      return MMBrokerToUtc(broker_time);
   }

   double Clamp(double value, double low, double high)
   {
      return MathMax(low, MathMin(high, value));
   }

   double Signed(double value)
   {
      if(value > 0.0) return 1.0;
      if(value < 0.0) return -1.0;
      return 0.0;
   }

   double Buffer(int handle, int buffer, int shift)
   {
      double values[1];
      if(handle == INVALID_HANDLE || CopyBuffer(handle, buffer, shift, 1, values) != 1)
         return EMPTY_VALUE;
      return values[0];
   }

   double CloseAt(ENUM_TIMEFRAMES tf, int shift)
   {
      double values[1];
      if(CopyClose(m_symbol, tf, shift, 1, values) != 1)
         return EMPTY_VALUE;
      return values[0];
   }

   double TrendScore()
   {
      double close_m5 = CloseAt(PERIOD_M5, 1);
      double e20 = Buffer(m_ema20_m5, 0, 1);
      double e50 = Buffer(m_ema50_m5, 0, 1);
      double e200 = Buffer(m_ema200_m5, 0, 1);
      double m15_20 = Buffer(m_ema20_m15, 0, 1);
      double m15_50 = Buffer(m_ema50_m15, 0, 1);
      double h1_50 = Buffer(m_ema50_h1, 0, 1);
      double h1_200 = Buffer(m_ema200_h1, 0, 1);
      if(close_m5 == EMPTY_VALUE || e20 == EMPTY_VALUE || e50 == EMPTY_VALUE ||
         e200 == EMPTY_VALUE || m15_20 == EMPTY_VALUE || m15_50 == EMPTY_VALUE ||
         h1_50 == EMPTY_VALUE || h1_200 == EMPTY_VALUE)
         return 0.0;

      double score = 0.0;
      score += close_m5 > e20 ? 12.0 : -12.0;
      score += e20 > e50 ? 16.0 : -16.0;
      score += e50 > e200 ? 20.0 : -20.0;
      score += m15_20 > m15_50 ? 22.0 : -22.0;
      score += h1_50 > h1_200 ? 30.0 : -30.0;
      return Clamp(score, -100.0, 100.0);
   }

   double MomentumScore(double atr_price)
   {
      double c1 = CloseAt(PERIOD_M5, 1);
      double c2 = CloseAt(PERIOD_M5, 2);
      double c4 = CloseAt(PERIOD_M5, 4);
      double c13 = CloseAt(PERIOD_M5, 13);
      double rsi = Buffer(m_rsi_m5, 0, 1);
      if(c1 == EMPTY_VALUE || c2 == EMPTY_VALUE || c4 == EMPTY_VALUE ||
         c13 == EMPTY_VALUE || atr_price <= 0.0 || rsi == EMPTY_VALUE)
         return 0.0;
      double normalized = 25.0 * (c1 - c2) / atr_price;
      normalized += 35.0 * (c1 - c4) / atr_price;
      normalized += 25.0 * (c1 - c13) / atr_price;
      normalized += (rsi - 50.0) * 0.3;
      return Clamp(normalized, -100.0, 100.0);
   }

   ENUM_MARKET_MAP_DIRECTION Direction(double net_atr)
   {
      if(net_atr >= 0.75) return MM_DIRECTION_BULL;
      if(net_atr <= -0.75) return MM_DIRECTION_BEAR;
      return MM_DIRECTION_NEUTRAL;
   }

   ENUM_MARKET_MAP_STRUCTURE Structure(double net_atr, double efficiency)
   {
      if(MathAbs(net_atr) >= 1.25 && efficiency >= 0.40)
         return MM_STRUCTURE_TREND;
      if(MathAbs(net_atr) >= 0.75 && efficiency < 0.40)
         return MM_STRUCTURE_CHOP;
      return MM_STRUCTURE_RANGE;
   }

   ENUM_MARKET_MAP_VOLATILITY_PHASE VolatilityPhase(double expansion)
   {
      if(expansion <= 0.70) return MM_VOL_PHASE_COMPRESSION;
      if(expansion >= 1.35) return MM_VOL_PHASE_EXPANSION;
      return MM_VOL_PHASE_NORMAL;
   }

   ENUM_MARKET_MAP_VOLATILITY Volatility(double atr_pips, double expected_range)
   {
      if(atr_pips <= 0.0 || expected_range <= 0.0)
         return MM_VOL_UNKNOWN;
      double ratio = atr_pips / expected_range;
      if(ratio < 0.07) return MM_VOL_LOW;
      if(ratio < 0.14) return MM_VOL_NORMAL;
      if(ratio < 0.24) return MM_VOL_HIGH;
      return MM_VOL_EXTREME;
   }

   ENUM_MARKET_MAP_REGIME Regime(double net_atr, double efficiency,
                                 ENUM_MARKET_MAP_DIRECTION direction,
                                 ENUM_MARKET_MAP_STRUCTURE structure,
                                 ENUM_MARKET_MAP_VOLATILITY_PHASE phase)
   {
      if(net_atr >= 2.50 && efficiency >= 0.55) return MM_REGIME_STRONG_BULL;
      if(net_atr <= -2.50 && efficiency >= 0.55) return MM_REGIME_STRONG_BEAR;
      if(direction == MM_DIRECTION_BULL && structure == MM_STRUCTURE_TREND)
         return MM_REGIME_BULL_TREND;
      if(direction == MM_DIRECTION_BEAR && structure == MM_STRUCTURE_TREND)
         return MM_REGIME_BEAR_TREND;
      if(direction == MM_DIRECTION_BULL && structure == MM_STRUCTURE_CHOP)
         return MM_REGIME_BULL_CHOP;
      if(direction == MM_DIRECTION_BEAR && structure == MM_STRUCTURE_CHOP)
         return MM_REGIME_BEAR_CHOP;
      if(direction == MM_DIRECTION_NEUTRAL && phase == MM_VOL_PHASE_COMPRESSION)
         return MM_REGIME_COMPRESSION;
      if(direction == MM_DIRECTION_NEUTRAL && phase == MM_VOL_PHASE_EXPANSION)
         return MM_REGIME_EXPANSION;
      return MM_REGIME_RANGE;
   }

   void ClearForecast(MarketMapForecast &forecast, int minutes)
   {
      ZeroMemory(forecast);
      forecast.minutes = minutes;
      forecast.valid = false;
      forecast.status = MM_FORECAST_UNAVAILABLE;
      forecast.source = "NONE";
      forecast.model_version = "";
   }

public:
   CMarketMap()
   {
      m_ema20_m5 = INVALID_HANDLE;
      m_ema50_m5 = INVALID_HANDLE;
      m_ema200_m5 = INVALID_HANDLE;
      m_rsi_m5 = INVALID_HANDLE;
      m_atr_m5 = INVALID_HANDLE;
      m_adx_m5 = INVALID_HANDLE;
      m_ema20_m15 = INVALID_HANDLE;
      m_ema50_m15 = INVALID_HANDLE;
      m_ema50_h1 = INVALID_HANDLE;
      m_ema200_h1 = INVALID_HANDLE;
      m_use_live_broker_offset = false;
      m_live_broker_offset_seconds = 0;
   }

   void SetLiveBrokerUtcOffset(int offset_seconds)
   {
      if(MathAbs(offset_seconds) > 14 * 3600)
         return;
      m_live_broker_offset_seconds = offset_seconds;
      m_use_live_broker_offset = true;
   }

   void UseHistoricalBrokerTime()
   {
      m_use_live_broker_offset = false;
   }

   bool Init(string symbol, ENUM_TIMEFRAMES tf=PERIOD_M5,
             ENUM_MARKET_MAP_MODE mode=MM_MODE_NATIVE)
   {
      m_symbol = symbol;
      m_tf = tf;
      m_mode = mode;
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      m_pip = (digits == 3 || digits == 5) ? point * 10.0 : point;

      m_ema20_m5 = iMA(symbol, PERIOD_M5, 20, 0, MODE_EMA, PRICE_CLOSE);
      m_ema50_m5 = iMA(symbol, PERIOD_M5, 50, 0, MODE_EMA, PRICE_CLOSE);
      m_ema200_m5 = iMA(symbol, PERIOD_M5, 200, 0, MODE_EMA, PRICE_CLOSE);
      m_rsi_m5 = iRSI(symbol, PERIOD_M5, 14, PRICE_CLOSE);
      m_atr_m5 = iATR(symbol, PERIOD_M5, 14);
      m_adx_m5 = iADX(symbol, PERIOD_M5, 14);
      m_ema20_m15 = iMA(symbol, PERIOD_M15, 20, 0, MODE_EMA, PRICE_CLOSE);
      m_ema50_m15 = iMA(symbol, PERIOD_M15, 50, 0, MODE_EMA, PRICE_CLOSE);
      m_ema50_h1 = iMA(symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
      m_ema200_h1 = iMA(symbol, PERIOD_H1, 200, 0, MODE_EMA, PRICE_CLOSE);

      return m_ema20_m5 != INVALID_HANDLE &&
             m_ema50_m5 != INVALID_HANDLE &&
             m_ema200_m5 != INVALID_HANDLE &&
             m_rsi_m5 != INVALID_HANDLE &&
             m_atr_m5 != INVALID_HANDLE &&
             m_adx_m5 != INVALID_HANDLE &&
             m_ema20_m15 != INVALID_HANDLE &&
             m_ema50_m15 != INVALID_HANDLE &&
             m_ema50_h1 != INVALID_HANDLE &&
             m_ema200_h1 != INVALID_HANDLE;
   }

   void Release()
   {
      int handles[] = {m_ema20_m5,m_ema50_m5,m_ema200_m5,m_rsi_m5,m_atr_m5,
                       m_adx_m5,m_ema20_m15,m_ema50_m15,m_ema50_h1,m_ema200_h1};
      for(int i = 0; i < ArraySize(handles); i++)
         if(handles[i] != INVALID_HANDLE)
            IndicatorRelease(handles[i]);
   }

   bool Update()
   {
      ZeroMemory(m_state);
      m_state.symbol = m_symbol;
      m_state.version = MARKET_MAP_VERSION;
      m_state.source = m_mode == MM_MODE_NATIVE ?
                       "MT5_CURRENT_STATE" : "MT5_CURRENT_STATE_ENHANCED_RESERVED";

      MqlRates rates[];
      ArraySetAsSeries(rates, true);
      if(CopyRates(m_symbol, PERIOD_M5, 1, 61, rates) < 61)
         return false;
      m_state.timestamp = rates[0].time;
      m_state.data_age_seconds = (int)MathMax(0, TimeCurrent() - rates[0].time);

      double atr_price = Buffer(m_atr_m5, 0, 1);
      double adx = Buffer(m_adx_m5, 0, 1);
      double plus_di = Buffer(m_adx_m5, 1, 1);
      double minus_di = Buffer(m_adx_m5, 2, 1);
      if(atr_price == EMPTY_VALUE || atr_price <= 0.0 || adx == EMPTY_VALUE ||
         plus_di == EMPTY_VALUE || minus_di == EMPTY_VALUE)
         return false;

      double path = 0.0;
      double path_high = rates[0].high;
      double path_low = rates[0].low;
      double current_range_sum = 0.0;
      double prior_range_sum = 0.0;
      double current_volume_sum = 0.0;
      double prior_volume_sum = 0.0;
      for(int i = 0; i < 12; i++)
      {
         path += MathAbs(rates[i].close - rates[i + 1].close);
         path_high = MathMax(path_high, rates[i].high);
         path_low = MathMin(path_low, rates[i].low);
         current_range_sum += rates[i].high - rates[i].low;
         current_volume_sum += (double)rates[i].tick_volume;
      }
      for(int i = 12; i < 60; i++)
      {
         prior_range_sum += rates[i].high - rates[i].low;
         prior_volume_sum += (double)rates[i].tick_volume;
      }

      double net_price = rates[0].close - rates[12].close;
      double average_current_range = current_range_sum / 12.0;
      double average_prior_range = prior_range_sum / 48.0;
      double average_current_volume = current_volume_sum / 12.0;
      double average_prior_volume = prior_volume_sum / 48.0;

      m_state.atr_pips = atr_price / m_pip;
      double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
      m_state.spread_pips = MathMax(0.0, ask - bid) / m_pip;
      m_state.net_atr = net_price / atr_price;
      m_state.path_efficiency = MathAbs(net_price) / MathMax(path, m_pip * 0.1);
      m_state.range_atr = (path_high - path_low) / atr_price;
      m_state.range_expansion = average_current_range /
                                MathMax(average_prior_range, m_pip * 0.1);
      m_state.volume_ratio = average_current_volume /
                             MathMax(average_prior_volume, 1.0);
      m_state.spread_atr_ratio = m_state.spread_pips /
                                 MathMax(m_state.atr_pips, 0.1);

      m_state.direction = Direction(m_state.net_atr);
      m_state.structure = Structure(m_state.net_atr, m_state.path_efficiency);
      m_state.volatility_phase = VolatilityPhase(m_state.range_expansion);
      m_state.direction_score = Clamp(m_state.net_atr / 2.50 * 100.0,
                                      -100.0, 100.0);
      m_state.structure_score = Clamp(Signed(m_state.net_atr) *
                                      m_state.path_efficiency * 100.0,
                                      -100.0, 100.0);
      double displacement_strength = Clamp(MathAbs(m_state.net_atr) / 2.50,
                                           0.0, 1.0);
      double efficiency_strength = Clamp(m_state.path_efficiency / 0.55,
                                         0.0, 1.0);
      m_state.strength_score = 100.0 *
                               MathSqrt(displacement_strength * efficiency_strength);

      m_state.trend_score = TrendScore();
      m_state.momentum_score = MomentumScore(atr_price);
      m_state.pressure_score = Clamp((plus_di - minus_di) * 2.5, -100.0, 100.0);
      m_state.trend_quality = Clamp(adx * 2.0, 0.0, 100.0);

      double expected_range = 0.0;
      double heatmap_direction = 0.0;
      bool has_heatmap = MMHeatmapValues(BrokerToUtc(rates[0].time),
                                         heatmap_direction, expected_range);
      m_state.historical_score = has_heatmap ?
                                 Clamp(heatmap_direction * 4.0, -50.0, 50.0) : 0.0;
      m_state.historical_range_pips = has_heatmap ? expected_range : 0.0;
      m_state.volatility = Volatility(m_state.atr_pips, expected_range);

      double volume_quality = Clamp(50.0 + (m_state.volume_ratio - 1.0) * 50.0,
                                    0.0, 100.0);
      double spread_quality = Clamp(100.0 - m_state.spread_atr_ratio * 250.0,
                                    0.0, 100.0);
      m_state.liquidity_score = 0.55 * volume_quality + 0.45 * spread_quality;

      double recent_move = MathAbs(rates[0].close - rates[3].close) / atr_price;
      double prior_move = MathAbs(rates[3].close - rates[6].close) / atr_price;
      double slowdown = Clamp((prior_move - recent_move) /
                              MathMax(prior_move, 0.10), 0.0, 1.0);
      double last_range = MathMax(rates[0].high - rates[0].low, m_pip * 0.1);
      double rejection = 0.0;
      if(m_state.net_atr > 0.0)
         rejection = (rates[0].high - MathMax(rates[0].open, rates[0].close)) /
                     last_range;
      else if(m_state.net_atr < 0.0)
         rejection = (MathMin(rates[0].open, rates[0].close) - rates[0].low) /
                     last_range;
      double extension = Clamp((MathAbs(m_state.net_atr) - 1.50) / 2.50, 0.0, 1.0);
      m_state.exhaustion_score = 100.0 *
                                 (0.45 * extension +
                                  0.35 * slowdown +
                                  0.20 * Clamp(rejection, 0.0, 1.0));

      double raw = 0.45 * m_state.direction_score +
                   0.25 * m_state.trend_score +
                   0.15 * m_state.momentum_score +
                   0.15 * m_state.pressure_score;
      m_state.feel = Clamp(raw, -100.0, 100.0);

      double direction_sign = Signed(m_state.direction_score);
      double agreement_count = 0.0;
      if(direction_sign == 0.0)
         agreement_count = MathAbs(m_state.trend_score) < 25.0 ? 1.0 : 0.0;
      else
      {
         if(Signed(m_state.trend_score) == direction_sign) agreement_count += 1.0;
         if(Signed(m_state.momentum_score) == direction_sign) agreement_count += 1.0;
         if(Signed(m_state.pressure_score) == direction_sign) agreement_count += 1.0;
         agreement_count /= 3.0;
      }
      double classification_clarity = Clamp(
         45.0 * MathAbs(m_state.net_atr) / 1.25 +
         35.0 * m_state.path_efficiency / 0.40 +
         20.0 * MathAbs(m_state.range_expansion - 1.0) / 0.35,
         0.0, 100.0);
      m_state.data_quality = Clamp(0.65 * spread_quality +
                                   0.35 * Clamp(m_state.volume_ratio * 70.0,
                                                0.0, 100.0),
                                   0.0, 100.0);
      m_state.state_confidence = Clamp(0.45 * classification_clarity +
                                       0.35 * agreement_count * 100.0 +
                                       0.20 * m_state.data_quality,
                                       0.0, 100.0);
      m_state.confidence = m_state.state_confidence;

      double prior_net_atr = (rates[3].close - rates[15].close) / atr_price;
      ENUM_MARKET_MAP_DIRECTION prior_direction = Direction(prior_net_atr);
      if(m_state.exhaustion_score >= 65.0 &&
         m_state.direction != MM_DIRECTION_NEUTRAL)
         m_state.transition = MM_TRANSITION_EXHAUSTION;
      else if((prior_direction != m_state.direction &&
               prior_direction != MM_DIRECTION_NEUTRAL) ||
              (m_state.state_confidence < 35.0 &&
               m_state.structure != MM_STRUCTURE_RANGE))
         m_state.transition = MM_TRANSITION_CHANGING;
      else if(prior_direction == MM_DIRECTION_NEUTRAL &&
              m_state.direction != MM_DIRECTION_NEUTRAL)
         m_state.transition = MM_TRANSITION_DEVELOPING;
      else
         m_state.transition = MM_TRANSITION_STABLE;

      m_state.regime = Regime(m_state.net_atr, m_state.path_efficiency,
                              m_state.direction, m_state.structure,
                              m_state.volatility_phase);

      m_state.forecast_available = false;
      m_state.forecast_source = "NONE";
      m_state.forecast_model_version = "";
      ClearForecast(m_state.h5, 5);
      ClearForecast(m_state.h15, 15);
      ClearForecast(m_state.h30, 30);
      ClearForecast(m_state.h60, 60);
      MqlDateTime utc;
      TimeToStruct(BrokerToUtc(rates[0].time), utc);
      int remaining_minutes = MathMax(5, (24 * 60) - (utc.hour * 60 + utc.min));
      ClearForecast(m_state.rest_of_day, remaining_minutes);

      m_state.valid = true;
      return true;
   }

   bool GetState(MarketMapState &state)
   {
      state = m_state;
      return state.valid;
   }
};

#endif
