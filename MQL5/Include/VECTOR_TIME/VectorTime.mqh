#ifndef VECTOR_TIME_MQH
#define VECTOR_TIME_MQH

// Reusable live clock and trading-session HUD.
// Live broker offset is measured from the MT5 trade server, never hard-coded.

datetime VTDate(int year, int month, int day, int hour = 0, int minute = 0)
{
   MqlDateTime value;
   ZeroMemory(value);
   value.year = year;
   value.mon = month;
   value.day = day;
   value.hour = hour;
   value.min = minute;
   return StructToTime(value);
}

datetime VTLastSundayUtc(int year, int month, int hour)
{
   int next_month = month == 12 ? 1 : month + 1;
   int next_year = month == 12 ? year + 1 : year;
   datetime last_day = VTDate(next_year, next_month, 1, hour) - 86400;
   MqlDateTime value;
   TimeToStruct(last_day, value);
   return last_day - value.day_of_week * 86400;
}

datetime VTNthSundayUtc(int year, int month, int occurrence, int hour)
{
   datetime first = VTDate(year, month, 1, hour);
   MqlDateTime value;
   TimeToStruct(first, value);
   int days_to_sunday = (7 - value.day_of_week) % 7;
   return first + (days_to_sunday + (occurrence - 1) * 7) * 86400;
}

bool VTLondonSummer(datetime utc)
{
   MqlDateTime value;
   TimeToStruct(utc, value);
   datetime start = VTLastSundayUtc(value.year, 3, 1);
   datetime end = VTLastSundayUtc(value.year, 10, 1);
   return utc >= start && utc < end;
}

bool VTNewYorkSummer(datetime utc)
{
   MqlDateTime value;
   TimeToStruct(utc, value);
   // US DST starts 02:00 EST (07:00 UTC), ends 02:00 EDT (06:00 UTC).
   datetime start = VTNthSundayUtc(value.year, 3, 2, 7);
   datetime end = VTNthSundayUtc(value.year, 11, 1, 6);
   return utc >= start && utc < end;
}

int VTRoundOffsetSeconds(long raw_seconds)
{
   const int step = 15 * 60;
   if(raw_seconds >= 0)
      return (int)((raw_seconds + step / 2) / step) * step;
   return (int)((raw_seconds - step / 2) / step) * step;
}

string VTOffsetText(int offset_seconds)
{
   string sign = offset_seconds >= 0 ? "+" : "-";
   int absolute = MathAbs(offset_seconds);
   return StringFormat("UTC%s%02d:%02d", sign, absolute / 3600,
                       (absolute % 3600) / 60);
}

string VTClockText(datetime value)
{
   return TimeToString(value, TIME_SECONDS);
}

string VTDurationText(int seconds)
{
   seconds = MathMax(0, seconds);
   int hours = seconds / 3600;
   int minutes = (seconds % 3600) / 60;
   int secs = seconds % 60;
   return StringFormat("%02d:%02d:%02d", hours, minutes, secs);
}

class CVectorTime
{
private:
   datetime m_utc_now;
   datetime m_broker_now;
   datetime m_local_now;
   int m_broker_offset;
   int m_local_offset;
   datetime m_last_check;
   bool m_ready;
   bool m_healthy;
   string m_health_reason;
   string m_prefix;

   void SetLabel(string suffix, int corner, int x, int y, string text,
                 int font_size, color text_color)
   {
      string name = m_prefix + suffix;
      if(ObjectFind(0, name) < 0)
      {
         ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
         ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
         ObjectSetInteger(0, name, OBJPROP_HIDDEN, true);
         ObjectSetString(0, name, OBJPROP_FONT, "Consolas");
      }
      ObjectSetInteger(0, name, OBJPROP_CORNER, corner);
      ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
      ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
      ObjectSetInteger(0, name, OBJPROP_FONTSIZE, font_size);
      ObjectSetInteger(0, name, OBJPROP_COLOR, text_color);
      ObjectSetString(0, name, OBJPROP_TEXT, text);
   }

   string SessionLine(string name, datetime local_time,
                      int open_minute, int close_minute)
   {
      MqlDateTime value;
      TimeToStruct(local_time, value);
      int now_minute = value.hour * 60 + value.min;
      int elapsed_seconds = now_minute * 60 + value.sec;
      int open_seconds = open_minute * 60;
      int close_seconds = close_minute * 60;
      bool weekday = value.day_of_week >= 1 && value.day_of_week <= 5;
      bool open = weekday && elapsed_seconds >= open_seconds &&
                  elapsed_seconds < close_seconds;
      int remaining = open ? close_seconds - elapsed_seconds : 0;
      if(!open)
      {
         datetime midnight = local_time - elapsed_seconds;
         for(int day = 0; day <= 7; day++)
         {
            datetime candidate = midnight + day * 86400 + open_seconds;
            MqlDateTime candidate_value;
            TimeToStruct(candidate, candidate_value);
            bool candidate_weekday = candidate_value.day_of_week >= 1 &&
                                     candidate_value.day_of_week <= 5;
            if(candidate_weekday && candidate > local_time)
            {
               remaining = (int)(candidate - local_time);
               break;
            }
         }
      }
      return StringFormat("%-8s %s  %s %s", name,
                          TimeToString(local_time, TIME_SECONDS),
                          open ? "OPEN end" : "CLOSED opens",
                          VTDurationText(remaining));
   }

   bool SessionIsOpen(datetime local_time, int open_minute, int close_minute)
   {
      MqlDateTime value;
      TimeToStruct(local_time, value);
      if(value.day_of_week < 1 || value.day_of_week > 5)
         return false;
      int elapsed_seconds = (value.hour * 60 + value.min) * 60 + value.sec;
      return elapsed_seconds >= open_minute * 60 &&
             elapsed_seconds < close_minute * 60;
   }

public:
   CVectorTime()
   {
      m_utc_now = 0;
      m_broker_now = 0;
      m_local_now = 0;
      m_broker_offset = 0;
      m_local_offset = 0;
      m_last_check = 0;
      m_ready = false;
      m_healthy = false;
      m_health_reason = "time service not initialized";
      m_prefix = "VECTOR_TIME_";
   }

   bool Update(bool force = false)
   {
      datetime utc = TimeGMT();
      datetime broker = TimeTradeServer();
      datetime local = TimeLocal();
      if(utc <= 0)
      {
         m_healthy = false;
         m_health_reason = "UTC clock unavailable";
         return false;
      }
      if(broker <= 0)
         broker = TimeCurrent();
      if(broker <= 0)
      {
         m_healthy = false;
         m_health_reason = "broker server clock unavailable";
         return false;
      }

      m_utc_now = utc;
      m_broker_now = broker;
      m_local_now = local > 0 ? local : utc;
      if(force || !m_ready || utc - m_last_check >= 30)
      {
         long raw_broker_offset = (long)broker - (long)utc;
         int measured_broker = VTRoundOffsetSeconds(raw_broker_offset);
         int measured_local = VTRoundOffsetSeconds((long)m_local_now - (long)utc);
         int previous_broker = m_broker_offset;
         int residual = (int)MathAbs(raw_broker_offset - measured_broker);
         if(MathAbs(measured_broker) > 14 * 3600)
         {
            m_healthy = false;
            m_health_reason = "broker UTC offset outside valid range";
            return false;
         }
         if(residual > 120)
         {
            m_healthy = false;
            m_health_reason = StringFormat(
               "broker/UTC clocks disagree by %d seconds", residual);
            return false;
         }
         m_broker_offset = measured_broker;
         if(MathAbs(measured_local) <= 14 * 3600)
            m_local_offset = measured_local;
         m_last_check = utc;
         if(m_ready && previous_broker != m_broker_offset)
            Print("VECTOR TIME: broker UTC offset changed ",
                  VTOffsetText(previous_broker), " -> ",
                  VTOffsetText(m_broker_offset));
      }
      m_ready = true;
      m_healthy = true;
      m_health_reason = "";
      return true;
   }

   bool Ready() const { return m_ready; }
   bool Healthy() const
   {
      if(!m_ready || !m_healthy || m_last_check <= 0)
         return false;
      return MathAbs((long)TimeGMT() - (long)m_last_check) <= 90;
   }
   string HealthReason() const
   {
      if(!m_ready)
         return m_health_reason;
      if(!m_healthy)
         return m_health_reason;
      if(MathAbs((long)TimeGMT() - (long)m_last_check) > 90)
         return "time synchronization is stale";
      return "";
   }
   datetime UtcNow() const { return m_utc_now; }
   datetime BrokerNow() const { return m_broker_now; }
   datetime LocalNow() const { return m_local_now; }
   int BrokerUtcOffsetSeconds() const { return m_broker_offset; }
   int LocalUtcOffsetSeconds() const { return m_local_offset; }

   datetime BrokerToUtc(datetime broker_time) const
   {
      return broker_time - m_broker_offset;
   }

   datetime UtcToBroker(datetime utc_time) const
   {
      return utc_time + m_broker_offset;
   }

   datetime TokyoTime(datetime utc) const { return utc + 9 * 3600; }
   datetime LondonTime(datetime utc) const
   {
      return utc + (VTLondonSummer(utc) ? 3600 : 0);
   }
   datetime NewYorkTime(datetime utc) const
   {
      return utc + (VTNewYorkSummer(utc) ? -4 * 3600 : -5 * 3600);
   }

   string Diagnostic() const
   {
      return StringFormat("broker=%s local=%s",
                          VTOffsetText(m_broker_offset),
                          VTOffsetText(m_local_offset));
   }

   void DrawHud(int corner = CORNER_LEFT_UPPER, int x = 10, int y = 20,
                int font_size = 9, color text_color = clrWhite,
                color open_color = clrLime, color closed_color = clrGray)
   {
      if(!Healthy())
      {
         SetLabel("TITLE", corner, x, y, "VECTOR TIME ERROR - CHECK EA",
                  font_size, clrRed);
         SetLabel("STATUS", corner, x, y + font_size + 5,
                  HealthReason(), font_size, clrRed);
         ChartRedraw(0);
         return;
      }
      datetime tokyo = TokyoTime(m_utc_now);
      datetime london = LondonTime(m_utc_now);
      datetime new_york = NewYorkTime(m_utc_now);
      int line = font_size + 5;
      SetLabel("TITLE", corner, x, y, "VECTOR TIME - automatic offsets",
               font_size, text_color);
      SetLabel("UTC", corner, x, y + line,
               "UTC      " + VTClockText(m_utc_now), font_size, text_color);
      SetLabel("LOCAL", corner, x, y + line * 2,
               "Local    " + VTClockText(m_local_now) + "  " +
               VTOffsetText(m_local_offset), font_size, text_color);
      SetLabel("BROKER", corner, x, y + line * 3,
               "Broker   " + VTClockText(m_broker_now) + "  " +
               VTOffsetText(m_broker_offset), font_size, text_color);
      SetLabel("TOKYO", corner, x, y + line * 4,
               SessionLine("Tokyo", tokyo, 9 * 60, 18 * 60),
               font_size, SessionIsOpen(tokyo, 9 * 60, 18 * 60) ?
                          open_color : closed_color);
      SetLabel("LONDON", corner, x, y + line * 5,
               SessionLine("London", london, 8 * 60, 17 * 60),
               font_size, SessionIsOpen(london, 8 * 60, 17 * 60) ?
                          open_color : closed_color);
      SetLabel("NEWYORK", corner, x, y + line * 6,
               SessionLine("New York", new_york, 8 * 60, 17 * 60),
               font_size, SessionIsOpen(new_york, 8 * 60, 17 * 60) ?
                          open_color : closed_color);
      SetLabel("STATUS", corner, x, y + line * 7,
               "Time sync OK", font_size, open_color);
      ChartRedraw(0);
   }

   void RemoveHud()
   {
      string suffixes[] = {"TITLE", "UTC", "BROKER", "LOCAL",
                           "TOKYO", "LONDON", "NEWYORK", "STATUS"};
      for(int i = 0; i < ArraySize(suffixes); i++)
         ObjectDelete(0, m_prefix + suffixes[i]);
   }
};

#endif
