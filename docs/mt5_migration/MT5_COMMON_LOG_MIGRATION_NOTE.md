# MT5 Common log migration note

Date: 2026-06-14

The portable MT5 terminals now use local `MQL5\Files` paths instead of the shared MetaQuotes `Common\Files` folder for the active EA set.

Active routing confirmed during migration:

- `RoboF1`: `OTT004` plus `SMC_Indicator`
- `RoboF2`: `GoldX_Modular_v13`, `OTT005`, `VECTOR80_BrokerReplay`, `ChartCamera`
- `RoboF3`: `GoldX_Modular_v12`
- `RoboF4`: multi-symbol `GoldX_Modular_v13`
- `RoboF5`: `GoldX_Modular_v13` replay

Copied Common logs were imported into portable-local folders:

- `RoboF2\MQL5\Files\GoldX_Modular_v13\LIVE\67196088\_CommonImported`
- `RoboF3\MQL5\Files\GoldX_Modular_v12\LIVE\67196146\_CommonImported`
- `RoboF4\MQL5\Files\GoldX_Modular_v13\LIVE\67197353\_CommonImported`
- `RoboF2\MQL5\Files\VECTOR80\_CommonImported`
- `RoboF1\MQL5\Files\SMCEA\_CommonImported`
- unmatched/legacy files: `C:\Users\cmake\MT5\_CommonFiles_Unmatched\NoCurrentPortableMatch`

The repeatable sorter is `sort_mt5_common_logs.ps1`.

Compile note:

- MetaEditor resolved standard/project includes from the AppData terminal mirror folders, not only from the portable folders.
- The portable `MQL5\Include` trees were synced into the matching AppData folders for `RoboF1` through `RoboF5`.
- After include sync, GoldX v12, GoldX v13, GoldX v13 replay, VECTOR80, and the SMC indicator compiled with `0 errors, 0 warnings`.
