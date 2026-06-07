# MARKET_MAP Research Archive

Archived from `/home/cmake/Vectorcodex/VECTOR80` on June 6, 2026.

## Directory Contents

- `reports/`: human-readable findings and research decisions.
- `heatmaps/`: self-contained interactive historical visualizations.
- `data/`: compact scans, metrics, predictions and training metadata.
- `models/`: disconnected research-only model artifacts.
- `scripts/`: exact Python study and data/time scripts.
- `tests/`: causality, target, time-conversion and regime-label tests.
- `SHA256SUMS`: checksums for every archived file.

## Primary Entry Point

Start with `reports/MARKET_MAP_REGIME_STUDY.md`, then read:

1. `reports/MARKET_MAP_INDICATOR_REPORT.md`
2. `reports/MARKET_MAP_FAMILY_REPORT.md`
3. `reports/MARKET_MAP_MODEL_REPORT.md`
4. `reports/MARKET_MAP_HEATMAP_REPORT.md`

Interactive historical maps:

`heatmaps/EURUSD_MARKET_MAP_HEATMAPS.html`

Advanced 15-minute tradability, volume and liquidity map:

`heatmaps/EURUSD_MARKET_MAP_TRADABILITY.html`

## Source Data

The large source panel is not duplicated:

`/home/cmake/VectorShared/research/EURUSD_M5_CALIBRATED_PANEL.csv.gz`

Read `/home/cmake/VectorShared/research/CALIBRATED_PANEL_README.md` before using
it. The panel combines Dukascopy history with broker-calibrated tick features.

## Key Findings

- Current direction: 82.2% continuous OOS accuracy; 94.5% at 59% coverage.
- Volatility phase: 86.4% continuous; 93.1% at 78% coverage.
- Trend/chop/range: 68.2% continuous; 88.0% at 27% coverage.
- Nine-class composite regime: 56.6% continuous; 79.0% at 15% coverage.
- Future directional forecasting remains much weaker than current-state
  identification.

## Constraints

- H1 features are shifted to the last completed H1 candle.
- Training ends December 31, 2025.
- Main out-of-sample evaluation begins March 1, 2026.
- Models are research-only and disconnected from trading.
