//+------------------------------------------------------------------+
//| VECTOR_ZZBufferPivotExport.mq5                                   |
//| Dumps ZigZag Lines MTF for MT5 buffers and parsed pivot rows.    |
//| Use on EURUSD M5 with zz m5.set values: Depth=12 Dev=5 Back=3.   |
//+------------------------------------------------------------------+
#property script_show_inputs

input string          InpSymbol      = "EURUSD";
input ENUM_TIMEFRAMES InpTF          = PERIOD_M5;
input int             InpDepth       = 12;
input int             InpDeviation   = 5;
input int             InpBackstep    = 3;
input int             InpTmpMaxBars  = 1000;
input int             InpIndPeriod   = 0;
input int             InpBarsBack    = 20000;
input int             InpMaxBuffers  = 10;
input bool            InpCommonFiles = true;

bool IsPriceLike(double v, double ref)
{
   return (v > ref * 0.80 && v < ref * 1.20);
}

bool IsTimestampLike(double v)
{
   return (v > 1500000000.0 && v < 2100000000.0);
}

int FindTimeIndex(const datetime &T[], int n, datetime want)
{
   for(int i = 0; i < n; i++)
      if(T[i] == want)
         return i;
   return -1;
}

void NormalizeBuffer(double &B[], int copied, int n)
{
   if(copied == n)
      return;
   ArrayResize(B, n);
   ArrayInitialize(B, 0.0);
}

void OnStart()
{
   string sym = InpSymbol;
   if(sym == "")
      sym = Symbol();

   int n = MathMin(InpBarsBack, Bars(sym, InpTF));
   if(n <= InpDepth * 2 + 1)
   {
      Print("ERROR: not enough bars. n=", n);
      return;
   }

   double O[], H[], L[], C[];
   datetime T[];
   ArraySetAsSeries(O, true);
   ArraySetAsSeries(H, true);
   ArraySetAsSeries(L, true);
   ArraySetAsSeries(C, true);
   ArraySetAsSeries(T, true);

   if(CopyOpen(sym, InpTF, 0, n, O) != n ||
      CopyHigh(sym, InpTF, 0, n, H) != n ||
      CopyLow(sym, InpTF, 0, n, L) != n ||
      CopyClose(sym, InpTF, 0, n, C) != n ||
      CopyTime(sym, InpTF, 0, n, T) != n)
   {
      Print("ERROR: Copy OHLC failed. err=", GetLastError());
      return;
   }

   int h = iCustom(sym, InpTF, "Market\\ZigZag Lines MTF for MT5",
                   IntegerToString(InpTmpMaxBars), InpIndPeriod,
                   InpDepth, InpDeviation, InpBackstep);
   if(h == INVALID_HANDLE)
   {
      Print("ERROR: indicator not loaded. err=", GetLastError());
      return;
   }

   double B0[], B1[], B2[], B3[], B4[], B5[], B6[], B7[], B8[], B9[];
   double empty[];
   ArraySetAsSeries(B0, true); ArraySetAsSeries(B1, true);
   ArraySetAsSeries(B2, true); ArraySetAsSeries(B3, true);
   ArraySetAsSeries(B4, true); ArraySetAsSeries(B5, true);
   ArraySetAsSeries(B6, true); ArraySetAsSeries(B7, true);
   ArraySetAsSeries(B8, true); ArraySetAsSeries(B9, true);

   double ref = C[0];
   int got[10];
   got[0] = CopyBuffer(h, 0, 0, n, B0);
   got[1] = CopyBuffer(h, 1, 0, n, B1);
   got[2] = CopyBuffer(h, 2, 0, n, B2);
   got[3] = CopyBuffer(h, 3, 0, n, B3);
   got[4] = CopyBuffer(h, 4, 0, n, B4);
   got[5] = CopyBuffer(h, 5, 0, n, B5);
   got[6] = CopyBuffer(h, 6, 0, n, B6);
   got[7] = CopyBuffer(h, 7, 0, n, B7);
   got[8] = CopyBuffer(h, 8, 0, n, B8);
   got[9] = CopyBuffer(h, 9, 0, n, B9);

   NormalizeBuffer(B0, got[0], n);
   NormalizeBuffer(B1, got[1], n);
   NormalizeBuffer(B2, got[2], n);
   NormalizeBuffer(B3, got[3], n);
   NormalizeBuffer(B4, got[4], n);
   NormalizeBuffer(B5, got[5], n);
   NormalizeBuffer(B6, got[6], n);
   NormalizeBuffer(B7, got[7], n);
   NormalizeBuffer(B8, got[8], n);
   NormalizeBuffer(B9, got[9], n);

   string stem = "VECTOR_ZZBUF_" + sym + "_" + EnumToString(InpTF) + "_D" +
                 IntegerToString(InpDepth) + "_Dev" + IntegerToString(InpDeviation) +
                 "_Back" + IntegerToString(InpBackstep) + "_Tmp" +
                 IntegerToString(InpTmpMaxBars);
   int flags = FILE_WRITE | FILE_CSV | FILE_ANSI;
   if(InpCommonFiles)
      flags |= FILE_COMMON;

   int raw = FileOpen(stem + "_raw.csv", flags, ',');
   if(raw == INVALID_HANDLE)
   {
      Print("ERROR: raw FileOpen failed. err=", GetLastError());
      IndicatorRelease(h);
      return;
   }
   FileWrite(raw, "bar", "time", "open", "high", "low", "close",
             "b0", "b1", "b2", "b3", "b4", "b5", "b6", "b7", "b8", "b9");

   for(int i = n - 1; i >= 0; i--)
   {
      FileWrite(raw, i, TimeToString(T[i], TIME_DATE | TIME_SECONDS),
                DoubleToString(O[i], 6), DoubleToString(H[i], 6),
                DoubleToString(L[i], 6), DoubleToString(C[i], 6),
                DoubleToString(B0[i], 8), DoubleToString(B1[i], 8),
                DoubleToString(B2[i], 8), DoubleToString(B3[i], 8),
                DoubleToString(B4[i], 8), DoubleToString(B5[i], 8),
                DoubleToString(B6[i], 8), DoubleToString(B7[i], 8),
                DoubleToString(B8[i], 8), DoubleToString(B9[i], 8));
   }
   FileClose(raw);

   int piv = FileOpen(stem + "_parsed_pivots.csv", flags, ',');
   if(piv == INVALID_HANDLE)
   {
      Print("ERROR: pivot FileOpen failed. err=", GetLastError());
      IndicatorRelease(h);
      return;
   }
   FileWrite(piv, "pivot_time", "bar", "side", "price", "source_buffer", "source_value");

   for(int i = n - 1; i >= 0; i--)
   {
      if(B6[i] != 0.0)
      {
         if(IsPriceLike(B6[i], ref))
            FileWrite(piv, TimeToString(T[i], TIME_DATE | TIME_SECONDS), i, "HIGH",
                      DoubleToString(B6[i], 6), 6, DoubleToString(B6[i], 8));
         else if(IsTimestampLike(B6[i]))
         {
            int j = FindTimeIndex(T, n, (datetime)B6[i]);
            if(j >= 0)
               FileWrite(piv, TimeToString(T[j], TIME_DATE | TIME_SECONDS), j, "HIGH",
                         DoubleToString(H[j], 6), 6, DoubleToString(B6[i], 8));
         }
      }
      if(B5[i] != 0.0)
      {
         if(IsPriceLike(B5[i], ref))
            FileWrite(piv, TimeToString(T[i], TIME_DATE | TIME_SECONDS), i, "LOW",
                      DoubleToString(B5[i], 6), 5, DoubleToString(B5[i], 8));
         else if(IsTimestampLike(B5[i]))
         {
            int j = FindTimeIndex(T, n, (datetime)B5[i]);
            if(j >= 0)
               FileWrite(piv, TimeToString(T[j], TIME_DATE | TIME_SECONDS), j, "LOW",
                         DoubleToString(L[j], 6), 5, DoubleToString(B5[i], 8));
         }
      }
   }
   FileClose(piv);

   Print("VECTOR_ZZBufferPivotExport complete. Bars=", n,
         " raw=", stem + "_raw.csv",
         " pivots=", stem + "_parsed_pivots.csv");
   for(int b = 0; b < 10; b++)
      Print("Buffer ", b, " copied=", got[b]);

   IndicatorRelease(h);
}
