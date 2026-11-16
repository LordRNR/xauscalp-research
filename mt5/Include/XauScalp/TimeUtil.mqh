//+------------------------------------------------------------------+
//| TimeUtil.mqh - server time <-> UTC and session anchors (DST)     |
//| Mirrors src/xauscalp/data/server_time.py and features/sessions.py|
//|                                                                  |
//| MQL5 facts (official docs): TimeGMT() is derived from the local  |
//| PC clock; in the Strategy Tester TimeGMT()==TimeTradeServer().   |
//| There is no API for historical server offsets, so in the tester  |
//| the server rule MUST be declared (and verified in Python).       |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14 via XauScalp_ReadOnly.mq5, 0 errors. |
//|         Compiling proves syntax only; not yet run in the Tester. |
//+------------------------------------------------------------------+
#ifndef XAUSCALP_TIMEUTIL_MQH
#define XAUSCALP_TIMEUTIL_MQH

enum ENUM_TZ_POLICY
{
   TZ_UNKNOWN          = 0,  // Unknown: refuse to compute sessions
   TZ_LIVE_CLOCK       = 1,  // Live only: current server-GMT offset (PC clock)
   TZ_FIXED            = 2,  // Fixed offset = base minutes
   TZ_BASE_PLUS_US_DST = 3,  // base, +60 min while New York observes DST
   TZ_BASE_PLUS_EU_DST = 4   // base, +60 min while EU/UK observe DST
};

const int TZ_INVALID = -999999;

datetime MakeTime(const int y, const int mo, const int d, const int h, const int mi)
{
   MqlDateTime s;
   ZeroMemory(s);
   s.year = y; s.mon = mo; s.day = d; s.hour = h; s.min = mi; s.sec = 0;
   return StructToTime(s);
}

int DayOfWeek(const datetime t)
{
   MqlDateTime s;
   TimeToStruct(t, s);
   return s.day_of_week;           // 0 = Sunday
}

// n-th Sunday of month (n >= 1)
int NthSunday(const int y, const int mo, const int n)
{
   int dow = DayOfWeek(MakeTime(y, mo, 1, 0, 0));
   int first = 1 + (7 - dow) % 7;
   return first + 7 * (n - 1);
}

int LastSunday(const int y, const int mo)
{
   int ny = (mo == 12) ? y + 1 : y;
   int nm = (mo == 12) ? 1 : mo + 1;
   datetime last = MakeTime(ny, nm, 1, 0, 0) - 86400;
   MqlDateTime s;
   TimeToStruct(last, s);
   return s.day - s.day_of_week;
}

// US: 2nd Sunday of March 02:00 EST (07:00 UTC) -> 1st Sunday of Nov 02:00 EDT (06:00 UTC)
bool IsUsDst(const datetime utc)
{
   MqlDateTime s;
   TimeToStruct(utc, s);
   datetime a = MakeTime(s.year, 3, NthSunday(s.year, 3, 2), 7, 0);
   datetime b = MakeTime(s.year, 11, NthSunday(s.year, 11, 1), 6, 0);
   return utc >= a && utc < b;
}

// EU/UK: last Sunday of March 01:00 UTC -> last Sunday of October 01:00 UTC
bool IsEuDst(const datetime utc)
{
   MqlDateTime s;
   TimeToStruct(utc, s);
   datetime a = MakeTime(s.year, 3, LastSunday(s.year, 3), 1, 0);
   datetime b = MakeTime(s.year, 10, LastSunday(s.year, 10), 1, 0);
   return utc >= a && utc < b;
}

// UTC instant of local wall time hh:mm on date y-mo-d. zone: 0 = London, 1 = New York
datetime LocalAnchorUtc(const int zone, const int y, const int mo, const int d,
                        const int hh, const int mm)
{
   datetime local = MakeTime(y, mo, d, hh, mm);
   if(zone == 0)
   {
      datetime std_utc = local;                     // GMT
      return IsEuDst(std_utc) ? std_utc - 3600 : std_utc;
   }
   datetime std_utc = local + 5 * 3600;             // EST
   return IsUsDst(std_utc) ? std_utc - 3600 : std_utc;
}

class CServerClock
{
private:
   ENUM_TZ_POLICY m_policy;
   int            m_base_min;
   bool           m_tester;

   int OffsetSecondsAtUtc(const datetime utc) const
   {
      switch(m_policy)
      {
         case TZ_LIVE_CLOCK:
         {
            if(m_tester) return TZ_INVALID;     // TimeGMT()==server time in the tester
            long raw = (long)(TimeTradeServer() - TimeGMT());
            return (int)(MathRound(raw / 1800.0) * 1800);
         }
         case TZ_FIXED:            return m_base_min * 60;
         case TZ_BASE_PLUS_US_DST: return m_base_min * 60 + (IsUsDst(utc) ? 3600 : 0);
         case TZ_BASE_PLUS_EU_DST: return m_base_min * 60 + (IsEuDst(utc) ? 3600 : 0);
         default:                  return TZ_INVALID;
      }
   }

public:
   void Init(const ENUM_TZ_POLICY policy, const int base_min)
   {
      m_policy = policy;
      m_base_min = base_min;
      m_tester = (bool)MQLInfoInteger(MQL_TESTER);
   }
   bool Usable() const
   {
      if(m_policy == TZ_UNKNOWN) return false;
      if(m_policy == TZ_LIVE_CLOCK && m_tester) return false;
      return true;
   }
   string Describe() const
   {
      return EnumToString(m_policy) + " base=" + IntegerToString(m_base_min) + "min" +
             (m_tester ? " [tester]" : "");
   }
   // server wall time -> UTC (0 if not determinable)
   datetime ToUtc(const datetime server) const
   {
      if(!Usable()) return 0;
      int off = OffsetSecondsAtUtc(server - m_base_min * 60);
      if(off == TZ_INVALID) return 0;
      datetime u = server - off;
      // re-check with the candidate UTC (rule-based policies switch on UTC instants)
      int off2 = OffsetSecondsAtUtc(u);
      if(off2 != off) u = server - off2;
      return u;
   }
   datetime ToServer(const datetime utc) const
   {
      if(!Usable()) return 0;
      int off = OffsetSecondsAtUtc(utc);
      if(off == TZ_INVALID) return 0;
      return utc + off;
   }
};

#endif
