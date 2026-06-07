//+------------------------------------------------------------------+
//| VECTOR_DataExport.mq5                                            |
//| Exports M1 bars + raw tick history from the broker's real-tick   |
//| feed to CSV files under MQL5/Files/ (terminal local sandbox).    |
//|                                                                  |
//| Outputs (per symbol):                                            |
//|   <SYMBOL>_M1.csv     time,open,high,low,close,tick_volume,spread|
//|   <SYMBOL>_M5.csv     time,open,high,low,close,tick_volume,spread|
//|   <SYMBOL>_ticks.csv  time_msc,bid,ask,last,volume,flags         |
//|                                                                  |
//| Run as a Script (drag onto chart). Adjust inputs as needed.      |
//+------------------------------------------------------------------+
#property script_show_inputs
#property strict

input string   InpSymbol      = "EURUSD";   // Symbol to export
input int      InpMonthsBack  = 5;          // How many months of history to dump
input bool     InpExportTicks = true;       // Set false to skip ticks (much faster)
input bool     InpExportM1    = true;       // Set false to skip M1
input bool     InpExportM5    = true;       // Set false to skip M5

//──────────────────────────────────────────────────────────────────
void OnStart()
{
    datetime now = TimeCurrent();
    // Approx N months ago — use 30-day months, MT5 will clamp to available history
    datetime from = now - (datetime)InpMonthsBack * 30 * 24 * 3600;

    PrintFormat("VECTOR_DataExport: symbol=%s from=%s to=%s",
                InpSymbol, TimeToString(from), TimeToString(now));

    if(InpExportM1) ExportBars(InpSymbol, PERIOD_M1, from, now);
    if(InpExportM5) ExportBars(InpSymbol, PERIOD_M5, from, now);
    if(InpExportTicks) ExportTicks(InpSymbol, from, now);

    Print("VECTOR_DataExport: DONE. Files under MQL5/Files/");
}

//──────────────────────────────────────────────────────────────────
void ExportBars(const string sym, ENUM_TIMEFRAMES tf, datetime from, datetime to)
{
    MqlRates rates[];
    int n = CopyRates(sym, tf, from, to, rates);
    if(n <= 0)
    {
        PrintFormat("ExportBars: CopyRates failed for %s %s  err=%d",
                    sym, EnumToString(tf), GetLastError());
        return;
    }

    string tfName = (tf == PERIOD_M1) ? "M1" : (tf == PERIOD_M5) ? "M5" : EnumToString(tf);
    string fn = sym + "_" + tfName + ".csv";
    int h = FileOpen(fn, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(h == INVALID_HANDLE)
    {
        PrintFormat("ExportBars: FileOpen failed for %s  err=%d", fn, GetLastError());
        return;
    }

    FileWrite(h, "datetime", "open", "high", "low", "close", "tick_volume", "spread", "real_volume");
    for(int i = 0; i < n; i++)
    {
        FileWrite(h,
            TimeToString(rates[i].time, TIME_DATE | TIME_SECONDS),
            DoubleToString(rates[i].open,  _Digits),
            DoubleToString(rates[i].high,  _Digits),
            DoubleToString(rates[i].low,   _Digits),
            DoubleToString(rates[i].close, _Digits),
            IntegerToString((long)rates[i].tick_volume),
            IntegerToString(rates[i].spread),
            IntegerToString((long)rates[i].real_volume));
    }
    FileClose(h);
    PrintFormat("ExportBars: wrote %d bars → %s", n, fn);
}

//──────────────────────────────────────────────────────────────────
void ExportTicks(const string sym, datetime from, datetime to)
{
    // CopyTicksRange uses milliseconds since epoch.
    ulong from_ms = (ulong)from * 1000;
    ulong to_ms   = (ulong)to   * 1000;

    MqlTick ticks[];
    // COPY_TICKS_ALL = both bid/ask updates and trades.
    int n = CopyTicksRange(sym, ticks, COPY_TICKS_ALL, from_ms, to_ms);
    if(n <= 0)
    {
        PrintFormat("ExportTicks: CopyTicksRange returned %d  err=%d "
                    "(broker may not provide tick history that far back)",
                    n, GetLastError());
        return;
    }
    PrintFormat("ExportTicks: got %d ticks — writing CSV (this can take a while)...", n);

    string fn = sym + "_ticks.csv";
    int h = FileOpen(fn, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
    if(h == INVALID_HANDLE)
    {
        PrintFormat("ExportTicks: FileOpen failed  err=%d", GetLastError());
        return;
    }

    FileWrite(h, "time_msc", "bid", "ask", "last", "volume", "flags");
    for(int i = 0; i < n; i++)
    {
        FileWrite(h,
            IntegerToString((long)ticks[i].time_msc),
            DoubleToString(ticks[i].bid,  _Digits),
            DoubleToString(ticks[i].ask,  _Digits),
            DoubleToString(ticks[i].last, _Digits),
            IntegerToString((long)ticks[i].volume),
            IntegerToString((int)ticks[i].flags));
    }
    FileClose(h);
    PrintFormat("ExportTicks: wrote %d ticks → %s", n, fn);
}
//+------------------------------------------------------------------+
