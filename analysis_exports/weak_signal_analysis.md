# Weak signal investigation: BUY_HL_HGB_090 + EQL_SSL

Source terminal: C:\Users\cmake\MT5\RoboF2
Vector logs: C:\Users\cmake\MT5\RoboF2\MQL5\Files\VECTOR80\LIVE
Chart copies: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts

| Time | Ticket | Result | Pips | Entry | SL | TP | Pivot | Score | Note |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
| 2026.06.25 22:50:00 | 697918949 | TP/WIN | 5 | 1.31964 | 1.31914 | 1.32014 | 1.31961 | 0.955000 | liquidity_proxy label=EQL_SSL score=0.955 dist_pips=0.9 rejection=false |
| 2026.06.26 04:40:01 | 698031494 | SL/LOSS | -5 | 1.31906 | 1.31856 | 1.31956 | 1.31879 | 0.990000 | liquidity_proxy label=EQL_SSL score=0.990 dist_pips=1.0 rejection=true |
| 2026.06.26 04:55:03 | 698039225 | SL/LOSS | -5 | 1.31889 | 1.31839 | 1.31939 | 1.31871 | 0.900000 | liquidity_proxy label=EQL_SSL score=0.880 dist_pips=1.8 rejection=false |
| 2026.06.26 05:20:00 | 698051200 | SL/LOSS | -5.2 | 1.31855 | 1.31805 | 1.31905 | 1.31845 | 0.990000 | liquidity_proxy label=EQL_SSL score=0.990 dist_pips=0.1 rejection=false |

## Screenshot map
- 697918949 open: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260625_225000_GBPUSD_P5_acct67196088_TRADE_OPEN_BUY_0.92lot_pos697918949_deal540467222.png
- 697918949 close: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260625_230132_GBPUSD_P5_acct67196088_TRADE_CLOSE_SELL_0.92lot_pos697918949_deal540471903.png
- 698031494 open: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260626_044001_GBPUSD_P5_acct67196088_TRADE_OPEN_BUY_0.99lot_pos698031494_deal540545540.png
- 698031494 close: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260626_051934_GBPUSD_P5_acct67196088_TRADE_CLOSE_SELL_0.99lot_pos698031494_deal540559914.png
- 698039225 open: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260626_045503_GBPUSD_P5_acct67196088_TRADE_OPEN_BUY_0.99lot_pos698039225_deal540551579.png
- 698039225 close: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260626_052225_GBPUSD_P5_acct67196088_TRADE_CLOSE_SELL_0.99lot_pos698039225_deal540561832.png
- 698051200 open: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260626_052001_GBPUSD_P5_acct67196088_TRADE_OPEN_BUY_0.98lot_pos698051200_deal540560776.png
- 698051200 close: \\wsl.localhost\Ubuntu\home\cmake\Vector\analysis_exports\weak_signal_charts\ChartCamera_20260626_055600_GBPUSD_P5_acct67196088_TRADE_CLOSE_SELL_0.98lot_pos698051200_deal540578977.png

## Findings
- The weak subset is specifically BUY_HL_HGB_090 when the liquidity proxy label is EQL_SSL.
- It took 4 trades: 1 TP and 3 SL, net about -10.2 pips before commission.
- The three losses occurred after a sell-side sweep/drop from the 04:00 high; the EA kept buying HL/EQL pullbacks while price was actively repricing lower.
- Two losing entries were non-rejection EQL_SSL signals; current default InpLiquidityRequireRejectionClose=false allows them.
- The scoring can pass without rejection because EQL strength plus proximity can reach/pass the 0.90 HL threshold, and rejection is only a boost unless the input is enabled.

## Recommended logic change
- Do not globally block EQL_SSL: BUY_LL_HGB_088 + EQL_SSL still had positive results in this sample.
- Add a targeted guard: for BUY_HL_HGB_090 + EQL_SSL, require rejection=true or a stronger trend/regime confirmation; otherwise block or down-score below 0.90.
- Add a short cooldown after a strong opposite HH/EQH sell signal or after a buy HL/EQL stopout to prevent repeated buys into the same sell leg.
