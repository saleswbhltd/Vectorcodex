# Greedy Pivot Cover Rules

Detection offsets used for recall: `[-2, -1, 0]` (bars relative to pivot; negative means before pivot).

## HH

Final: recall `95.7%`, fire rate `24.9%`, exact-bar precision `1.85%`, rules `1`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `velocity_3 >= 0.0003` | 463 | 95.7% | 24.9% |

Missed pivots: `21`
First missed examples: `2025-02-20 23:30:00, 2025-03-05 18:00:00, 2025-03-31 07:05:00, 2025-04-07 18:05:00, 2025-04-18 00:55:00, 2025-04-22 03:40:00, 2025-06-03 00:00:00, 2025-06-17 12:30:00, 2025-06-20 04:10:00, 2025-07-10 00:40:00`

## HL

Final: recall `98.8%`, fire rate `34.0%`, exact-bar precision `1.73%`, rules `2`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `dist_to_5bar_high_pips >= 6` | 487 | 94.9% | 29.0% |
| 2 | `williams_r14 <= -85.714` | 20 | 98.8% | 34.0% |

Missed pivots: `6`
First missed examples: `2025-03-31 16:25:00, 2025-04-16 17:30:00, 2025-05-28 13:40:00, 2025-07-03 05:35:00, 2025-07-22 07:50:00, 2025-12-15 08:10:00`

## LH

Final: recall `96.0%`, fire rate `26.3%`, exact-bar precision `1.90%`, rules `1`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `max_run_up_pips_intrabar >= 2.6` | 498 | 96.0% | 26.3% |

Missed pivots: `21`
First missed examples: `2025-02-19 06:25:00, 2025-02-21 03:55:00, 2025-02-25 06:25:00, 2025-03-27 04:35:00, 2025-07-10 22:50:00, 2025-07-14 11:25:00, 2025-07-25 00:45:00, 2025-09-01 23:45:00, 2025-09-04 10:40:00, 2025-09-25 10:45:00`

## LL

Final: recall `95.1%`, fire rate `24.7%`, exact-bar precision `1.98%`, rules `1`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `velocity_3 <= -0.0003` | 466 | 95.1% | 24.7% |

Missed pivots: `24`
First missed examples: `2025-03-12 12:35:00, 2025-03-13 08:15:00, 2025-04-23 15:20:00, 2025-05-05 18:00:00, 2025-06-05 05:55:00, 2025-06-06 12:30:00, 2025-06-13 01:35:00, 2025-07-25 13:05:00, 2025-08-29 12:30:00, 2025-10-08 16:30:00`
