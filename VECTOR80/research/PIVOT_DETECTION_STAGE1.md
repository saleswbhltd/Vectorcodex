# M5 Pivot Detection Stage 1

## Objective

Build a first-stage detector that catches most historical M5 ZigZag pivots in real time, before deciding whether each detected pivot is worth trading.

Development period:

```text
2025-02-01 to 2026-02-28
```

Reserved OOS period:

```text
2026-03-01 to 2026-06-01
```

## Files

| File | Purpose |
|---|---|
| `40_build_pivot_map.py` | Build and classify the M5 pivot map |
| `pivot_map.csv` | 2006 labeled pivots |
| `41_indicator_scan.py` | Indicator-by-indicator pivot distribution scan |
| `indicator_scan.csv` | Per-indicator class metrics |
| `indicator_kept.csv` | Indicators with measurable class effects |
| `42_recall_ensemble.py` | Broad OR ensemble recall experiment |
| `43_detection_matrix.py` | Per-condition timing/coverage matrix |
| `detection_matrix.csv` | Condition coverage, timing, fire-rate, precision |
| `detection_matrix_top.md` | Readable top conditions per class |
| `44_greedy_cover.py` | Greedy complementary condition selector |
| `greedy_cover_summary.csv` | Selected condition steps |
| `greedy_cover_rules.md` | Readable selected covers |

## Pivot Map

The map contains 2006 development pivots, balanced across four classes:

| Class | Meaning |
|---|---|
| `HH` | Sell swing |
| `LH` | Sell pullback |
| `HL` | Buy pullback |
| `LL` | Buy swing |

## Stage 1 Result

Using bars `[-2, -1, 0]` relative to pivot time as valid real-time detection windows:

| Class | Rules | Recall | Fire rate | Exact-bar precision | Main detector |
|---|---:|---:|---:|---:|---|
| `HH` | 1 | 95.7% | 24.9% | 1.85% | `velocity_3 >= 0.0003` |
| `LH` | 1 | 96.0% | 26.3% | 1.90% | `max_run_up_pips_intrabar >= 2.6` |
| `LL` | 1 | 95.1% | 24.7% | 1.98% | `velocity_3 <= -0.0003` |
| `HL` | 2 | 98.8% | 34.0% | 1.73% | `dist_to_5bar_high_pips >= 6` plus `williams_r14 <= -85.714` |

## Interpretation

High recall is achievable. The current detectors catch roughly 95-99% of pivots.

The candidate load is still too high for trading:

- The first-stage detector fires on about 25-34% of all M5 bars.
- Exact-bar precision remains only about 1.7-2.0%.

This is acceptable only as a first-stage map. It is not a trade signal.

## What Worked

The most useful first-stage detectors are broad momentum/location signatures:

- `velocity_3`
- `max_run_up_pips_intrabar`
- `dist_to_5bar_high_pips`
- `williams_r14`

Tick-derived intrabar features matter, especially for sell-side pivot detection.

## Next Step

Build Stage 2:

1. Treat Stage 1 fires as candidate pivot bars.
2. For each candidate, attach class probabilities and context.
3. Filter candidates by:
   - pivot class
   - tick exhaustion quality
   - H1 trend context
   - strength tier target
   - expected MFE/MAE
4. Evaluate OOS on `2026-03-01` to `2026-06-01`.

The correct next script is:

```text
45_stage2_candidate_quality.py
```

