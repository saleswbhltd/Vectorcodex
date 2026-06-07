# ZZLines Greedy Pivot Cover Rules

## HH

Final: recall `97.7%`, fire rate `26.4%`, exact-bar precision `4.60%`, rules `1`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `bb_pctB >= 0.75633` | 776 | 97.7% | 26.4% |

## HL

Final: recall `93.2%`, fire rate `33.3%`, exact-bar precision `2.29%`, rules `2`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `dist_to_5bar_low_pips <= 1` | 723 | 88.9% | 27.2% |
| 2 | `williams_r14 <= -81.818` | 35 | 93.2% | 33.3% |

## LH

Final: recall `93.0%`, fire rate `34.2%`, exact-bar precision `2.25%`, rules `2`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `dist_to_5bar_high_pips <= 1` | 706 | 88.6% | 29.2% |
| 2 | `williams_r14 >= -16.667` | 35 | 93.0% | 34.2% |

## LL

Final: recall `96.4%`, fire rate `23.8%`, exact-bar precision `5.00%`, rules `1`.

| # | condition | new pivots | cumulative recall | cumulative fire% |
|---:|---|---:|---:|---:|
| 1 | `bb_pctB <= 0.22446` | 749 | 96.4% | 23.8% |
