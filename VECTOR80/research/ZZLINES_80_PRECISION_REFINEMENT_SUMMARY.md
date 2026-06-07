# ZZLines 80% Precision Refinement Summary

Goal: refine four pivot classes into tradable `BUY` and `SELL` signal types and search for `80%+` OOS precision.

## Methods Tested

- Rebuilt side-level labels:
  - `BUY = HL + LL`
  - `SELL = HH + LH`
- Added causal support/resistance features from prior ZZLines pivots only.
- Added temporal lag/delta/rank features.
- Tested `HistGradientBoosting`, `RandomForest`, and `ExtraTrees`.
- Tested a two-stage model:
  - stage A: pivot timing
  - stage B: trade quality
- Added M1 micro-path features inside each M5 entry bar.
- Swept trade definitions:
  - stop buffers: `5`, `8`, `12`, `20` pips
  - targets: `1.0R`, `1.5R`, `2.0R`
  - horizons: `60m`, `120m`
  - entry offsets: `+0`, `+1`, `+2` M5 bars

## Result

The original strict target, `12 pip stop`, `1.5R`, `120m`, does not reach 80%.

Best strict-target live results:

- BUY: `40.0%` precision, `5` signals, `2` hits.
- SELL: `57.1%` precision, `7` signals, `4` hits.

The 80% target is reachable only after changing the trade definition to a faster/easier target.

Best OOS result with at least `5` signals:

- BUY: `85.7%`, stop `5`, target `1.0R`, horizon `120m`, threshold `0.92`, `7` signals, `6` hits.
- SELL: `78.6%`, stop `8`, target `1.0R`, horizon `120m`, threshold `0.88`, `14` signals, `11` hits.

Ultra-selective SELL result:

- SELL: `100.0%`, stop `8`, target `1.0R`, horizon `120m`, threshold `0.90`, `4` signals, `4` hits.

## Interpretation

The project can hit `80%+` precision for `BUY` under an easier target.

For `SELL`, 80% is only reached with `4` OOS signals. That is not enough sample size to treat as stable. The better practical SELL setting is `78.6%` from `14` signals.

The current evidence does not support deploying four pivot classes independently. The practical direction is:

1. Trade side-level engines first: `BUY` and `SELL`.
2. Use easier scalp-style targets first:
   - BUY: stop `5`, target `1R`, horizon `120m`.
   - SELL: stop `8`, target `1R`, horizon `120m`.
3. Keep the original class labels as metadata, not as independent EA engines yet.
4. Validate these exact thresholds on a new unseen broker/tick export before coding live risk rules.

## Files

- `/home/cmake/Vector/research/64_buy_sell_precision_refine.py`
- `/home/cmake/Vector/research/65_two_stage_buy_sell_signal.py`
- `/home/cmake/Vector/research/66_m1_micro_buy_sell_refine.py`
- `/home/cmake/Vector/research/67_buy_sell_target_sweep.py`
- `/home/cmake/Vector/research/zzlines_buy_sell_precision_refine_quality.csv`
- `/home/cmake/Vector/research/zzlines_two_stage_buy_sell_quality.csv`
- `/home/cmake/Vector/research/zzlines_m1_micro_buy_sell_quality.csv`
- `/home/cmake/Vector/research/zzlines_buy_sell_target_sweep_quality.csv`
