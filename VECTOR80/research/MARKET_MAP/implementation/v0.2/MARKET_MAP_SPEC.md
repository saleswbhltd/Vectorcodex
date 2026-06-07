# MARKET_MAP v0.2 Specification

MARKET_MAP is a reusable EURUSD current-market analyzer. It describes completed
price action but does not open, modify, or close trades. Forecast fields remain
in the API for a future validated model; version 0.2 never manufactures a
forecast from the current state.

## Time Contract

- Internal research timestamps are UTC.
- Dukascopy timestamps are already UTC.
- RoboForex tick exports use EET/EEST server timestamps.
- Broker timestamps are converted with the `Europe/Helsinki` timezone:
  UTC+2 in winter and UTC+3 in summer, using exact DST transition dates.
- `time_msc` in the existing MT5 exports mirrors the broker clock and is not an
  independent UTC source.
- Training must fail unless broker/Dukascopy M5 return Spearman correlation is
  at least `0.90` over at least `500` common bars.

## Public State

The public MQL5 API returns:

- `direction`: `BEAR`, `NEUTRAL`, or `BULL`;
- `structure`: `RANGE`, `CHOP`, or `TREND`;
- `volatility_phase`: `COMPRESSION`, `NORMAL`, or `EXPANSION`;
- `transition`: `STABLE`, `DEVELOPING`, `CHANGING`, or `EXHAUSTION`;
- `feel`: signed current directional pressure from `-100` to `+100`;
- `strength_score`, `liquidity_score`, and `exhaustion_score` from `0` to `100`;
- separate trend, momentum, pressure, structure, and historical-context scores;
- ATR, spread, volume ratio, path efficiency, range expansion, and data quality;
- source, module version, completed-bar timestamp, and data age.

`state_confidence` measures evidence clarity and agreement for the current
label. It is not forecast accuracy and is not a probability that price will
continue in the same direction.

## Research-Aligned Taxonomy

The primary state uses the trailing 12 completed M5 bars:

- direction requires a 60-minute net move of at least `0.75 x M5 ATR14`;
- trend requires at least `1.25 x ATR` net movement and path efficiency
  at least `0.40`;
- chop requires at least `0.75 x ATR` net movement with efficiency below
  `0.40`;
- strong trend requires at least `2.50 x ATR` and efficiency at least `0.55`;
- compression is current mean bar range no more than `0.70 x` its prior
  48-bar mean;
- expansion is current mean bar range at least `1.35 x` its prior 48-bar mean.

Supporting EMA, RSI, ADX/DI, tick-volume, spread, candle-rejection, and
historical time-zone measurements enrich the description. Historical direction
does not contribute to `feel`; it remains context because annual directional
zones were not stable enough to treat as a live directional signal.

## Forecast Contract

The `h5`, `h15`, `h30`, `h60`, and `rest_of_day` structures are reserved for a
future calibrated provider. In version 0.2:

- `forecast_available` is `false`;
- each forecast has `valid=false` and status `MM_FORECAST_UNAVAILABLE`;
- probabilities and expected returns remain zero;
- `MM_MODE_ENHANCED` identifies the future integration mode but does not claim
  that an enhanced provider exists.

A future provider must publish its source and model version, enforce freshness,
and distinguish research-only from validated forecasts. It must not fall back
to converting current `feel` into forecast probabilities.

## Consumer Guidance

EAs should use the axes as filters rather than as an entry command. Examples:

- trend strategy: matching direction, `TREND`, adequate strength and liquidity,
  low exhaustion;
- mean reversion: `RANGE` or `CHOP`, non-extreme expansion, controlled spread;
- no trade: low data quality, changing state, poor liquidity, or strategy/state
  mismatch.

The compatibility fields from version 0.1 remain available, but consumers
should migrate from a single `feel` threshold to the separate state axes.

### Minimal EA Integration

Create one global map, initialize it once, update it on each new M5 bar, and
release its indicator handles when the EA stops:

```cpp
#include <MARKET_MAP/MarketMap.mqh>

CMarketMap map;

int OnInit()
{
   return map.Init(_Symbol, PERIOD_M5, MM_MODE_NATIVE)
          ? INIT_SUCCEEDED : INIT_FAILED;
}

void OnDeinit(const int reason)
{
   map.Release();
}

void OnTick()
{
   if(!map.Update())
      return;

   MarketMapState state;
   if(!map.GetState(state))
      return;

   bool buy_environment =
      state.direction == MM_DIRECTION_BULL &&
      state.structure == MM_STRUCTURE_TREND &&
      state.transition != MM_TRANSITION_CHANGING &&
      state.state_confidence >= 60.0 &&
      state.liquidity_score >= 50.0 &&
      state.exhaustion_score <= 60.0;

   // Apply buy_environment to an existing entry signal. It is not an entry.
}
```

Production EAs should call `Update()` once per new M5 bar. Calling it on every
tick is valid but performs unnecessary indicator and history reads.

### Strategy Tester Harness

`ea/MARKET_MAP_Test.mq5` is a non-trading test EA. It writes one row per
completed M5 bar, prints a final state-count summary, and returns the percentage
of bars passing its example trend filter as the custom tester result.

Use EURUSD M5, a historical date range, and either every tick or one-minute
OHLC. Review `MARKET_MAP_test_states.csv` and the Strategy Tester Journal.
This validates implementation behavior and state distributions. It does not
validate trading profitability; that requires applying frozen filters to an
existing strategy and comparing OOS trade results with and without the filter.

The ready profile
`configs/MARKET_MAP_Test.EURUSD.M5.20250101_20251231.ini` performs a fast
calendar-2025 one-minute-OHLC run. Its preset writes
`MARKET_MAP_test_states_2025.csv` to the terminal Common Files folder.

## Research Evidence

The reproducible study index is `docs/MARKET_MAP_RESEARCH_INDEX.md`. The durable
archive is `/home/cmake/VectorShared/research/MARKET_MAP`.

The June 6, 2026 regime study supports publishing direction, structure, and
volatility as separate current-state axes. Separate studies found short-horizon
direction and general trend-termination forecasts too weak for live
publication. Current-state classification accuracy must never be presented as
future-price forecast accuracy.
