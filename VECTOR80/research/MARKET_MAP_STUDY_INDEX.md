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

Tick archive details and checksums are documented in
`docs/DUKASCOPY_TICK_ARCHIVE.md`.

The active project contains working copies. The shared archive contains the
study snapshot and reproducibility material that should be used to recover the
research later.

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
- Study report:
  `/home/cmake/VectorShared/research/MARKET_MAP/reports/MARKET_MAP_HEATMAP_REPORT.md`
- Zone table:
  `/home/cmake/VectorShared/research/MARKET_MAP/data/MARKET_MAP_heatmap_zones.csv`

The self-contained HTML provides hourly and 30-minute UTC maps for direction,
structure, volatility and strength, plus a cross-map overlap view. It also
documents why the older `EURUSD_M5_dow_heatmap.html` is not authoritative:
that file used a partial-year broker-clock dataset labelled as UTC.

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

## Reproduction

Run from `/home/cmake/Vectorcodex/VECTOR80`:

```bash
python3 scripts/scan_market_map_indicators.py
python3 scripts/test_market_map_indicator_families.py
python3 scripts/train_market_map_models.py
python3 scripts/study_market_regimes.py
python3 scripts/build_market_map_heatmaps.py
python3 scripts/study_tradability_zones.py
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
