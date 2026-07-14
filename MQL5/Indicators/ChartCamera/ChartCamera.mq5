#property strict
#property version   "1.13"
#property description "Standalone chart screenshot indicator with local metadata logging."
#property indicator_chart_window
#property indicator_plots 0

input string InpCameraTag = "AUTO";
input bool   InpCaptureOnTimer = true;
input int    InpTimerSeconds = 1;
input int    InpHistoryLookbackHours = 72;
input bool   InpCaptureOpenDeals = true;
input bool   InpCaptureCloseDeals = true;
input bool   InpOnlyChartSymbol = false;
input bool   InpUseTradeSymbolChart = true;
input bool   InpTerminalWideDedup = true;
input bool   InpCaptureExistingHistoryOnStart = false;
input bool   InpCaptureVirtualReplayTrades = true;
input int    InpDebounceSeconds = 2;
input int    InpImageWidth = 1600;
input int    InpImageHeight = 1000;
input bool   InpWriteJson = true;
input bool   InpWriteIndexCsv = true;
input string InpOutputRoot = "ChartCamera";
input string InpLiveEnvironmentFolder = "LIVE";
input string InpTesterEnvironmentFolder = "TEST_NON6E";
input int    InpScreenshotVerifyRetries = 10;
input int    InpScreenshotVerifyDelayMs = 100;

datetime g_lastCaptureTime = 0;
string   g_lastCaptureKey = "";
datetime g_lastSeenDealTime = 0;
ulong    g_lastSeenDealTicket = 0;
long     g_lastVirtualEventIndex = 0;
datetime g_lastTesterPollTime = 0;

string CameraSafePart(string value)
{
   string result = value;
   StringReplace(result, "\\", "_");
   StringReplace(result, "/", "_");
   StringReplace(result, ":", "_");
   StringReplace(result, "*", "_");
   StringReplace(result, "?", "_");
   StringReplace(result, "\"", "_");
   StringReplace(result, "<", "_");
   StringReplace(result, ">", "_");
   StringReplace(result, "|", "_");
   StringReplace(result, " ", "_");
   return result;
}

string CameraJsonEscape(string value)
{
   string result = value;
   StringReplace(result, "\\", "\\\\");
   StringReplace(result, "\"", "\\\"");
   StringReplace(result, "\r", "\\r");
   StringReplace(result, "\n", "\\n");
   StringReplace(result, "\t", "\\t");
   return result;
}

string CameraTimestamp(datetime when)
{
   MqlDateTime parts;
   TimeToStruct(when, parts);
   return StringFormat("%04d%02d%02d_%02d%02d%02d",
                       parts.year,
                       parts.mon,
                       parts.day,
                       parts.hour,
                       parts.min,
                       parts.sec);
}

string CameraEnvironment()
{
   if(MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_OPTIMIZATION))
      return CameraSafePart(InpTesterEnvironmentFolder);
   return CameraSafePart(InpLiveEnvironmentFolder);
}

string CameraTag()
{
   if(InpCameraTag == "" || InpCameraTag == "AUTO")
      return TerminalInfoString(TERMINAL_NAME);
   return InpCameraTag;
}

string CameraSymbolPeriodFolder(const string symbol)
{
   return CameraSafePart(symbol) + "_P" + IntegerToString((int)Period());
}

string CameraSymbolPeriodFolder(const string symbol, const int period)
{
   return CameraSafePart(symbol) + "_P" + IntegerToString(period);
}

bool CameraEnsureFolder(const string folder)
{
   string partial = "";
   string parts[];
   int count = StringSplit(folder, '\\', parts);
   for(int i = 0; i < count; ++i)
   {
      if(parts[i] == "")
         continue;

      partial = (partial == "" ? parts[i] : partial + "\\" + parts[i]);
      ResetLastError();
      if(!FolderCreate(partial) && GetLastError() != 5016)
      {
         PrintFormat("ChartCamera folder create failed folder=%s err=%d", partial, GetLastError());
         return false;
      }
   }
   return true;
}


bool CameraFileExistsAfterWait(const string path)
{
   int retries = MathMax(0, InpScreenshotVerifyRetries);
   int delay_ms = MathMax(0, InpScreenshotVerifyDelayMs);
   for(int i = 0; i <= retries; ++i)
   {
      if(FileIsExist(path))
         return true;
      if(delay_ms > 0)
      {
         ChartRedraw();
         Sleep(delay_ms);
      }
   }
   return FileIsExist(path);
}

string CameraBaseFolder(const string symbol)
{
   long account = AccountInfoInteger(ACCOUNT_LOGIN);
   return CameraSafePart(InpOutputRoot) + "\\" +
          CameraEnvironment() + "\\" +
          IntegerToString((int)account) + "\\" +
          CameraSymbolPeriodFolder(symbol);
}

string CameraBaseFolder(const string symbol, const int period)
{
   long account = AccountInfoInteger(ACCOUNT_LOGIN);
   return CameraSafePart(InpOutputRoot) + "\\" +
          CameraEnvironment() + "\\" +
          IntegerToString((int)account) + "\\" +
          CameraSymbolPeriodFolder(symbol, period);
}

string CameraDealEntryName(const ENUM_DEAL_ENTRY entry)
{
   if(entry == DEAL_ENTRY_IN)
      return "OPEN";
   if(entry == DEAL_ENTRY_OUT)
      return "CLOSE";
   if(entry == DEAL_ENTRY_INOUT)
      return "REVERSE";
   if(entry == DEAL_ENTRY_OUT_BY)
      return "CLOSE_BY";
   return "UNKNOWN";
}

string CameraDealTypeName(const ENUM_DEAL_TYPE type)
{
   if(type == DEAL_TYPE_BUY)
      return "BUY";
   if(type == DEAL_TYPE_SELL)
      return "SELL";
   if(type == DEAL_TYPE_BALANCE)
      return "BALANCE";
   if(type == DEAL_TYPE_CREDIT)
      return "CREDIT";
   return EnumToString(type);
}

bool CameraShouldCaptureEntry(const ENUM_DEAL_ENTRY entry)
{
   if(entry == DEAL_ENTRY_IN)
      return InpCaptureOpenDeals;
   if(entry == DEAL_ENTRY_OUT || entry == DEAL_ENTRY_OUT_BY)
      return InpCaptureCloseDeals;
   if(entry == DEAL_ENTRY_INOUT)
      return InpCaptureOpenDeals || InpCaptureCloseDeals;
   return false;
}

bool CameraIsTradeDeal(const ENUM_DEAL_TYPE type)
{
   return type == DEAL_TYPE_BUY || type == DEAL_TYPE_SELL;
}

string CameraVirtualEventPrefix()
{
   return "VTE." + _Symbol + ".";
}

bool CameraReadGlobalDouble(const string name, double &value)
{
   if(!GlobalVariableCheck(name))
      return false;
   value = GlobalVariableGet(name);
   return true;
}

long CameraVirtualNextIndex()
{
   double value = 0.0;
   if(!CameraReadGlobalDouble(CameraVirtualEventPrefix() + "NEXT_IDX", value))
      return 0;
   return (long)value;
}

string CameraGlobalCaptureKey(const string reason, const string symbol, const ulong deal, const ulong position)
{
   return "ChartCamera.CAPTURED." +
          CameraEnvironment() + "." +
          IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + "." +
          CameraSafePart(symbol) + "." +
          CameraSafePart(reason) + "." +
          IntegerToString((int)deal) + "." +
          IntegerToString((int)position);
}

bool CameraAlreadyCaptured(const string reason, const string symbol, const ulong deal, const ulong position)
{
   if(!InpTerminalWideDedup || deal == 0)
      return false;
   return GlobalVariableCheck(CameraGlobalCaptureKey(reason, symbol, deal, position));
}

void CameraMarkCaptured(const string reason, const string symbol, const ulong deal, const ulong position)
{
   if(!InpTerminalWideDedup || deal == 0)
      return;
   GlobalVariableSet(CameraGlobalCaptureKey(reason, symbol, deal, position), (double)TimeCurrent());
}

long CameraFindTradeChart(const string symbol)
{
   if(!InpUseTradeSymbolChart)
      return ChartID();

   long fallback = 0;
   long exactPeriod = 0;
   long chart = ChartFirst();
   while(chart >= 0)
   {
      if(ChartSymbol(chart) == symbol)
      {
         if(fallback == 0)
            fallback = chart;
         if((int)ChartPeriod(chart) == (int)Period())
         {
            exactPeriod = chart;
            break;
         }
      }
      chart = ChartNext(chart);
   }

   if(exactPeriod != 0)
      return exactPeriod;
   if(fallback != 0)
      return fallback;
   return ChartID();
}

void CameraPrimeVirtualEvents()
{
   if(!InpCaptureVirtualReplayTrades)
      return;

   g_lastVirtualEventIndex = CameraVirtualNextIndex();
   GlobalVariableSet(CameraVirtualEventPrefix() + "DONE_IDX", (double)g_lastVirtualEventIndex);
}

string CameraFormatDouble(const double value, const int digits)
{
   return DoubleToString(value, digits);
}

void CameraWriteJson(const string path,
                     const long chartId,
                     const string chartSymbol,
                     const int chartPeriod,
                     const string symbol,
                     const string reason,
                     const ulong deal,
                     const ulong position,
                     const ENUM_DEAL_ENTRY entry,
                     const ENUM_DEAL_TYPE type,
                     const double volume,
                     const double price,
                     const double profit,
                     const double commission,
                     const double swap,
                     const long magic,
                     const string comment,
                     const string imagePath)
{
   if(!InpWriteJson)
      return;

   ResetLastError();
   int handle = FileOpen(path, FILE_WRITE | FILE_TXT | FILE_ANSI);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("ChartCamera json open failed path=%s err=%d", path, GetLastError());
      return;
   }

   MqlTick tick;
   bool hasTick = SymbolInfoTick(symbol, tick);
   double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double spread = 0.0;
   if(hasTick && point > 0.0)
      spread = (tick.ask - tick.bid) / point;

   FileWriteString(handle, "{\n");
   FileWriteString(handle, "  \"utility\": \"ChartCamera\",\n");
   FileWriteString(handle, "  \"utility_type\": \"indicator\",\n");
   FileWriteString(handle, "  \"camera_tag\": \"" + CameraJsonEscape(CameraTag()) + "\",\n");
   FileWriteString(handle, "  \"environment\": \"" + CameraEnvironment() + "\",\n");
   FileWriteString(handle, "  \"account\": " + IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)) + ",\n");
   FileWriteString(handle, "  \"broker\": \"" + CameraJsonEscape(AccountInfoString(ACCOUNT_COMPANY)) + "\",\n");
   FileWriteString(handle, "  \"terminal\": \"" + CameraJsonEscape(TerminalInfoString(TERMINAL_NAME)) + "\",\n");
   FileWriteString(handle, "  \"symbol\": \"" + CameraJsonEscape(symbol) + "\",\n");
   FileWriteString(handle, "  \"chart_symbol\": \"" + CameraJsonEscape(chartSymbol) + "\",\n");
   FileWriteString(handle, "  \"period\": " + IntegerToString(chartPeriod) + ",\n");
   FileWriteString(handle, "  \"chart_id\": " + IntegerToString((int)chartId) + ",\n");
   FileWriteString(handle, "  \"capture_time\": \"" + TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS) + "\",\n");
   FileWriteString(handle, "  \"reason\": \"" + CameraJsonEscape(reason) + "\",\n");
   FileWriteString(handle, "  \"deal\": " + IntegerToString((int)deal) + ",\n");
   FileWriteString(handle, "  \"position\": " + IntegerToString((int)position) + ",\n");
   FileWriteString(handle, "  \"entry\": \"" + CameraDealEntryName(entry) + "\",\n");
   FileWriteString(handle, "  \"type\": \"" + CameraDealTypeName(type) + "\",\n");
   FileWriteString(handle, "  \"volume\": " + CameraFormatDouble(volume, 2) + ",\n");
   FileWriteString(handle, "  \"price\": " + CameraFormatDouble(price, digits) + ",\n");
   FileWriteString(handle, "  \"profit\": " + CameraFormatDouble(profit, 2) + ",\n");
   FileWriteString(handle, "  \"commission\": " + CameraFormatDouble(commission, 2) + ",\n");
   FileWriteString(handle, "  \"swap\": " + CameraFormatDouble(swap, 2) + ",\n");
   FileWriteString(handle, "  \"magic\": " + IntegerToString((int)magic) + ",\n");
   FileWriteString(handle, "  \"comment\": \"" + CameraJsonEscape(comment) + "\",\n");
   FileWriteString(handle, "  \"bid\": " + CameraFormatDouble(hasTick ? tick.bid : 0.0, digits) + ",\n");
   FileWriteString(handle, "  \"ask\": " + CameraFormatDouble(hasTick ? tick.ask : 0.0, digits) + ",\n");
   FileWriteString(handle, "  \"spread_points\": " + CameraFormatDouble(spread, 1) + ",\n");
   FileWriteString(handle, "  \"open_positions_total\": " + IntegerToString(PositionsTotal()) + ",\n");
   FileWriteString(handle, "  \"image\": \"" + CameraJsonEscape(imagePath) + "\"\n");
   FileWriteString(handle, "}\n");
   FileClose(handle);
}

void CameraWriteIndex(const string folder,
                      const string imagePath,
                      const string chartSymbol,
                      const int chartPeriod,
                      const string symbol,
                      const string reason,
                      const ulong deal,
                      const ulong position,
                      const ENUM_DEAL_ENTRY entry,
                      const ENUM_DEAL_TYPE type,
                      const double volume,
                      const double price,
                      const double profit)
{
   if(!InpWriteIndexCsv)
      return;

   string path = folder + "\\index.csv";
   bool exists = FileIsExist(path);
   ResetLastError();
   int handle = FileOpen(path, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("ChartCamera index open failed path=%s err=%d", path, GetLastError());
      return;
   }

   if(!exists)
   {
      FileWrite(handle,
                "capture_time",
                "environment",
                "account",
                "symbol",
                "chart_symbol",
                "period",
                "reason",
                "entry",
                "type",
                "volume",
                "price",
                "profit",
                "deal",
                "position",
                "image");
   }

   FileSeek(handle, 0, SEEK_END);
   FileWrite(handle,
             TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
             CameraEnvironment(),
             IntegerToString((int)AccountInfoInteger(ACCOUNT_LOGIN)),
             symbol,
             chartSymbol,
             IntegerToString(chartPeriod),
             reason,
             CameraDealEntryName(entry),
             CameraDealTypeName(type),
             DoubleToString(volume, 2),
             DoubleToString(price, (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS)),
             DoubleToString(profit, 2),
             IntegerToString((int)deal),
             IntegerToString((int)position),
             imagePath);
   FileClose(handle);
}

bool CameraCapture(const string reason,
                   const string symbol,
                   const ulong deal = 0,
                   const ulong position = 0,
                   const ENUM_DEAL_ENTRY entry = DEAL_ENTRY_IN,
                   const ENUM_DEAL_TYPE type = DEAL_TYPE_BUY,
                   const double volume = 0.0,
                   const double price = 0.0,
                   const double profit = 0.0,
                   const double commission = 0.0,
                   const double swap = 0.0,
                   const long magic = 0,
                   const string comment = "")
{
   if(InpOnlyChartSymbol && !InpUseTradeSymbolChart && symbol != _Symbol)
      return false;

   string key = symbol + "|" + reason + "|" + IntegerToString((int)deal) + "|" + IntegerToString((int)position);
   datetime now = TimeCurrent();
   if(InpDebounceSeconds > 0 && key == g_lastCaptureKey && (now - g_lastCaptureTime) < InpDebounceSeconds)
      return false;

   if(CameraAlreadyCaptured(reason, symbol, deal, position))
      return false;

   long chartId = CameraFindTradeChart(symbol);
   string chartSymbol = ChartSymbol(chartId);
   int chartPeriod = (int)ChartPeriod(chartId);

   if(InpUseTradeSymbolChart && chartSymbol != symbol)
   {
      PrintFormat("ChartCamera no open chart for trade_symbol=%s attached_chart=%s deal=%d", symbol, _Symbol, (int)deal);
      return false;
   }

   string folder = CameraBaseFolder(chartSymbol, chartPeriod);
   if(!CameraEnsureFolder(folder))
      return false;

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   string stamp = CameraTimestamp(now);
   string baseName = StringFormat("ChartCamera_%s_%s_P%d_acct%d_%s_%s_%s_%slot_pos%d_deal%d",
                                  stamp,
                                  CameraSafePart(chartSymbol),
                                  chartPeriod,
                                  (int)AccountInfoInteger(ACCOUNT_LOGIN),
                                  CameraSafePart(reason),
                                  CameraDealEntryName(entry),
                                  CameraDealTypeName(type),
                                  DoubleToString(volume, 2),
                                  (int)position,
                                  (int)deal);
   string imagePath = folder + "\\" + baseName + ".png";
   string jsonPath = folder + "\\" + baseName + ".json";

   ChartRedraw(chartId);
   ResetLastError();
   bool ok = ChartScreenShot(chartId, imagePath, InpImageWidth, InpImageHeight, ALIGN_RIGHT);
   int shot_error = GetLastError();
   if(!ok)
   {
      PrintFormat("ChartCamera screenshot failed path=%s err=%d", imagePath, shot_error);
      return false;
   }

   if(!CameraFileExistsAfterWait(imagePath))
   {
      PrintFormat("ChartCamera screenshot missing after success path=%s err=%d retries=%d delay_ms=%d", imagePath, shot_error, InpScreenshotVerifyRetries, InpScreenshotVerifyDelayMs);
      return false;
   }

   CameraWriteJson(jsonPath, chartId, chartSymbol, chartPeriod, symbol, reason, deal, position, entry, type, volume, NormalizeDouble(price, digits), profit, commission, swap, magic, comment, imagePath);
   CameraWriteIndex(folder, imagePath, chartSymbol, chartPeriod, symbol, reason, deal, position, entry, type, volume, price, profit);

   CameraMarkCaptured(reason, symbol, deal, position);
   g_lastCaptureKey = key;
   g_lastCaptureTime = now;
   PrintFormat("ChartCamera captured chart=%s trade_symbol=%s reason=%s image=%s", chartSymbol, symbol, reason, imagePath);
   return true;
}

bool CameraDealIsNewer(const datetime dealTime, const ulong dealTicket)
{
   if(dealTime > g_lastSeenDealTime)
      return true;
   return dealTime == g_lastSeenDealTime && dealTicket > g_lastSeenDealTicket;
}

void CameraRememberDeal(const datetime dealTime, const ulong dealTicket)
{
   if(dealTime > g_lastSeenDealTime || (dealTime == g_lastSeenDealTime && dealTicket > g_lastSeenDealTicket))
   {
      g_lastSeenDealTime = dealTime;
      g_lastSeenDealTicket = dealTicket;
   }
}

void CameraScanDeals(const bool capture)
{
   datetime now = TimeCurrent();
   datetime from = now - MathMax(1, InpHistoryLookbackHours) * 3600;
   if(!HistorySelect(from, now))
      return;

   int total = HistoryDealsTotal();
   for(int i = 0; i < total; ++i)
   {
      ulong deal = HistoryDealGetTicket(i);
      if(deal == 0)
         continue;

      datetime dealTime = (datetime)HistoryDealGetInteger(deal, DEAL_TIME);
      if(capture && !CameraDealIsNewer(dealTime, deal))
         continue;

      string symbol = HistoryDealGetString(deal, DEAL_SYMBOL);
      if(InpOnlyChartSymbol && !InpUseTradeSymbolChart && symbol != _Symbol)
         continue;

      ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(deal, DEAL_ENTRY);
      ENUM_DEAL_TYPE type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(deal, DEAL_TYPE);
      if(!CameraIsTradeDeal(type) || !CameraShouldCaptureEntry(entry))
         continue;

      ulong position = (ulong)HistoryDealGetInteger(deal, DEAL_POSITION_ID);
      double volume = HistoryDealGetDouble(deal, DEAL_VOLUME);
      double price = HistoryDealGetDouble(deal, DEAL_PRICE);
      double profit = HistoryDealGetDouble(deal, DEAL_PROFIT);
      double commission = HistoryDealGetDouble(deal, DEAL_COMMISSION);
      double swap = HistoryDealGetDouble(deal, DEAL_SWAP);
      long magic = HistoryDealGetInteger(deal, DEAL_MAGIC);
      string comment = HistoryDealGetString(deal, DEAL_COMMENT);

      if(capture)
      {
         CameraCapture("TRADE",
                       symbol,
                       deal,
                       position,
                       entry,
                       type,
                       volume,
                       price,
                       profit,
                       commission,
                       swap,
                       magic,
                       comment);
      }

      CameraRememberDeal(dealTime, deal);
   }
}

void CameraScanVirtualEvents(const bool capture)
{
   if(!InpCaptureVirtualReplayTrades)
      return;

   string prefix = CameraVirtualEventPrefix();
   long next_index = CameraVirtualNextIndex();
   if(next_index <= 0)
      return;

   for(long index = g_lastVirtualEventIndex + 1; index <= next_index; ++index)
   {
      string item = prefix + "Q." + IntegerToString((int)index) + ".";
      double ready = 0.0;
      if(!CameraReadGlobalDouble(item + "READY", ready) || ready < 1.0)
         break;

      double entry_value = 0.0;
      double type_value = 0.0;
      double ticket_value = 0.0;
      double volume = 0.0;
      double price = 0.0;
      double profit = 0.0;
      double magic_value = 0.0;

      CameraReadGlobalDouble(item + "ENTRY", entry_value);
      CameraReadGlobalDouble(item + "TYPE", type_value);
      CameraReadGlobalDouble(item + "TICKET", ticket_value);
      CameraReadGlobalDouble(item + "VOLUME", volume);
      CameraReadGlobalDouble(item + "PRICE", price);
      CameraReadGlobalDouble(item + "PROFIT", profit);
      CameraReadGlobalDouble(item + "MAGIC", magic_value);

      ENUM_DEAL_ENTRY entry = ((int)entry_value == 1 ? DEAL_ENTRY_OUT : DEAL_ENTRY_IN);
      ENUM_DEAL_TYPE type = ((int)type_value == 1 ? DEAL_TYPE_BUY : DEAL_TYPE_SELL);
      string reason = ((int)entry_value == 1 ? "VIRTUAL_CLOSE" : "VIRTUAL_OPEN");

      if(capture)
      {
         CameraCapture(reason,
                       _Symbol,
                       (ulong)ticket_value,
                       (ulong)ticket_value,
                       entry,
                       type,
                       volume,
                       price,
                       profit,
                       0.0,
                       0.0,
                       (long)magic_value,
                       "virtual_replay");
      }

      g_lastVirtualEventIndex = index;
      GlobalVariableSet(prefix + "DONE_IDX", (double)g_lastVirtualEventIndex);
   }
}

int OnInit()
{
   if(InpTimerSeconds < 1 || InpHistoryLookbackHours < 1)
   {
      Print("ChartCamera invalid timer/history settings.");
      return INIT_PARAMETERS_INCORRECT;
   }

   CameraEnsureFolder(CameraBaseFolder(_Symbol));
   if(!InpCaptureExistingHistoryOnStart)
   {
      CameraScanDeals(false);
      CameraPrimeVirtualEvents();
   }

   if(InpCaptureOnTimer)
      EventSetTimer(InpTimerSeconds);

   PrintFormat("ChartCamera indicator ready tag=%s env=%s chart=%s folder=%s last_deal_time=%s last_deal=%d",
               CameraTag(),
               CameraEnvironment(),
               _Symbol,
               CameraBaseFolder(_Symbol),
               TimeToString(g_lastSeenDealTime, TIME_DATE | TIME_SECONDS),
               (int)g_lastSeenDealTicket);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   PrintFormat("ChartCamera indicator stopped reason=%d", reason);
}

void OnTimer()
{
   if(InpCaptureOnTimer)
   {
      CameraScanDeals(true);
      CameraScanVirtualEvents(true);
   }
}

int OnCalculate(const int rates_total,
                const int prev_calculated,
                const datetime& time[],
                const double& open[],
                const double& high[],
                const double& low[],
                const double& close[],
                const long& tick_volume[],
                const long& volume[],
                const int& spread[])
{
   if(MQLInfoInteger(MQL_TESTER))
   {
      datetime now = TimeCurrent();
      if(now != g_lastTesterPollTime)
      {
         g_lastTesterPollTime = now;
         CameraScanDeals(true);
         CameraScanVirtualEvents(true);
      }
   }
   return rates_total;
}
