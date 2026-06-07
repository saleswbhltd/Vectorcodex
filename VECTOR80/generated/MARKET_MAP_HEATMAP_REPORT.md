# MARKET_MAP Historical Heatmap Study

Four historical day/time maps were generated from the DST-corrected
calibrated EURUSD M5 panel for calendar year 2025.

- Interactive HTML: `/home/cmake/Vectorcodex/VECTOR80/generated/EURUSD_MARKET_MAP_HEATMAPS.html`
- Authoritative rows: 72,576
- Period: 2025-01-02 19:55:00 through 2025-12-31 21:55:00

## Legacy Direction Map Check

- Legacy source: `/mnt/c/Users/cmake/Documents/MarketData/EURUSD_M5_2025_bars.csv`
- Legacy rows: 69762
- Legacy period: 2025-01-22 16:40:00 through 2025-12-31 20:00:00
- The legacy map is partial-year and its timestamps were labelled UTC without
  the broker/Dukascopy DST alignment contract. It is retained for comparison,
  but the regenerated calibrated UTC map is authoritative.

## Map Definitions

- Direction: mean M5 candle body divided by mean M5 range, scaled to -100..100.
- Structure: trend share minus chop share.
- Volatility: expansion share minus compression share.
- Strength: normalized trailing-hour displacement multiplied by path efficiency.
- Overlap: number of dimensions above the 65th percentile across all 120
  weekday/hour zones; overlap score is their geometric-mean percentile.

## Cross-Map Spearman Correlation

| metric | direction_score | trend_share | expansion_share | strength_score |
|---|---|---|---|---|
| direction_score | 1.0 | 0.097 | 0.045 | 0.087 |
| trend_share | 0.097 | 1.0 | 0.19 | 0.88 |
| expansion_share | 0.045 | 0.19 | 1.0 | 0.478 |
| strength_score | 0.087 | 0.88 | 0.478 | 1.0 |

Correlation measures whether whole maps overlap generally. Individual high-value
zones can overlap even when the global correlation is modest.

Structure trend share and strength are strongly related (`rho=0.880`), so their
agreement is not two fully independent confirmations. Direction is nearly independent
of structure, volatility and strength; zones where direction also aligns are therefore
the more informative overlaps.

## Strongest Hourly Overlap Zones

| day | time | direction_score | trend_share | expansion_share | strength_score | overlap_count | overlap_score |
|---|---|---|---|---|---|---|---|
| Monday | 07:00 | -6.603 | 0.37 | 0.806 | 49.248 | 4 | 96.995 |
| Tuesday | 00:00 | -4.845 | 0.405 | 0.396 | 52.728 | 4 | 89.489 |
| Friday | 14:00 | 6.396 | 0.324 | 0.459 | 45.013 | 4 | 88.748 |
| Monday | 00:00 | 6.135 | 0.351 | 0.333 | 46.521 | 4 | 87.039 |
| Wednesday | 00:00 | 6.396 | 0.314 | 0.357 | 45.314 | 4 | 84.842 |
| Thursday | 07:00 | 4.825 | 0.291 | 0.804 | 43.303 | 4 | 82.214 |
| Tuesday | 02:00 | 5.98 | 0.293 | 0.413 | 41.821 | 4 | 79.65 |
| Thursday | 13:00 | 3.454 | 0.307 | 0.562 | 42.996 | 4 | 78.948 |
| Wednesday | 14:00 | 8.528 | 0.284 | 0.389 | 41.348 | 4 | 78.515 |
| Monday | 08:00 | 3.104 | 0.309 | 0.761 | 44.47 | 3 | 81.152 |
| Thursday | 00:00 | 2.676 | 0.345 | 0.332 | 47.465 | 3 | 77.383 |
| Wednesday | 10:00 | -4.673 | 0.333 | 0.061 | 42.851 | 3 | 69.412 |
| Thursday | 14:00 | -1.997 | 0.302 | 0.392 | 41.795 | 3 | 68.481 |
| Friday | 07:00 | 6.609 | 0.252 | 0.792 | 40.363 | 3 | 66.598 |
| Wednesday | 07:00 | -0.694 | 0.343 | 0.854 | 48.541 | 3 | 66.239 |

These are historical priors, not standalone trade signals.
