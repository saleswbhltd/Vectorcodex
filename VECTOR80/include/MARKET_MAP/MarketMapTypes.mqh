#ifndef MARKET_MAP_TYPES_MQH
#define MARKET_MAP_TYPES_MQH

#define MARKET_MAP_VERSION "0.2.0"

enum ENUM_MARKET_MAP_MODE
{
   MM_MODE_NATIVE = 0,
   MM_MODE_ENHANCED = 1
};

enum ENUM_MARKET_MAP_DIRECTION
{
   MM_DIRECTION_UNKNOWN = 0,
   MM_DIRECTION_BEAR,
   MM_DIRECTION_NEUTRAL,
   MM_DIRECTION_BULL
};

enum ENUM_MARKET_MAP_STRUCTURE
{
   MM_STRUCTURE_UNKNOWN = 0,
   MM_STRUCTURE_RANGE,
   MM_STRUCTURE_CHOP,
   MM_STRUCTURE_TREND
};

enum ENUM_MARKET_MAP_VOLATILITY_PHASE
{
   MM_VOL_PHASE_UNKNOWN = 0,
   MM_VOL_PHASE_COMPRESSION,
   MM_VOL_PHASE_NORMAL,
   MM_VOL_PHASE_EXPANSION
};

enum ENUM_MARKET_MAP_TRANSITION
{
   MM_TRANSITION_UNKNOWN = 0,
   MM_TRANSITION_STABLE,
   MM_TRANSITION_DEVELOPING,
   MM_TRANSITION_CHANGING,
   MM_TRANSITION_EXHAUSTION
};

enum ENUM_MARKET_MAP_FORECAST_STATUS
{
   MM_FORECAST_UNAVAILABLE = 0,
   MM_FORECAST_RESEARCH,
   MM_FORECAST_VALIDATED
};

enum ENUM_MARKET_MAP_REGIME
{
   MM_REGIME_UNKNOWN = 0,
   MM_REGIME_STRONG_BEAR,
   MM_REGIME_BEAR_TREND,
   MM_REGIME_BEAR_CHOP,
   MM_REGIME_RANGE,
   MM_REGIME_BULL_CHOP,
   MM_REGIME_BULL_TREND,
   MM_REGIME_STRONG_BULL,
   MM_REGIME_COMPRESSION,
   MM_REGIME_EXPANSION
};

enum ENUM_MARKET_MAP_VOLATILITY
{
   MM_VOL_UNKNOWN = 0,
   MM_VOL_LOW,
   MM_VOL_NORMAL,
   MM_VOL_HIGH,
   MM_VOL_EXTREME
};

struct MarketMapForecast
{
   int    minutes;
   bool   valid;
   ENUM_MARKET_MAP_FORECAST_STATUS status;
   string source;
   string model_version;
   double direction;
   double confidence;
   double p_up;
   double p_flat;
   double p_down;
   double expected_pips;
   double expected_range_pips;
};

struct MarketMapState
{
   datetime timestamp;
   bool     valid;
   int      data_age_seconds;
   string   symbol;
   string   version;
   string   source;

   // Compatibility fields retained for existing EAs.
   double   feel;
   double   confidence;
   double   trend_score;
   double   momentum_score;
   double   pressure_score;
   double   structure_score;
   double   historical_score;
   double   trend_quality;
   double   atr_pips;
   double   spread_pips;

   // Current-state analyzer axes and diagnostics.
   ENUM_MARKET_MAP_DIRECTION direction;
   ENUM_MARKET_MAP_STRUCTURE structure;
   ENUM_MARKET_MAP_VOLATILITY_PHASE volatility_phase;
   ENUM_MARKET_MAP_TRANSITION transition;
   double   direction_score;
   double   strength_score;
   double   liquidity_score;
   double   exhaustion_score;
   double   state_confidence;
   double   data_quality;
   double   net_atr;
   double   path_efficiency;
   double   range_atr;
   double   range_expansion;
   double   volume_ratio;
   double   spread_atr_ratio;
   double   historical_range_pips;

   ENUM_MARKET_MAP_REGIME regime;
   ENUM_MARKET_MAP_VOLATILITY volatility;

   bool     forecast_available;
   string   forecast_source;
   string   forecast_model_version;
   MarketMapForecast h5;
   MarketMapForecast h15;
   MarketMapForecast h30;
   MarketMapForecast h60;
   MarketMapForecast rest_of_day;
};

string MarketMapDirectionName(ENUM_MARKET_MAP_DIRECTION value)
{
   switch(value)
   {
      case MM_DIRECTION_BEAR: return "BEAR";
      case MM_DIRECTION_NEUTRAL: return "NEUTRAL";
      case MM_DIRECTION_BULL: return "BULL";
      default: return "UNKNOWN";
   }
}

string MarketMapStructureName(ENUM_MARKET_MAP_STRUCTURE value)
{
   switch(value)
   {
      case MM_STRUCTURE_RANGE: return "RANGE";
      case MM_STRUCTURE_CHOP: return "CHOP";
      case MM_STRUCTURE_TREND: return "TREND";
      default: return "UNKNOWN";
   }
}

string MarketMapVolatilityPhaseName(ENUM_MARKET_MAP_VOLATILITY_PHASE value)
{
   switch(value)
   {
      case MM_VOL_PHASE_COMPRESSION: return "COMPRESSION";
      case MM_VOL_PHASE_NORMAL: return "NORMAL";
      case MM_VOL_PHASE_EXPANSION: return "EXPANSION";
      default: return "UNKNOWN";
   }
}

string MarketMapTransitionName(ENUM_MARKET_MAP_TRANSITION value)
{
   switch(value)
   {
      case MM_TRANSITION_STABLE: return "STABLE";
      case MM_TRANSITION_DEVELOPING: return "DEVELOPING";
      case MM_TRANSITION_CHANGING: return "CHANGING";
      case MM_TRANSITION_EXHAUSTION: return "EXHAUSTION";
      default: return "UNKNOWN";
   }
}

string MarketMapForecastStatusName(ENUM_MARKET_MAP_FORECAST_STATUS value)
{
   switch(value)
   {
      case MM_FORECAST_RESEARCH: return "RESEARCH_ONLY";
      case MM_FORECAST_VALIDATED: return "VALIDATED";
      default: return "UNAVAILABLE";
   }
}

string MarketMapRegimeName(ENUM_MARKET_MAP_REGIME value)
{
   switch(value)
   {
      case MM_REGIME_STRONG_BEAR: return "STRONG_BEAR_TREND";
      case MM_REGIME_BEAR_TREND: return "BEAR_TREND";
      case MM_REGIME_BEAR_CHOP: return "BEAR_CHOP";
      case MM_REGIME_RANGE: return "RANGE";
      case MM_REGIME_BULL_CHOP: return "BULL_CHOP";
      case MM_REGIME_BULL_TREND: return "BULL_TREND";
      case MM_REGIME_STRONG_BULL: return "STRONG_BULL_TREND";
      case MM_REGIME_COMPRESSION: return "COMPRESSION";
      case MM_REGIME_EXPANSION: return "VOLATILE_RANGE";
      default: return "UNKNOWN";
   }
}

string MarketMapVolatilityName(ENUM_MARKET_MAP_VOLATILITY value)
{
   switch(value)
   {
      case MM_VOL_LOW: return "LOW";
      case MM_VOL_NORMAL: return "NORMAL";
      case MM_VOL_HIGH: return "HIGH";
      case MM_VOL_EXTREME: return "EXTREME";
      default: return "UNKNOWN";
   }
}

#endif
