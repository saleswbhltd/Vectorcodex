# MARKET_MAP Indicator Study

Indicators are oriented using data through December 31, 2025 and evaluated
on March 1 through June 1, 2026. Flat moves within 1 pip are excluded from AUC.

## Current State

### Direction

| Indicator | Family | |rho| | Signed rho |
|---|---|---:|---:|
| `bb_pctB` | candle | 0.887 | 0.887 |
| `dist_ema20_atr` | trend | 0.882 | 0.882 |
| `stoch_k` | momentum | 0.872 | 0.872 |
| `rsi14` | momentum | 0.854 | 0.854 |
| `williams_r14` | momentum | 0.853 | 0.853 |
| `stoch_d` | momentum | 0.844 | 0.844 |
| `macd_hist` | momentum | 0.770 | 0.770 |
| `dist_ema50_atr` | trend | 0.733 | 0.733 |
| `minus_di` | trend | 0.724 | -0.724 |
| `plus_di` | trend | 0.721 | 0.721 |

### Trend efficiency

| Indicator | Family | |rho| | Signed rho |
|---|---|---:|---:|
| `bb_squeeze` | volatility | 0.354 | 0.354 |
| `bb_width_pips` | volatility | 0.299 | 0.299 |
| `adx14` | trend | 0.237 | 0.237 |
| `vol_z20` | other | 0.095 | 0.095 |
| `range_z20` | volatility | 0.063 | 0.063 |
| `minus_di` | trend | 0.062 | 0.062 |
| `dist_to_today_low_pips` | location | 0.062 | -0.062 |
| `dist_to_5bar_high_pips` | location | 0.059 | 0.059 |
| `atr_ratio_5_50` | volatility | 0.058 | 0.058 |
| `vol_of_vol_20` | volatility | 0.054 | 0.054 |

### Volatility

| Indicator | Family | |rho| | Signed rho |
|---|---|---:|---:|
| `atr_pct100` | volatility | 1.000 | 1.000 |
| `atr_ratio_5_50` | volatility | 0.910 | 0.910 |
| `atr5` | volatility | 0.659 | 0.659 |
| `tick_count` | microstructure | 0.619 | 0.619 |
| `max_tick_interval_ms` | microstructure | 0.597 | -0.597 |
| `range_pips` | volatility | 0.572 | 0.572 |
| `realized_vol_20` | volatility | 0.550 | 0.550 |
| `ticks_at_high_pct` | microstructure | 0.524 | -0.524 |
| `atr14_pips` | volatility | 0.519 | 0.519 |
| `ticks_at_low_pct` | microstructure | 0.519 | -0.519 |

### Chop

| Indicator | Family | |rho| | Signed rho |
|---|---|---:|---:|
| `bb_squeeze` | volatility | 0.354 | -0.354 |
| `bb_width_pips` | volatility | 0.299 | -0.299 |
| `adx14` | trend | 0.237 | -0.237 |
| `vol_z20` | other | 0.095 | -0.095 |
| `range_z20` | volatility | 0.063 | -0.063 |
| `minus_di` | trend | 0.062 | -0.062 |
| `dist_to_today_low_pips` | location | 0.062 | 0.062 |
| `dist_to_5bar_high_pips` | location | 0.059 | -0.059 |
| `atr_ratio_5_50` | volatility | 0.058 | -0.058 |
| `vol_of_vol_20` | volatility | 0.054 | -0.054 |

### Pressure

| Indicator | Family | |rho| | Signed rho |
|---|---|---:|---:|
| `body_to_range` | candle | 0.926 | 0.926 |
| `body_pips` | candle | 0.876 | 0.876 |
| `consec_up` | momentum | 0.781 | 0.781 |
| `consec_dn` | momentum | 0.779 | -0.779 |
| `dist_ema20_atr` | trend | 0.651 | 0.651 |
| `max_run_up_pips_intrabar` | microstructure | 0.649 | 0.649 |
| `bb_pctB` | candle | 0.636 | 0.636 |
| `williams_r14` | momentum | 0.635 | 0.635 |
| `max_run_dn_pips_intrabar` | microstructure | 0.627 | -0.627 |
| `rsi14` | momentum | 0.612 | 0.612 |

## Future Direction

### 5 minutes

| Indicator | Family | Test IC | AUC | Decile spread (pips) | Stable |
|---|---|---:|---:|---:|---:|
| `body_to_range` | candle | 0.047 | 0.536 | 0.33 | yes |
| `williams_r14` | momentum | 0.038 | 0.529 | 0.35 | yes |
| `lower_wick_ratio` | candle | 0.038 | 0.525 | 0.30 | yes |
| `body_pips` | candle | 0.042 | 0.528 | 0.19 | yes |
| `dist_ema20_atr` | trend | 0.033 | 0.523 | 0.32 | yes |
| `dist_to_5bar_low_pips` | location | 0.032 | 0.522 | 0.35 | yes |
| `dist_to_20bar_high_pips` | location | 0.029 | 0.522 | 0.38 | yes |
| `consec_dn` | momentum | 0.036 | 0.527 | 0.20 | yes |
| `rsi14` | momentum | 0.031 | 0.522 | 0.28 | yes |
| `bb_pctB` | candle | 0.031 | 0.522 | 0.28 | yes |
| `dist_to_5bar_high_pips` | location | 0.032 | 0.526 | 0.20 | yes |
| `dist_ema50_atr` | trend | 0.027 | 0.519 | 0.34 | yes |

### 10 minutes

| Indicator | Family | Test IC | AUC | Decile spread (pips) | Stable |
|---|---|---:|---:|---:|---:|
| `dist_to_20bar_high_pips` | location | 0.034 | 0.527 | 0.69 | yes |
| `williams_r14` | momentum | 0.044 | 0.527 | 0.51 | yes |
| `dist_to_50bar_high_pips` | location | 0.031 | 0.526 | 0.62 | yes |
| `dist_ema50_atr` | trend | 0.034 | 0.525 | 0.54 | yes |
| `rsi14` | momentum | 0.037 | 0.525 | 0.49 | yes |
| `dist_ema20_atr` | trend | 0.038 | 0.525 | 0.48 | yes |
| `body_to_range` | candle | 0.040 | 0.527 | 0.41 | yes |
| `stoch_k` | momentum | 0.033 | 0.520 | 0.54 | yes |
| `bb_pctB` | candle | 0.035 | 0.522 | 0.45 | yes |
| `dist_to_5bar_high_pips` | location | 0.033 | 0.526 | 0.33 | yes |
| `stoch_d` | momentum | 0.028 | 0.518 | 0.44 | yes |
| `body_pips` | candle | 0.036 | 0.522 | 0.29 | yes |

### 15 minutes

| Indicator | Family | Test IC | AUC | Decile spread (pips) | Stable |
|---|---|---:|---:|---:|---:|
| `dist_to_20bar_high_pips` | location | 0.038 | 0.529 | 0.88 | yes |
| `dist_to_50bar_high_pips` | location | 0.036 | 0.527 | 0.88 | yes |
| `williams_r14` | momentum | 0.045 | 0.530 | 0.68 | yes |
| `dist_ema50_atr` | trend | 0.036 | 0.525 | 0.77 | yes |
| `stoch_k` | momentum | 0.037 | 0.526 | 0.72 | yes |
| `rsi14` | momentum | 0.038 | 0.526 | 0.65 | yes |
| `dist_ema20_atr` | trend | 0.039 | 0.526 | 0.59 | yes |
| `bb_pctB` | candle | 0.036 | 0.524 | 0.59 | yes |
| `dist_to_5bar_high_pips` | location | 0.035 | 0.530 | 0.50 | yes |
| `stoch_d` | momentum | 0.033 | 0.522 | 0.53 | yes |
| `macd` | momentum | 0.026 | 0.517 | 0.53 | yes |
| `minus_di` | trend | 0.029 | 0.520 | 0.44 | yes |

### 30 minutes

| Indicator | Family | Test IC | AUC | Decile spread (pips) | Stable |
|---|---|---:|---:|---:|---:|
| `dist_to_50bar_high_pips` | location | 0.044 | 0.535 | 1.84 | yes |
| `dist_to_20bar_high_pips` | location | 0.045 | 0.535 | 1.66 | yes |
| `rsi14` | momentum | 0.042 | 0.531 | 1.36 | yes |
| `williams_r14` | momentum | 0.051 | 0.535 | 1.19 | yes |
| `dist_ema50_atr` | trend | 0.040 | 0.531 | 1.33 | yes |
| `stoch_k` | momentum | 0.043 | 0.529 | 1.20 | yes |
| `dist_ema20_atr` | trend | 0.041 | 0.530 | 1.15 | yes |
| `bb_pctB` | candle | 0.041 | 0.529 | 1.13 | yes |
| `dist_to_5bar_high_pips` | location | 0.043 | 0.535 | 0.93 | yes |
| `dist_to_today_high_pips` | location | 0.027 | 0.525 | 1.17 | yes |
| `macd` | momentum | 0.030 | 0.523 | 1.04 | yes |
| `stoch_d` | momentum | 0.037 | 0.525 | 0.79 | yes |

### 60 minutes

| Indicator | Family | Test IC | AUC | Decile spread (pips) | Stable |
|---|---|---:|---:|---:|---:|
| `dist_to_50bar_high_pips` | location | 0.046 | 0.530 | 2.74 | yes |
| `dist_to_20bar_high_pips` | location | 0.040 | 0.527 | 2.35 | yes |
| `dist_to_5bar_high_pips` | location | 0.043 | 0.529 | 1.66 | yes |
| `rsi14` | momentum | 0.040 | 0.524 | 1.70 | yes |
| `dist_ema50_atr` | trend | 0.039 | 0.526 | 1.60 | yes |
| `realized_vol_20` | volatility | 0.017 | 0.519 | 1.86 | yes |
| `dist_to_today_high_pips` | location | 0.027 | 0.524 | 1.66 | yes |
| `bb_width_pips` | volatility | 0.009 | 0.512 | 1.88 | yes |
| `dist_ema20_atr` | trend | 0.037 | 0.522 | 1.46 | yes |
| `williams_r14` | momentum | 0.041 | 0.523 | 1.36 | yes |
| `atr5` | volatility | 0.015 | 0.518 | 1.67 | yes |
| `stoch_k` | momentum | 0.032 | 0.516 | 1.52 | yes |

## Interpretation Rules

- An indicator is not accepted from AUC alone.
- Direction must be stable from development to test.
- Prefer indicators with positive test IC and positive extreme-bucket spread.
- Correlated variants from one family count as one idea, not multiple confirmations.
- This report measures prediction, not trade profitability after spread and commission.
