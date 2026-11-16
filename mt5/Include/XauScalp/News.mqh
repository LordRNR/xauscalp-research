//+------------------------------------------------------------------+
//| News.mqh - high-impact event calendar (Common\Files CSV)         |
//| Hardened after audit M2: the calendar is "ok" only if it parsed  |
//| WITHOUT discarded lines, holds >= 1 event and extends at least   |
//| NEWS_MIN_FUTURE_DAYS beyond the decision time; it is reloaded    |
//| periodically; impact matching is case-insensitive.               |
//| Contains NO trading code.                                        |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14 via XauScalp_Exec.mq5, 0 err, 0 warn. |
//|         Never run in the Tester.                                  |
//+------------------------------------------------------------------+
#ifndef XAUSCALP_NEWS_MQH
#define XAUSCALP_NEWS_MQH

#define NEWS_MIN_FUTURE_DAYS 14
#define NEWS_MAX_GAP_DAYS    45

class CNewsCalendar
{
private:
   datetime m_t[];
   int      m_discarded;
   int      m_lines;
   string   m_file;
   datetime m_loaded_at;

public:
   int Events() const { return ArraySize(m_t); }
   int Discarded() const { return m_discarded; }

   // Returns false if the file is missing/unreadable (calendar then "not ok").
   bool Load(const string file)
   {
      m_file = file;
      ArrayResize(m_t, 0);
      m_discarded = 0; m_lines = 0;
      m_loaded_at = TimeLocal();
      if(!FileIsExist(file, FILE_COMMON)) return false;
      int h = FileOpen(file, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
      if(h == INVALID_HANDLE) return false;
      while(!FileIsEnding(h))
      {
         string line = FileReadString(h);
         StringTrimLeft(line); StringTrimRight(line);
         if(StringLen(line) == 0 || StringGetCharacter(line, 0) == '#' ||
            StringFind(line, "utc_time") == 0) continue;
         m_lines++;
         string f[];
         string impact;
         if(StringFind(line, "\"") >= 0 || StringSplit(line, ',', f) != 3) { m_discarded++; continue; }
         impact = f[2];
         StringToLower(impact);
         if(StringFind(impact, "high") < 0) continue;          // low/medium: not a blackout
         string ts = f[0];
         StringReplace(ts, "T", " "); StringReplace(ts, "Z", ""); StringReplace(ts, "-", ".");
         datetime t = StringToTime(ts);                         // UTC
         if(t <= 0) { m_discarded++; continue; }
         int n = ArraySize(m_t);
         ArrayResize(m_t, n + 1);
         m_t[n] = t;
      }
      FileClose(h);
      return true;
   }

   // Reload at most once an hour (long-running EAs must not run on a stale calendar).
   void ReloadIfOld()
   {
      if(TimeLocal() - m_loaded_at >= 3600) Load(m_file);
   }

   bool Ok(const datetime utc) const
   {
      if(m_discarded > 0 || ArraySize(m_t) == 0) return false;
      // contiguous coverage: the file must span the decision time AND 14 days beyond it
      // (a single far-away event, or a calendar that starts later than `utc`, is not coverage)
      datetime lo = m_t[0], hi = m_t[0];
      for(int i = 1; i < ArraySize(m_t); i++)
      {
         if(m_t[i] < lo) lo = m_t[i];
         if(m_t[i] > hi) hi = m_t[i];
      }
      if(!(lo <= utc && hi >= utc + NEWS_MIN_FUTURE_DAYS * 86400)) return false;
      // no hole: consecutive high-impact events overlapping [utc-1d, utc+14d] at most NEWS_MAX_GAP_DAYS apart
      datetime s[];
      ArrayCopy(s, m_t);
      ArraySort(s);
      for(int i = 1; i < ArraySize(s); i++)
         if(s[i] >= utc - 86400 && s[i - 1] <= utc + NEWS_MIN_FUTURE_DAYS * 86400 &&
            s[i] - s[i - 1] > NEWS_MAX_GAP_DAYS * 86400) return false;
      return true;
   }

   bool InBlackout(const datetime utc, const int before_min, const int after_min) const
   {
      for(int i = 0; i < ArraySize(m_t); i++)
         if(utc >= m_t[i] - before_min * 60 && utc <= m_t[i] + after_min * 60) return true;
      return false;
   }
};

#endif
