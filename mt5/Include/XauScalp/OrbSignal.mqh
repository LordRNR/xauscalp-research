//+------------------------------------------------------------------+
//| OrbSignal.mqh - ORB rules, mirror of src/xauscalp/strategies/orb.py|
//| One record per (day, session) with the same statuses as Python:  |
//| NO_DATA, OR_INCOMPLETE, NO_ATR, NO_BREAKOUT, DATA_GAP_AT_SIGNAL, |
//| REJECT_SPREAD, REJECT_COST, SIGNAL. Produces PROPOSALS only.     |
//|                                                                  |
//| Known, documented differences vs Python (checked by parity tool):|
//|  * spread for the cost/spread filters = live tick spread at the  |
//|    decision (Python: bar-close spread of the decision bar);      |
//|  * ATR(M5,14) Wilder seeded ATR_LOOKBACK_DAYS calendar days back |
//|    (Python: seeded at segment start). The seed error decays as   |
//|    (13/14)^n with n = M5 bars actually used, so the EA REQUIRES  |
//|    ATR_MIN_BARS bars (a 502-bar CALENDAR window held only ~110   |
//|    bars on Monday mornings: parity1/2 ATR off by 0.10-0.13 %).   |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14 via XauScalp_ReadOnly.mq5, 0 errors. |
//|         Tester run 1-2 (2025-09..10): NOT equivalent to Python (ATR |
//|         window bug, fixed + recompiled 0/0); parity3 pending.      |
//+------------------------------------------------------------------+
#ifndef XAUSCALP_ORBSIGNAL_MQH
#define XAUSCALP_ORBSIGNAL_MQH

#include "TimeUtil.mqh"

struct OrbParams
{
   int    or_minutes;
   double sl_atr;
   double tp_r;
   int    entry_window_min;
   int    max_hold_min;
   double buffer_atr;
   double max_cost_frac;
   double max_spread;     // same gate as the risk manager (price units)
   double slippage;       // per market fill (price units)
   double extra_spread;   // 0 with broker data (only for Dukascopy-based research parity)
};

struct OrbRecord
{
   string   session;
   string   day;          // UTC date of the session anchor
   string   status;
   datetime anchor_utc;
   datetime bar_server;   // decision bar (open time, server)
   datetime bar_utc;
   int      or_bars;
   double   or_high, or_low, atr, or_width_atr, bar_close;
   double   spread_now, spread_bar, sl_dist, tp_dist, cost, cost_frac;
   int      direction;
   double   entry, sl, tp;
};

void ResetRecord(OrbRecord &r)
{
   r.session = ""; r.day = ""; r.status = "";
   r.anchor_utc = 0; r.bar_server = 0; r.bar_utc = 0; r.or_bars = 0;
   r.or_high = EMPTY_VALUE; r.or_low = EMPTY_VALUE; r.atr = EMPTY_VALUE;
   r.or_width_atr = EMPTY_VALUE; r.bar_close = EMPTY_VALUE; r.spread_now = EMPTY_VALUE;
   r.spread_bar = EMPTY_VALUE; r.sl_dist = EMPTY_VALUE; r.tp_dist = EMPTY_VALUE;
   r.cost = EMPTY_VALUE; r.cost_frac = EMPTY_VALUE; r.direction = 0;
   r.entry = EMPTY_VALUE; r.sl = EMPTY_VALUE; r.tp = EMPTY_VALUE;
}

// Wilder ATR(14) on M5 Bid bars that have CLOSED by `decision_server`
// (bar open + 300 s <= decision time), seeded with the first TR of the window,
// exactly like pandas ewm(alpha=1/14, adjust=False, min_periods=14).
// The window is measured in CALENDAR time and must hold enough BARS: the market is closed
// ~2 days a week, so "N bars back" cannot be expressed as N*300 s (that bug left only ~110
// bars on Monday London sessions and the seed error (13/14)^110 ~ 3e-4 was visible).
// Fewer than ATR_MIN_BARS bars -> EMPTY_VALUE (status NO_ATR) instead of a silently
// less accurate number: (13/14)^ATR_MIN_BARS ~ 5e-7 relative seed error.
#define ATR_LOOKBACK_DAYS 10
#define ATR_MIN_BARS      300
double AtrM5Wilder(const string sym, const datetime decision_server, const int n = 14)
{
   MqlRates r[];
   int got = CopyRates(sym, PERIOD_M5, decision_server - ATR_LOOKBACK_DAYS * 86400,
                       decision_server, r);
   if(got <= 0) return EMPTY_VALUE;
   double atr = 0, prev_close = 0;
   int used = 0;
   for(int i = 0; i < got; i++)
   {
      if(r[i].time + 300 > decision_server) break;      // not closed yet
      double tr = r[i].high - r[i].low;
      if(used > 0)
         tr = MathMax(tr, MathMax(MathAbs(r[i].high - prev_close), MathAbs(r[i].low - prev_close)));
      atr = (used == 0) ? tr : atr + (tr - atr) / n;
      prev_close = r[i].close;
      used++;
   }
   return (used >= ATR_MIN_BARS) ? atr : EMPTY_VALUE;
}

class COrbSession
{
private:
   string m_name;
   int    m_zone;         // 0 London, 1 New York
   int    m_hh, m_mm;
   int    m_day_key;
   bool   m_done;
   bool   m_or_ready;
   double m_or_h, m_or_l;
   int    m_or_bars;

   void Reset(const int key)
   {
      m_day_key = key; m_done = false; m_or_ready = false;
      m_or_h = EMPTY_VALUE; m_or_l = EMPTY_VALUE; m_or_bars = 0;
   }

public:
   void Init(const string name, const int zone, const int hh, const int mm)
   {
      m_name = name; m_zone = zone; m_hh = hh; m_mm = mm;
      Reset(-1);
   }
   string Name() const { return m_name; }
   bool   Done() const { return m_done; }

   // Evaluate the bar that just CLOSED. `next_open_server` is the open time of the bar
   // that follows it (the bar in which execution would happen).
   // Returns true when the day's record is final (rec filled).
   bool OnClosedBar(const string sym, const CServerClock &clock, const OrbParams &p,
                    const MqlRates &bar, const datetime next_open_server, OrbRecord &rec)
   {
      datetime bar_utc = clock.ToUtc(bar.time);
      if(bar_utc == 0) return false;
      MqlDateTime u;
      TimeToStruct(bar_utc, u);
      if(u.day_of_week == 0 || u.day_of_week == 6) return false;
      int key = u.year * 10000 + u.mon * 100 + u.day;
      if(key != m_day_key) Reset(key);
      if(m_done) return false;

      datetime anchor = LocalAnchorUtc(m_zone, u.year, u.mon, u.day, m_hh, m_mm);
      datetime or_end = anchor + p.or_minutes * 60;
      datetime win_end = or_end + p.entry_window_min * 60;
      if(bar_utc < or_end) return false;

      ResetRecord(rec);
      rec.session = m_name;
      rec.day = StringFormat("%04d-%02d-%02d", u.year, u.mon, u.day);
      rec.anchor_utc = anchor; rec.bar_server = bar.time; rec.bar_utc = bar_utc;
      rec.bar_close = bar.close;

      if(!m_or_ready)
      {
         MqlRates orr[];
         datetime a_srv = clock.ToServer(anchor), e_srv = clock.ToServer(or_end);
         int n = (a_srv > 0 && e_srv > 0) ? CopyRates(sym, PERIOD_M1, a_srv, e_srv - 60, orr) : -1;
         m_or_bars = MathMax(n, 0);
         rec.or_bars = m_or_bars;
         if(n <= 0)                       { rec.status = "NO_DATA"; m_done = true; return true; }
         if(n < 0.8 * p.or_minutes)       { rec.status = "OR_INCOMPLETE"; m_done = true; return true; }
         m_or_h = orr[0].high; m_or_l = orr[0].low;
         for(int i = 1; i < n; i++)
         {
            m_or_h = MathMax(m_or_h, orr[i].high);
            m_or_l = MathMin(m_or_l, orr[i].low);
         }
         m_or_ready = true;
      }
      rec.or_bars = m_or_bars; rec.or_high = m_or_h; rec.or_low = m_or_l;
      if(bar_utc >= win_end) { rec.status = "NO_BREAKOUT"; m_done = true; return true; }

      double atr = AtrM5Wilder(sym, bar.time + 60);
      if(atr == EMPTY_VALUE || atr <= 0) { rec.status = "NO_ATR"; m_done = true; return true; }
      rec.atr = atr;
      rec.or_width_atr = (m_or_h - m_or_l) / atr;
      double buf = p.buffer_atr * atr;
      int d = 0;
      if(bar.close > m_or_h + buf)      d = 1;
      else if(bar.close < m_or_l - buf) d = -1;
      else return false;                                   // keep scanning the window

      MqlTick tk;
      bool have_tick = SymbolInfoTick(sym, tk);
      double point = SymbolInfoDouble(sym, SYMBOL_POINT);
      rec.direction = d;
      rec.spread_bar = bar.spread * point + p.extra_spread;
      rec.spread_now = have_tick ? (tk.ask - tk.bid) + p.extra_spread : EMPTY_VALUE;
      rec.sl_dist = p.sl_atr * atr;
      rec.tp_dist = p.tp_r * rec.sl_dist;
      double sp = (rec.spread_now == EMPTY_VALUE) ? rec.spread_bar : rec.spread_now;
      rec.cost = sp + 2 * p.slippage;
      rec.cost_frac = rec.cost / rec.sl_dist;
      if(have_tick)
      {
         int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
         rec.entry = (d == 1) ? tk.ask : tk.bid;
         rec.sl = NormalizeDouble(rec.entry - d * rec.sl_dist, digits);
         rec.tp = NormalizeDouble(rec.entry + d * rec.tp_dist, digits);
      }
      if(next_open_server - bar.time > 300)       rec.status = "DATA_GAP_AT_SIGNAL";
      else if(sp > p.max_spread)                  rec.status = "REJECT_SPREAD";
      else if(rec.cost > p.max_cost_frac * rec.sl_dist) rec.status = "REJECT_COST";
      else if(!have_tick)                         rec.status = "DATA_GAP_AT_SIGNAL";
      else                                        rec.status = "SIGNAL";
      m_done = true;
      return true;
   }
};

#endif
