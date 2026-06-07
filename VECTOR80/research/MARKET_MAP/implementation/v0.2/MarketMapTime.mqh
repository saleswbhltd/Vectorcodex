#ifndef MARKET_MAP_TIME_MQH
#define MARKET_MAP_TIME_MQH

datetime MMLastSunday(int year, int month, int hour)
{
   MqlDateTime value;
   ZeroMemory(value);
   value.year = year;
   value.mon = month;
   value.day = 31;
   value.hour = hour;
   datetime result = StructToTime(value);
   TimeToStruct(result, value);
   return result - value.day_of_week * 86400;
}

int MMBrokerUtcOffsetHours(datetime broker_time)
{
   MqlDateTime value;
   TimeToStruct(broker_time, value);
   datetime summer_start = MMLastSunday(value.year, 3, 4);
   datetime winter_start = MMLastSunday(value.year, 10, 4);
   if(broker_time >= summer_start && broker_time < winter_start)
      return 3;
   return 2;
}

datetime MMBrokerToUtc(datetime broker_time)
{
   return broker_time - MMBrokerUtcOffsetHours(broker_time) * 3600;
}

#endif

