# MARKET_MAP Research Index

This document is the project-side pointer to the durable MARKET_MAP research
archive.

## Canonical Locations

- Active implementation:
  `/home/cmake/Vectorcodex/VECTOR80`
- Shared research archive:
  `/home/cmake/VectorShared/research/MARKET_MAP`
- Windows/WSL path:
  `\\wsl.localhost\Ubuntu\home\cmake\VectorShared\research\MARKET_MAP`
- Calibrated source panel:
  `/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz`
- Historical tick archive:
  `/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024`
- Broker-adjusted M5 feature archive:
  `/home/cmake/VectorShared/research/dukascopy/EURUSD/2023_2024/broker_adjusted`

Tick archive details and checksums are documented in
`docs/DUKASCOPY_TICK_ARCHIVE.md`.

The active project contains working copies. The shared archive contains the
study snapshot and reproducibility material that should be used to recover the
research later.

## Current Implementation

MARKET_MAP v0.2 is a current-state analyzer implemented in:

- `include/MARKET_MAP/MarketMap.mqh`
- `include/MARKET_MAP/MarketMapTypes.mqh`
- `indicators/MARKET_MAP_Dashboard.mq5`
- `docs/MARKET_MAP_SPEC.md`

It publishes direction, structure, volatility phase, transition, strength,
liquidity, exhaustion and evidence-quality diagnostics from completed M5 bars.
The trailing-hour direction/structure/volatility taxonomy uses the same
thresholds as the regime study. Forecast fields are reserved in the public API
but explicitly unavailable because the completed studies did not validate a
live short-horizon forecast model.

## Studies

### Trend and Regime Study

Primary report:

`/home/cmake/VectorShared/research/MARKET_MAP/reports/MARKET_MAP_REGIME_STUDY.md`

It defines and tests separate current-state axes:

- direction: bull, bear, neutral;
- structure: trend, chop, range;
- volatility phase: compression, normal, expansion;
- nine-class composite regime.

The study trains through December 31, 2025 and evaluates March 1 through
June 1, 2026. It includes confidence/coverage curves, monthly stability,
transition accuracy and state-duration analysis.

### Indicator and Family Studies

- `reports/MARKET_MAP_INDICATOR_REPORT.md`
- `reports/MARKET_MAP_FAMILY_REPORT.md`
- `reports/MARKET_MAP_MODEL_REPORT.md`

These studies distinguish current-state measurement from future directional
forecasting. They also document the corrected causal treatment of H1 inputs.

### Historical Day/Time Heatmaps

- Interactive map:
  `/home/cmake/VectorShared/research/MARKET_MAP/heatmaps/EURUSD_MARKET_MAP_HEATMAPS.html`
- Three-year 15-minute/5-minute map:
  `/home/cmake/VectorShared/research/MARKET_MAP/heatmaps/EURUSD_MARKET_MAP_HISTORICAL_ZONES_2023_2025.html`
- Study report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/MARKET_MAP_HEATMAP_REPORT.md`
- Zone table:
  `/home/cmake/VectorShared/research/MARKET_MAP/data/MARKET_MAP_heatmap_zones.csv`

The self-contained HTML provides hourly and 30-minute UTC maps for direction,
structure, volatility and strength, plus a cross-map overlap view. It also
documents why the older `EURUSD_M5_dow_heatmap.html` is not authoritative:
that file used a partial-year broker-clock dataset labelled as UTC.

The three-year version preserves the Historical Zones design and adds
2023/2024/2025 selection plus primary 15-minute and exploratory 5-minute
resolutions. Each year is ranked independently with the same formulas.

### Advanced Tradability Zones

- Interactive 15-minute map:
  `/home/cmake/VectorShared/research/MARKET_MAP/heatmaps/EURUSD_MARKET_MAP_TRADABILITY.html`
- Report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/MARKET_MAP_TRADABILITY_STUDY.md`
- Validation table:
  `/home/cmake/VectorShared/research/MARKET_MAP/data/MARKET_MAP_tradability_validation.csv`

This study combines tick volume, bid/ask volume, liquidity, spread relative to
ATR, path cleanliness and target-before-stop outcomes. Fifteen-minute zones are
primary and 30-minute parent zones provide a robustness check. The map can
switch between tradability, volume, liquidity, spread and cleanliness layers.

### 2024 Q4 Historical Holdout

- Report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/MARKET_MAP_TRADABILITY_2024Q4_VALIDATION.md`
- Full validation table:
  `/home/cmake/VectorShared/research/MARKET_MAP/data/MARKET_MAP_tradability_2024Q4_validation.csv`

This independent October-December 2024 check freezes the calendar-2025 zone
definitions and applies them to the broker-adjusted historical archive. The
broad 88-zone candidate set had negative mean holdout edge, while 7 of the 10
previously robust zones remained positive with a weighted `+0.350` pip edge.
It is reverse-time historical validation, not genuine broker-feed forward OOS.

### Trend Continuation and Termination

- Report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/MARKET_MAP_TREND_TERMINATION_2024Q4.md`
- Metrics and conditional tables:
  `/home/cmake/VectorShared/research/MARKET_MAP/data`

This study trains through September 2024 and tests October-December 2024.
Contiguous active BULL/BEAR movements are deduplicated into episodes, then
classified by whether an ATR-scaled continuation target or retracement boundary
is reached first over 15, 30 and 60 minutes. General termination prediction is
near chance; conditional strength/volatility/time combinations are retained as
research priors with sample-size warnings.

### VECTOR80 Adaptive Threshold Study

- Report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/VECTOR80_MARKET_MAP_THRESHOLD_STUDY.md`
- Policy results and below-threshold candidate audit:
  `/home/cmake/VectorShared/research/MARKET_MAP/data`

This study freezes the published VECTOR80 baseline and tests whether current
MARKET_MAP direction, structure and volatility can safely permit lower model
thresholds. Policies are discovered on March-April 2026 and checked on the
untouched May 1-June 1, 2026 holdout. Holdout is not used to select a policy.

### VECTOR80 Clock-Time Threshold Study

- Report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/VECTOR80_TIME_THRESHOLD_STUDY.md`
- Full policy grid, candidate audit and selected shadow additions:
  `/home/cmake/VectorShared/research/MARKET_MAP/data`

This separate study tests UTC time windows directly. It finds a small
forward-monitoring candidate at `00:00-02:00 UTC`, while late-afternoon
threshold reductions perform poorly. The candidate is not enabled in the EA
because only eight additions were observed after testing many windows.

### VECTOR80 15-Minute Threshold Zones

- Interactive all-day map:
  `/home/cmake/VectorShared/research/MARKET_MAP/heatmaps/EURUSD_VECTOR80_15M_THRESHOLD_ZONES.html`
- Report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/VECTOR80_15M_THRESHOLD_ZONES.md`
- Full 96-slot results and summary:
  `/home/cmake/VectorShared/research/MARKET_MAP/data`

All 96 UTC quarter-hour slots are evaluated at six threshold reductions, with
March-April discovery and May holdout shown separately. Exact slots are sparse:
the repeated-positive cells have only two total additions each. The map is a
diagnostic for neighboring-zone research, not an EA threshold schedule.

### 2023 vs 2024 Annual Tradability Drift

- Original-style standalone 2023 map:
  `/home/cmake/VectorShared/research/MARKET_MAP/heatmaps/EURUSD_MARKET_MAP_TRADABILITY_2023.html`
- Original-style standalone 2024 map:
  `/home/cmake/VectorShared/research/MARKET_MAP/heatmaps/EURUSD_MARKET_MAP_TRADABILITY_2024.html`
- Interactive comparison:
  `/home/cmake/VectorShared/research/MARKET_MAP/heatmaps/EURUSD_MARKET_MAP_TRADABILITY_2023_2024.html`
- Report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/MARKET_MAP_TRADABILITY_2023_2024_COMPARISON.md`
- Annual zones and comparison tables:
  `/home/cmake/VectorShared/research/MARKET_MAP/data`

Both calendar years use the parity-audited canonical tick/panel/calibration
pipeline and the same advanced tradability formulas. Quality ranks are
relatively stable, but exact parent-confirmed zones and strategy archetypes
rotate materially. The standalone annual HTML files use the exact original
five-layer renderer; the comparison HTML adds a separate drift view.

## Reproduction

Run from `/home/cmake/Vectorcodex/VECTOR80`:

```bash
python3 scripts/scan_market_map_indicators.py
python3 scripts/test_market_map_indicator_families.py
python3 scripts/train_market_map_models.py
python3 scripts/study_market_regimes.py
python3 scripts/build_market_map_heatmaps.py
python3 scripts/build_three_year_historical_zones.py
python3 scripts/study_tradability_zones.py
python3 scripts/validate_tradability_historical_holdout.py
python3 scripts/compare_yearly_tradability_maps.py
python3 scripts/render_yearly_tradability_maps.py
python3 scripts/study_trend_termination.py
python3 -m unittest discover -s tests -v
```

The scripts default to the calibrated panel in `VectorShared/research`.

## Safety

- All research timestamps are UTC.
- RoboForex timestamps require exact `Europe/Helsinki` EET/EEST conversion.
- H1 features must reference the last fully completed H1 candle.
- Research models are not connected to live trading.
- Current-state classification accuracy must not be presented as future-price
  forecast accuracy.
