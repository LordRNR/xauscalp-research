//+------------------------------------------------------------------+
//| RiskGuard.mqh - mirror of src/xauscalp/risk/manager.py           |
//| EVALUATES proposals only. It contains NO order-sending code.     |
//| Fail-closed: any invalid number -> rejection with a reason.      |
//| Money figures use the broker's own calculators: OrderCalcProfit  |
//| (loss at SL incl. currency conversion) and OrderCalcMargin.      |
//|                                                                  |
//| Audit follow-up (2026-11-12): sizing from the WORST of proposal  |
//| entry and live quote; SL beyond the triggering price and outside |
//| stops/freeze level; staleness vs TimeTradeServer(); day/week     |
//| anchors reconstructed from deal history; fail-closed counters.   |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14 via XauScalp_ReadOnly.mq5, 0 errors. |
//|         Compiling proves syntax only; not yet run in the Tester. |
//+------------------------------------------------------------------+
#ifndef XAUSCALP_RISKGUARD_MQH
#define XAUSCALP_RISKGUARD_MQH

#include "TimeUtil.mqh"

// Hard ceilings: identical to HARD_LIMITS in src/xauscalp/config.py
#define HARD_MAX_RISK_PCT        1.0
#define HARD_MAX_DAILY_LOSS_PCT  3.0
#define HARD_MAX_WEEKLY_LOSS_PCT 6.0
#define HARD_MAX_DRAWDOWN_PCT   10.0
#define HARD_MAX_POSITIONS         1
#define HARD_MAX_TRADES_PER_DAY   10
#define HARD_MAX_MARGIN_USAGE   50.0
// Sanity bounds: identical to SANITY_BOUNDS in src/xauscalp/config.py
#define SANE_MIN_SPREAD   0.01
#define SANE_MAX_SPREAD   5.0
#define SANE_MIN_AGE_S    1.0
#define SANE_MAX_AGE_S  120.0
#define SANE_MIN_ERRORS     1
#define SANE_MAX_ERRORS    10
#define SANE_MIN_SLIP     0.01
#define SANE_MAX_SLIP    10.0

bool XsValid(const double v) { return MathIsValidNumber(v) && v != EMPTY_VALUE; }
bool XsPos(const double v)   { return XsValid(v) && v > 0.0; }

struct XsRiskConfig
{
   double risk_pct, daily_loss_pct, weekly_loss_pct, max_dd_pct;
   int    max_positions, max_trades_day, max_consecutive_errors;
   double max_spread, max_data_age_s, slippage, commission_per_lot, max_margin_usage_pct;
};

struct XsRiskResult
{
   bool   approved;
   double volume;
   double risk_money;
   double budget;
   double loss_per_lot;
   double margin;
   string reasons;
};

void XsResetResult(XsRiskResult &r)
{
   r.approved = false; r.volume = 0; r.risk_money = 0; r.budget = 0;
   r.loss_per_lot = EMPTY_VALUE; r.margin = EMPTY_VALUE; r.reasons = "";
}

string XsCheckRiskConfig(const XsRiskConfig &c)
{
   if(!XsPos(c.risk_pct) || c.risk_pct > HARD_MAX_RISK_PCT) return "risk_pct";
   if(!XsPos(c.daily_loss_pct) || c.daily_loss_pct > HARD_MAX_DAILY_LOSS_PCT) return "daily_loss_pct";
   if(!XsPos(c.weekly_loss_pct) || c.weekly_loss_pct > HARD_MAX_WEEKLY_LOSS_PCT) return "weekly_loss_pct";
   if(!XsPos(c.max_dd_pct) || c.max_dd_pct > HARD_MAX_DRAWDOWN_PCT) return "max_dd_pct";
   if(c.max_positions < 0 || c.max_positions > HARD_MAX_POSITIONS) return "max_positions";
   if(c.max_trades_day < 0 || c.max_trades_day > HARD_MAX_TRADES_PER_DAY) return "max_trades_day";
   if(!XsPos(c.max_margin_usage_pct) || c.max_margin_usage_pct > HARD_MAX_MARGIN_USAGE) return "max_margin_usage_pct";
   if(!XsValid(c.max_spread) || c.max_spread < SANE_MIN_SPREAD || c.max_spread > SANE_MAX_SPREAD) return "max_spread";
   if(!XsValid(c.max_data_age_s) || c.max_data_age_s < SANE_MIN_AGE_S || c.max_data_age_s > SANE_MAX_AGE_S) return "max_data_age_s";
   if(c.max_consecutive_errors < SANE_MIN_ERRORS || c.max_consecutive_errors > SANE_MAX_ERRORS) return "max_consecutive_errors";
   if(!XsValid(c.slippage) || c.slippage < SANE_MIN_SLIP || c.slippage > SANE_MAX_SLIP) return "slippage";
   if(!XsValid(c.commission_per_lot) || c.commission_per_lot < 0) return "commission";
   return "";
}

class CRiskGuard
{
private:
   XsRiskConfig m_c;
   string       m_sym;
   long         m_magic;
   string       m_prefix;
   int          m_consecutive_errors;
   bool         m_tester;
   datetime     m_init_time;
   double       m_init_eq;

   void Add(string &reasons, const string code) const
   {
      if(StringFind(reasons, code) < 0)
         reasons += (reasons == "" ? "" : "|") + code;
   }
   datetime DayStart(const datetime t) const
   {
      MqlDateTime s; TimeToStruct(t, s);
      return MakeTime(s.year, s.mon, s.day, 0, 0);
   }
   datetime WeekStart(const datetime t) const
   {
      MqlDateTime s; TimeToStruct(t, s);
      int back = (s.day_of_week + 6) % 7;            // days since Monday
      return DayStart(t) - back * 86400;
   }
   string Key(const datetime t) const
   {
      MqlDateTime s; TimeToStruct(t, s);
      return StringFormat("%04d%02d%02d", s.year, s.mon, s.day);
   }
   // Equity at `since` reconstructed from deal history: current equity minus the realised
   // result of every deal since then (profit + commission + swap + fee). Open P/L is not
   // reconstructable and is ignored (documented). Returns EMPTY_VALUE if history fails.
   double EquityAt(const datetime since) const
   {
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      if(!XsPos(eq) || !HistorySelect(since, TimeTradeServer() + 60)) return EMPTY_VALUE;
      double realised = 0;
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
      {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0) return EMPTY_VALUE;
         realised += HistoryDealGetDouble(tk, DEAL_PROFIT) + HistoryDealGetDouble(tk, DEAL_COMMISSION)
                   + HistoryDealGetDouble(tk, DEAL_SWAP) + HistoryDealGetDouble(tk, DEAL_FEE);
      }
      return eq - realised;
   }
   // Anchor = the HIGHER of the stored value and the reconstruction: an EA started
   // mid-day after losses cannot reset the daily limit (audit M5).
   double Anchor(const string name, const datetime since) const
   {
      double rec = EquityAt(since);
      double stored = GlobalVariableCheck(name) ? GlobalVariableGet(name) : EMPTY_VALUE;
      double a = EMPTY_VALUE;
      if(XsPos(rec) && XsPos(stored)) a = MathMax(rec, stored);
      else if(XsPos(rec)) a = rec;
      else if(XsPos(stored)) a = stored;
      // Strategy Tester only: the simulated account starts at the deposit and has no earlier deals,
      // but HistorySelect cannot reconstruct a period that began before the test (observed: the
      // first test week gave INVALID_ACCOUNT, 10 sessions). Seed with the equity at test start.
      // Never used live: there the reconstruction/stored value is mandatory (fail-closed).
      if(!XsPos(a) && m_tester && since <= m_init_time && XsPos(m_init_eq)) a = m_init_eq;
      if(XsPos(a)) GlobalVariableSet(name, a);
      return a;
   }

public:
   bool Init(const string sym, const long magic, const XsRiskConfig &c, string &err)
   {
      err = XsCheckRiskConfig(c);
      if(err != "") return false;
      m_c = c; m_sym = sym; m_magic = magic;
      m_prefix = "xauscalp.ro." + (MQLInfoInteger(MQL_TESTER) ? "T." : "L.") + (string)AccountInfoInteger(ACCOUNT_LOGIN) + "." + sym + ".";   // per account (audit M2)
      m_consecutive_errors = 0;
      m_tester = (bool)MQLInfoInteger(MQL_TESTER);
      m_init_time = TimeTradeServer();
      m_init_eq = AccountInfoDouble(ACCOUNT_EQUITY);
      return true;
   }
   void ErrorOccurred()  { m_consecutive_errors++; }
   void ErrorCleared()   { m_consecutive_errors = 0; }
   // Stage C keeps the counter in a persistent GlobalVariable and injects it before Evaluate.
   void SetConsecutiveErrors(const int n) { m_consecutive_errors = n; }
   int  ConsecutiveErrors() const { return m_consecutive_errors; }

   // Called periodically: anchors, peak equity (kept alive: GVs expire after 4 weeks
   // without access) and the persistent drawdown lock.
   void UpdateAnchors()
   {
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      if(!XsPos(eq)) return;
      datetime now = TimeTradeServer();
      Anchor(m_prefix + "day." + Key(now), DayStart(now));
      Anchor(m_prefix + "week." + Key(WeekStart(now)), WeekStart(now));
      string pk = m_prefix + "peak";
      double peak = GlobalVariableCheck(pk) ? GlobalVariableGet(pk) : eq;
      peak = MathMax(peak, eq);
      GlobalVariableSet(pk, peak);
      if((1.0 - eq / peak) * 100.0 >= m_c.max_dd_pct)
         GlobalVariableSet(m_prefix + "ddlock", 1.0);   // only a human deletes it (F3)
   }

   // Counts ANY position on the symbol (any magic). If a position cannot be read the
   // count is forced to the limit: fail-closed (audit L3).
   int OpenPositionsOnSymbol() const
   {
      int n = 0;
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         string s = PositionGetSymbol(i);
         if(s == "" || s == m_sym) n++;
      }
      return n;
   }

   int TradesToday() const
   {
      datetime now = TimeTradeServer();
      if(!HistorySelect(DayStart(now), now + 60)) return 9999;   // unknown -> limit hit
      int n = 0;
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
      {
         ulong tk = HistoryDealGetTicket(i);
         if(tk == 0) return 9999;
         long entry = HistoryDealGetInteger(tk, DEAL_ENTRY);
         if(HistoryDealGetString(tk, DEAL_SYMBOL) == m_sym &&
            HistoryDealGetInteger(tk, DEAL_MAGIC) == m_magic &&
            (entry == DEAL_ENTRY_IN || entry == DEAL_ENTRY_INOUT))
            n++;
      }
      return n;
   }

   void Evaluate(const int direction, const double entry, const double sl, const double tp,
                 const bool news_blackout, const bool news_calendar_ok, XsRiskResult &r)
   {
      XsResetResult(r);
      string rs = "";

      // --- kill switch / locks / errors / news ------------------------------
      if(FileIsExist("xauscalp\\KILL_SWITCH", FILE_COMMON)) Add(rs, "KILL_SWITCH");
      if(GlobalVariableCheck(m_prefix + "ddlock")) Add(rs, "DRAWDOWN_LOCK");
      if(m_consecutive_errors >= m_c.max_consecutive_errors) Add(rs, "PAUSED_AFTER_ERRORS");
      if(news_blackout) Add(rs, "NEWS_BLACKOUT");
      if(!news_calendar_ok) Add(rs, "NEWS_CALENDAR_MISSING");   // audit M7: fail-closed

      // --- market ----------------------------------------------------------
      MqlTick tk;
      bool quote_ok = SymbolInfoTick(m_sym, tk) && XsPos(tk.bid) && XsPos(tk.ask) && tk.ask > tk.bid;
      if(!quote_ok) Add(rs, "INVALID_QUOTE");
      else
      {
         // audit M4: TimeTradeServer() keeps advancing even if the feed freezes
         double age = (double)(TimeTradeServer() - tk.time);
         if(age < 0 || age > m_c.max_data_age_s) Add(rs, "STALE_DATA");
         if(tk.ask - tk.bid > m_c.max_spread) Add(rs, "SPREAD_TOO_WIDE");
         double ref = (direction == 1) ? tk.ask : tk.bid;
         if(XsPos(entry) && MathAbs(entry - ref) > 0.001 * ref) Add(rs, "ENTRY_PRICE_MISMATCH");
      }
      ENUM_SYMBOL_TRADE_MODE tm = (ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(m_sym, SYMBOL_TRADE_MODE);
      if(tm != SYMBOL_TRADE_MODE_FULL) Add(rs, "SYMBOL_NOT_FULLY_TRADABLE");

      // --- account / limits ------------------------------------------------
      double eq = AccountInfoDouble(ACCOUNT_EQUITY);
      double fm = AccountInfoDouble(ACCOUNT_MARGIN_FREE);
      datetime now = TimeTradeServer();
      double d0 = Anchor(m_prefix + "day." + Key(now), DayStart(now));
      double w0 = Anchor(m_prefix + "week." + Key(WeekStart(now)), WeekStart(now));
      double pk = GlobalVariableCheck(m_prefix + "peak") ? GlobalVariableGet(m_prefix + "peak") : EMPTY_VALUE;
      bool acct_ok = XsPos(eq) && XsValid(fm) && fm >= 0 && XsPos(d0) && XsPos(w0) && XsPos(pk);
      if(!acct_ok)
      {
         Add(rs, "INVALID_ACCOUNT");
         // which input failed (diagnostics; the code above stays the mirror of Python's reason)
         if(!XsPos(eq)) Add(rs, "ACCT_EQUITY");
         if(!(XsValid(fm) && fm >= 0)) Add(rs, "ACCT_MARGIN_FREE");
         if(!XsPos(d0)) Add(rs, "ACCT_DAY_ANCHOR");
         if(!XsPos(w0)) Add(rs, "ACCT_WEEK_ANCHOR");
         if(!XsPos(pk)) Add(rs, "ACCT_PEAK");
      }
      if(OpenPositionsOnSymbol() >= m_c.max_positions) Add(rs, "MAX_OPEN_POSITIONS");
      if(TradesToday() >= m_c.max_trades_day) Add(rs, "MAX_TRADES_PER_DAY");
      double remaining = 0;
      if(acct_ok)
      {
         pk = MathMax(pk, eq);
         if((eq / d0 - 1.0) * 100.0 <= -m_c.daily_loss_pct)  Add(rs, "DAILY_LOSS_LIMIT");
         if((eq / w0 - 1.0) * 100.0 <= -m_c.weekly_loss_pct) Add(rs, "WEEKLY_LOSS_LIMIT");
         if((1.0 - eq / pk) * 100.0 >= m_c.max_dd_pct)       Add(rs, "MAX_DRAWDOWN");
         double rd = d0 * m_c.daily_loss_pct / 100.0 - (d0 - eq);
         double rw = w0 * m_c.weekly_loss_pct / 100.0 - (w0 - eq);
         double rp = pk * m_c.max_dd_pct / 100.0 - (pk - eq);
         remaining = MathMax(0.0, MathMin(rd, MathMin(rw, rp)));
      }

      // --- stop loss vs. LIVE market (audit H1, M3) -------------------------
      double worst_entry = EMPTY_VALUE;
      if(direction != 1 && direction != -1) Add(rs, "INVALID_DIRECTION");
      else if(!XsPos(entry) || !XsPos(sl)) Add(rs, "SL_MISSING_OR_INVALID");
      else if((entry - sl) * direction <= 0) Add(rs, "SL_WRONG_SIDE");
      else if(quote_ok)
      {
         double trigger = (direction == 1) ? tk.bid : tk.ask;    // price that fires the stop
         if((trigger - sl) * direction <= 0) Add(rs, "SL_WRONG_SIDE_OF_MARKET");
         else
         {
            worst_entry = (direction == 1) ? MathMax(entry, tk.ask) : MathMin(entry, tk.bid);
            double point = SymbolInfoDouble(m_sym, SYMBOL_POINT);
            long stops_lvl  = SymbolInfoInteger(m_sym, SYMBOL_TRADE_STOPS_LEVEL);
            long freeze_lvl = SymbolInfoInteger(m_sym, SYMBOL_TRADE_FREEZE_LEVEL);
            long lvl = (stops_lvl > freeze_lvl) ? stops_lvl : freeze_lvl;
            if(lvl > 0 && (trigger - sl) * direction < lvl * point) Add(rs, "SL_INSIDE_STOPS_OR_FREEZE_LEVEL");
            if(XsPos(tp) && (tp - worst_entry) * direction <= 0) Add(rs, "TP_WRONG_SIDE");
         }
      }

      // --- sizing with the broker's calculators ----------------------------
      double vmin = SymbolInfoDouble(m_sym, SYMBOL_VOLUME_MIN);
      double vmax = SymbolInfoDouble(m_sym, SYMBOL_VOLUME_MAX);
      double vstep = SymbolInfoDouble(m_sym, SYMBOL_VOLUME_STEP);
      bool spec_ok = XsPos(vmin) && XsPos(vmax) && XsPos(vstep) && vmax >= vmin;
      if(!spec_ok) Add(rs, "INVALID_SPEC");
      if(XsPos(worst_entry) && acct_ok && spec_ok)
      {
         ENUM_ORDER_TYPE ot = (direction == 1) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
         double stop_fill = sl - direction * m_c.slippage;        // stops can slip
         double pl = 0;
         if(!OrderCalcProfit(ot, m_sym, 1.0, worst_entry, stop_fill, pl) || !XsValid(pl) || pl >= 0)
            Add(rs, "PROFIT_CALC_FAILED");
         else
         {
            r.loss_per_lot = -pl + m_c.commission_per_lot;
            r.budget = MathMin(eq * m_c.risk_pct / 100.0, remaining);
            if(!XsPos(r.budget)) Add(rs, "NO_RISK_BUDGET");
            else
            {
               double raw = r.budget / r.loss_per_lot / vstep;
               double cap = MathFloor(vmax / vstep + 1e-9);
               double steps = (!XsValid(raw) || raw > cap) ? cap : MathFloor(raw + 1e-9);
               while(steps > 0 && steps * vstep * r.loss_per_lot > r.budget * (1 + 1e-12))
                  steps -= 1;
               int vdig = (int)MathMax(0, MathCeil(-MathLog10(vstep) - 1e-9));
               double vol = NormalizeDouble(steps * vstep, vdig);
               if(vol * r.loss_per_lot > r.budget * (1 + 1e-12)) vol = NormalizeDouble(vol - vstep, vdig);
               if(vol + 1e-12 < vmin)
               {
                  Add(rs, "MIN_VOLUME_EXCEEDS_RISK");
                  r.risk_money = vmin * r.loss_per_lot;           // informative
               }
               else
               {
                  double margin = 0;
                  if(!OrderCalcMargin(ot, m_sym, vol, worst_entry, margin) || !XsPos(margin))
                     Add(rs, "MARGIN_CALC_FAILED");
                  else
                  {
                     r.margin = margin;
                     if(margin > fm * m_c.max_margin_usage_pct / 100.0) Add(rs, "INSUFFICIENT_MARGIN");
                  }
                  r.volume = vol;
                  r.risk_money = vol * r.loss_per_lot;
               }
            }
         }
      }
      else if(rs == "")
         Add(rs, "CANNOT_SIZE");
      r.reasons = rs;
      r.approved = (rs == "") && XsPos(r.volume) && XsPos(r.risk_money);
      if(!r.approved && rs == "") r.reasons = "INTERNAL_INCONSISTENCY";
      if(!r.approved) r.volume = 0;
   }
};

#endif
