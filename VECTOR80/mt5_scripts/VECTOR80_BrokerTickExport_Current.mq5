//+------------------------------------------------------------------+
//| VECTOR80_BrokerTickExport_Current.mq5                            |
//| Export recent broker ticks for VECTOR80 score refresh.           |
//|                                                                  |
//| Run as an MT5 Script. Output goes to Common\Files.               |
//+------------------------------------------------------------------+
#property script_show_inputs

input string   InpSymbol     = "EURUSD";
input datetime InpFrom       = D'2026.06.01 00:00';
input datetime InpTo         = 0; // 0 = current broker time
input int      InpChunkHours = 6;

string DateTag(datetime t)
{
   MqlDateTime dt;
   TimeToStruct(t, dt);
   return StringFormat("%04d%02d%02d", dt.year, dt.mon, dt.day);
}

void OnStart()
{
   datetime export_to = InpTo > 0 ? InpTo : TimeCurrent();
   if(export_to <= InpFrom)
   {
      Alert("InpTo must be after InpFrom");
      return;
   }
   if(!SymbolSelect(InpSymbol, true))
   {
      Alert("Symbol not found: ", InpSymbol);
      return;
   }

   int chunk_hours = MathMax(1, InpChunkHours);
   string fname = StringFormat("VECTOR80_BROKER_TICKS_%s_%s_%s.csv",
                               InpSymbol, DateTag(InpFrom), DateTag(export_to));
   int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_COMMON | FILE_ANSI, ',');
   if(fh == INVALID_HANDLE)
   {
      Alert("Cannot open Common\\Files\\", fname, " err=", GetLastError());
      return;
   }

   FileWrite(fh, "datetime", "time_msc", "bid", "ask", "last", "volume", "flags", "mid");

   ulong total = 0;
   datetime chunk_from = InpFrom;
   while(chunk_from < export_to)
   {
      datetime chunk_to = chunk_from + chunk_hours * 3600;
      if(chunk_to > export_to)
         chunk_to = export_to;

      MqlTick ticks[];
      ulong from_msc = (ulong)chunk_from * 1000;
      ulong to_msc = (ulong)chunk_to * 1000 - 1;
      int copied = CopyTicksRange(InpSymbol, ticks, COPY_TICKS_ALL, from_msc, to_msc);

      if(copied < 0)
      {
         PrintFormat("CopyTicksRange failed %s -> %s err=%d",
                     TimeToString(chunk_from, TIME_DATE | TIME_SECONDS),
                     TimeToString(chunk_to, TIME_DATE | TIME_SECONDS),
                     GetLastError());
      }
      else
      {
         for(int i = 0; i < copied; i++)
         {
            double mid = 0.0;
            if(ticks[i].bid > 0.0 && ticks[i].ask > 0.0)
               mid = (ticks[i].bid + ticks[i].ask) * 0.5;
            else if(ticks[i].last > 0.0)
               mid = ticks[i].last;
            else if(ticks[i].bid > 0.0)
               mid = ticks[i].bid;
            else if(ticks[i].ask > 0.0)
               mid = ticks[i].ask;

            FileWrite(fh,
                      TimeToString(ticks[i].time, TIME_DATE | TIME_SECONDS),
                      (string)ticks[i].time_msc,
                      DoubleToString(ticks[i].bid, _Digits),
                      DoubleToString(ticks[i].ask, _Digits),
                      DoubleToString(ticks[i].last, _Digits),
                      DoubleToString(ticks[i].volume_real, 2),
                      (string)ticks[i].flags,
                      DoubleToString(mid, _Digits));
         }
         total += (ulong)copied;
         PrintFormat("VECTOR80 exported %d ticks: %s -> %s total=%I64u",
                     copied,
                     TimeToString(chunk_from, TIME_DATE | TIME_SECONDS),
                     TimeToString(chunk_to, TIME_DATE | TIME_SECONDS),
                     total);
      }
      chunk_from = chunk_to;
   }

   FileClose(fh);
   Alert(StringFormat("VECTOR80 tick export complete: %I64u ticks -> Common\\Files\\%s",
                      total, fname));
}
