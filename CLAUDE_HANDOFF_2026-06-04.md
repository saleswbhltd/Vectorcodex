# Claude Handoff - Vector Folder Split

Date: 2026-06-04

## Summary

The project files have been separated by ownership so Claude and Codex can work on different EA approaches while sharing research/data/model artifacts.

## Project Ownership

Claude-owned project:

```text
/home/cmake/Vector
```

Use this for:

- `VECTOR001.mq5`
- `VECTOR002.mq5`
- `VECTOR003.mq5`
- `VECTOR003_BRIDGE.py`
- `VECTOR003_DEPLOY.md`
- `deploy.sh`, `deploy_v2.sh`, `deploy_v3.sh`
- Claude notes and Claude-side EA work

Codex-owned project:

```text
/home/cmake/Vectorcodex/VECTOR80
```

Use this for:

- `ea/VECTOR80_BrokerReplay.mq5`
- `ea/VECTOR80_Prototype.mq5`
- `notes/close-up/2026-06-03_2045.md`

Shared project:

```text
/home/cmake/VectorShared
```

Use this for common research, tick-history data, Python research scripts, generated reports, model scores, and exported model files that can help both EA approaches.

## Shared Paths Claude Should Use

From the Claude project, keep using these normal paths:

```text
/home/cmake/Vector/research
/home/cmake/Vector/models
```

They are symlinks:

```text
/home/cmake/Vector/research -> ../VectorShared/research
/home/cmake/Vector/models   -> ../VectorShared/models
```

Canonical shared paths:

```text
/home/cmake/VectorShared/research
/home/cmake/VectorShared/models
```

Codex sees the same shared files through:

```text
/home/cmake/Vectorcodex/VECTOR80/research
/home/cmake/Vectorcodex/VECTOR80/models
```

These resolve through:

```text
/home/cmake/Vectorcodex/shared/research -> /home/cmake/VectorShared/research
/home/cmake/Vectorcodex/shared/models   -> /home/cmake/VectorShared/models
```

## Important Shared Files

Research and score artifacts Claude may need:

```text
/home/cmake/Vector/research/VECTOR80_model_scores.csv
/home/cmake/Vector/research/vector80_engine_config.json
/home/cmake/Vector/research/vector80_sell_expanded_engine_config.json
/home/cmake/Vector/research/vector80_25_vs_45_trade_siblings.html
/home/cmake/Vector/research/vector80_25_clusters_with_45_siblings.csv
/home/cmake/Vector/research/vector80_45_vs_25_trade_compare.csv
```

Model artifacts:

```text
/home/cmake/Vector/models/manifest.json
/home/cmake/Vector/models/*.pkl
```

Raw or derived market data is also in:

```text
/home/cmake/Vector/research
```

This includes tick-history `.csv.gz` files and M1/M5 feature panels.

## VECTOR80 Status For Reference

The active VECTOR80 file from the previous close-up is:

```text
/home/cmake/Vectorcodex/VECTOR80/ea/VECTOR80_BrokerReplay.mq5
```

The close-up note identifying that active file is:

```text
/home/cmake/Vectorcodex/VECTOR80/notes/close-up/2026-06-03_2045.md
```

Live MT5 copy from the close-up:

```text
C:\Users\cmake\AppData\Roaming\MetaQuotes\Terminal\72B4906E79165035DB072CC7DF25FBDA\MQL5\Experts\Advisors\VECTOR80_BrokerReplay.mq5
```

WSL path:

```text
/mnt/c/Users/cmake/AppData/Roaming/MetaQuotes/Terminal/72B4906E79165035DB072CC7DF25FBDA/MQL5/Experts/Advisors/VECTOR80_BrokerReplay.mq5
```

## Git / Cleanup Notes

`/home/cmake/Vector` currently has many uncommitted/untracked files. After the migration, Git sees `research` and `models` as untracked symlinks instead of large untracked directories. That is expected.

Do not delete `/home/cmake/VectorShared`. Both projects now depend on it.

Do not move `VECTOR80` work back into `/home/cmake/Vector`; use `/home/cmake/Vectorcodex/VECTOR80` for Codex-owned VECTOR80 work.

## Quick Verification Commands

```bash
ls -ld /home/cmake/Vector/research /home/cmake/Vector/models
ls -ld /home/cmake/VectorShared/research /home/cmake/VectorShared/models
ls -ld /home/cmake/Vectorcodex/VECTOR80/research /home/cmake/Vectorcodex/VECTOR80/models
test -f /home/cmake/Vector/research/VECTOR80_model_scores.csv && echo "shared research ok"
test -f /home/cmake/Vector/models/manifest.json && echo "shared models ok"
```
