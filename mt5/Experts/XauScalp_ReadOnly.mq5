//+------------------------------------------------------------------+
//| XauScalp_ReadOnly.mq5 - STAGE A: read-only signal + risk monitor |
//|                                                                  |
//| What it does: detects the gold symbol, refuses non-demo accounts,|
//| reads Bid/Ask, computes London/COMEX sessions (DST-aware), runs  |
//| the ORB rules on every closed M1 bar, asks the risk guard whether|
//| a SIGNAL would be allowed and logs the decision with its reasons.|
//|                                                                  |
//| What it can NOT do: send, modify or close orders. The file and   |
//| its includes contain no trading calls (enforced by               |
//| tests/test_mql5_static.py). Execution is Stage C, not yet      |
//| written, and will be disabled by default.                        |
//|                                                                  |
//| Logs: Common\Files\xauscalp\decisions_<tag>.csv, state_<tag>.json|
//| Kill switch file (honoured by the risk guard):                   |
//|       Common\Files\xauscalp\KILL_SWITCH                          |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14, MetaEditor CLI (macOS/Wine), 0 err. |
//|         Tester run 1-2 (2025-09..10): NOT equivalent to Python (ATR |
//|         window bug, fixed + recompiled 0/0); parity3 pending.      |
//+------------------------------------------------------------------+
#property copyright "xauscalp"
#property version   "1.00"
#property description "READ-ONLY. Logs ORB signals and risk decisions. Never trades."

#include <XauScalp/TimeUtil.mqh>
#include <XauScalp/OrbSignal.mqh>
#include <XauScalp/RiskGuard.mqh>
#include <XauScalp/Logger.mqh>

//--- symbol & time
input string         InpSymbol        = "";                 // Symbol (empty = auto-detect gold)
input ENUM_TZ_POLICY InpTzPolicy      = TZ_LIVE_CLOCK;      // Server timezone policy (tester: must declare)
input int            InpTzBaseMinutes = 120;                // Base offset for FIXED / BASE+DST policies
input string         InpLogTag        = "ro";               // Log file tag
input datetime       InpTesterStopUtc = D'2025.11.01 00:00'; // Tester only: stop at the first bar opening at/after this UTC time (research holdout lockbox; 0 = off, only if YOU unlocked the holdout)
//--- ORB (mirror of config/default.yaml strategy.orb)
input string         InpLondonOpen    = "08:00";            // London open (London local time)
input string         InpComexOpen     = "08:20";            // COMEX open (New York local time)
input int            InpOrMinutes     = 15;
input double         InpSlAtr         = 1.5;
input double         InpTpR           = 1.5;
input int            InpEntryWindow   = 60;
input int            InpMaxHoldMin    = 90;
input double         InpBufferAtr     = 0.10;
input double         InpMaxCostFrac   = 0.20;
input double         InpExtraSpread   = 0.0;                // 0 with broker data
input double         InpCostSlippage  = 0.05;               // ORB cost filter slippage (= costs.slippage_usd)
//--- risk (mirror of config/default.yaml risk; hard ceilings enforced)
input double         InpRiskPct       = 0.5;
input double         InpDailyLossPct  = 2.0;
input double         InpWeeklyLossPct = 5.0;
input double         InpMaxDdPct      = 8.0;
input int            InpMaxTradesDay  = 3;
input double         InpMaxSpread     = 0.60;               // price units (USD/oz)
input double         InpMaxDataAgeS   = 10;
input int            InpMaxConsecErr  = 3;
input double         InpSlippage      = 0.10;               // risk sizing slippage (= risk.expected_slippage_usd)
input double         InpCommissionLot = 0.0;                // account currency, round turn
input double         InpMaxMarginPct  = 30.0;
input long           InpMagic         = 2026111201;
input string         InpNewsFile      = "xauscalp\\events.csv"; // Common\Files; optional
input int            InpNewsBeforeMin = 30;
input int            InpNewsAfterMin  = 30;

string       g_sym = "";
string       g_mode = "";
CServerClock g_clock;
CRiskGuard   g_risk;
CDecisionLog g_log;
COrbSession  g_sess[2];
OrbParams    g_p;
datetime     g_last_bar = 0;
datetime     g_news[];
string       g_last_status = "", g_last_reasons = "", g_last_error = "";
int          g_signals = 0, g_approved = 0;

//+------------------------------------------------------------------+
bool ParseHHMM(const string s, int &h, int &m)
{
   string parts[];
   if(StringSplit(s, ':', parts) != 2) return false;
   h = (int)StringToInteger(parts[0]);
   m = (int)StringToInteger(parts[1]);
   return h >= 0 && h < 24 && m >= 0 && m < 60;
}

bool IsGoldSymbol(const string s)
{
   return StringFind(s, "XAUUSD") == 0 || s == "GOLD" || StringFind(s, "GOLD.") == 0;
}

string DetectSymbol()
{
   if(InpSymbol != "") return SymbolSelect(InpSymbol, true) ? InpSymbol : "";
   if(IsGoldSymbol(_Symbol)) return _Symbol;
   string found = "";
   int count = 0;
   for(int i = 0; i < SymbolsTotal(false); i++)
   {
      string s = SymbolName(i, false);
      if(IsGoldSymbol(s)) { found = s; count++; }
   }
   if(count == 1 && SymbolSelect(found, true)) return found;
   Print("Symbol auto-detection found ", count, " candidates: set InpSymbol explicitly.");
   return "";
}

void LoadNews()
{
   ArrayResize(g_news, 0);
   if(!FileIsExist(InpNewsFile, FILE_COMMON)) return;
   int h = FileOpen(InpNewsFile, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE) return;
   while(!FileIsEnding(h))
   {
      string line = FileReadString(h);
      if(StringLen(line) < 10 || StringGetCharacter(line, 0) == '#' ||
         StringFind(line, "utc_time") == 0) continue;
      string f[];
      if(StringSplit(line, ',', f) < 3 || StringFind(f[2], "high") < 0) continue;
      string ts = f[0];
      StringReplace(ts, "T", " "); StringReplace(ts, "Z", ""); StringReplace(ts, "-", ".");
      datetime t = StringToTime(ts);                 // UTC
      if(t > 0) { int n = ArraySize(g_news); ArrayResize(g_news, n + 1); g_news[n] = t; }
   }
   FileClose(h);
}

// Calendar is "ok" only if it has at least one high-impact event at or after now (UTC):
// a missing or expired calendar means the EA cannot know about news -> fail-closed.
bool NewsCalendarOk(const datetime utc)
{
   for(int i = 0; i < ArraySize(g_news); i++)
      if(g_news[i] >= utc) return true;
   return false;
}

datetime NowUtc()
{
   return g_clock.Usable() ? g_clock.ToUtc(TimeTradeServer()) : TimeGMT();
}

bool InNewsBlackout(const datetime utc)
{
   for(int i = 0; i < ArraySize(g_news); i++)
      if(utc >= g_news[i] - InpNewsBeforeMin * 60 && utc <= g_news[i] + InpNewsAfterMin * 60)
         return true;
   return false;
}

//+------------------------------------------------------------------+
int OnInit()
{
   bool tester = (bool)MQLInfoInteger(MQL_TESTER);
   ENUM_ACCOUNT_TRADE_MODE tm = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   if(!tester && tm != ACCOUNT_TRADE_MODE_DEMO)
   {
      Alert("XauScalp_ReadOnly: account is not DEMO (", EnumToString(tm), "). Refusing to run.");
      return INIT_FAILED;
   }
   g_mode = tester ? "TESTER" : "DEMO_READONLY";

   g_sym = DetectSymbol();
   if(g_sym == "") return INIT_FAILED;

   int lh, lm, nh, nm;
   if(!ParseHHMM(InpLondonOpen, lh, lm) || !ParseHHMM(InpComexOpen, nh, nm))
      return INIT_PARAMETERS_INCORRECT;
   if(InpOrMinutes <= 0 || InpEntryWindow <= 0 || InpMaxHoldMin <= 0 || InpSlAtr <= 0 ||
      InpTpR <= 0 || InpBufferAtr < 0 || InpMaxCostFrac <= 0 || InpExtraSpread < 0 ||
      InpCostSlippage < 0)
      return INIT_PARAMETERS_INCORRECT;

   g_clock.Init(InpTzPolicy, InpTzBaseMinutes);
   if(!g_clock.Usable())
      Print("WARNING: timezone policy ", g_clock.Describe(),
            " is not usable here; sessions will NOT be evaluated. In the Strategy Tester ",
            "declare FIXED/BASE+DST after verifying it in Python (server_time.py).");

   g_p.or_minutes = InpOrMinutes; g_p.sl_atr = InpSlAtr; g_p.tp_r = InpTpR;
   g_p.entry_window_min = InpEntryWindow; g_p.max_hold_min = InpMaxHoldMin;
   g_p.buffer_atr = InpBufferAtr; g_p.max_cost_frac = InpMaxCostFrac;
   // ORB cost filter uses the BACKTEST slippage (Python: costs.slippage_usd); the risk guard
   // sizes with the larger risk.expected_slippage_usd. Mixing them broke parity (2026-11-14).
   g_p.max_spread = InpMaxSpread; g_p.slippage = InpCostSlippage; g_p.extra_spread = InpExtraSpread;
   g_sess[0].Init("london", 0, lh, lm);
   g_sess[1].Init("newyork", 1, nh, nm);

   XsRiskConfig rc;
   rc.risk_pct = InpRiskPct; rc.daily_loss_pct = InpDailyLossPct;
   rc.weekly_loss_pct = InpWeeklyLossPct; rc.max_dd_pct = InpMaxDdPct;
   rc.max_positions = 1; rc.max_trades_day = InpMaxTradesDay;
   rc.max_consecutive_errors = InpMaxConsecErr; rc.max_spread = InpMaxSpread;
   rc.max_data_age_s = InpMaxDataAgeS; rc.slippage = InpSlippage;
   rc.commission_per_lot = InpCommissionLot; rc.max_margin_usage_pct = InpMaxMarginPct;
   string err;
   if(!g_risk.Init(g_sym, InpMagic, rc, err))
   {
      Alert("Risk config rejected (", err, "): exceeds a hard ceiling or is invalid.");
      return INIT_PARAMETERS_INCORRECT;
   }
   g_risk.UpdateAnchors();
   if(!g_log.Init(InpLogTag)) { Print("cannot open log, error ", GetLastError()); return INIT_FAILED; }
   LoadNews();
   EventSetTimer(5);
   Print("XauScalp_ReadOnly started on ", g_sym, " mode=", g_mode, " tz=", g_clock.Describe(),
         " news_events=", ArraySize(g_news), ". READ-ONLY: no orders will be sent.");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   Comment("");
}

//+------------------------------------------------------------------+
void ProcessClosedBar()
{
   MqlRates r[];
   ResetLastError();
   if(CopyRates(g_sym, PERIOD_M1, 0, 2, r) != 2)   // r[0] = closed bar, r[1] = new bar
   {
      g_risk.ErrorOccurred();
      g_last_error = "CopyRates M1 failed " + IntegerToString(GetLastError());
      return;
   }
   g_risk.ErrorCleared();
   if(!g_clock.Usable()) { g_last_status = "TZ_POLICY_UNUSABLE"; return; }

   for(int s = 0; s < 2; s++)
   {
      OrbRecord rec;
      if(!g_sess[s].OnClosedBar(g_sym, g_clock, g_p, r[0], r[1].time, rec)) continue;
      XsRiskResult k;
      XsResetResult(k);
      bool evaluated = false;
      if(rec.status == "SIGNAL")
      {
         g_signals++;
         g_risk.Evaluate(rec.direction, rec.entry, rec.sl, rec.tp,
                         InNewsBlackout(rec.bar_utc + 60), NewsCalendarOk(rec.bar_utc), k);
         evaluated = true;
         if(k.approved) g_approved++;
         g_last_reasons = k.approved ? "APPROVED (would trade; read-only)" : k.reasons;
      }
      g_last_status = rec.session + " " + rec.day + " " + rec.status;
      g_log.Write(g_mode, g_clock.Describe(), rec, k, evaluated);
   }
}

void OnTick()
{
   datetime t0 = iTime(g_sym, PERIOD_M1, 0);
   if(t0 == 0 || t0 == g_last_bar) return;
   bool first = (g_last_bar == 0);
   g_last_bar = t0;
   if(g_mode == "TESTER" && InpTesterStopUtc > 0 && g_clock.Usable())
   {
      datetime u = g_clock.ToUtc(t0);
      if(u != 0 && u >= InpTesterStopUtc)
      {
         Print("XauScalp_ReadOnly: bar ", XsTime(t0), " (UTC ", XsTime(u), ") reaches InpTesterStopUtc ",
               XsTime(InpTesterStopUtc), " -> stopping the tester (holdout lockbox).");
         TesterStop();
         return;
      }
   }
   if(!first) ProcessClosedBar();
}

void OnTimer()
{
   g_risk.UpdateAnchors();
   MqlTick tk;
   bool ok = SymbolInfoTick(g_sym, tk);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY), bal = AccountInfoDouble(ACCOUNT_BALANCE);
   string json = StringFormat(
      "{\"updated_server\":\"%s\",\"mode\":\"%s\",\"read_only\":true,\"symbol\":\"%s\","
      "\"connected\":%s,\"tz_policy\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,"
      "\"bid\":%s,\"ask\":%s,\"spread\":%s,\"signals\":%d,\"approved\":%d,"
      "\"last_status\":\"%s\",\"last_reasons\":\"%s\",\"last_error\":\"%s\","
      "\"consecutive_errors\":%d,\"kill_switch\":%s,\"news_events\":%d,"
      "\"news_calendar_ok\":%s}",
      XsTime(TimeTradeServer()), g_mode, g_sym,
      TerminalInfoInteger(TERMINAL_CONNECTED) ? "true" : "false", g_clock.Describe(), bal, eq,
      ok ? XsDbl(tk.bid) : "null", ok ? XsDbl(tk.ask) : "null", ok ? XsDbl(tk.ask - tk.bid) : "null",
      g_signals, g_approved, g_last_status, g_last_reasons, g_last_error,
      g_risk.ConsecutiveErrors(),
      FileIsExist("xauscalp\\KILL_SWITCH", FILE_COMMON) ? "true" : "false", ArraySize(g_news),
      NewsCalendarOk(NowUtc()) ? "true" : "false");
   g_log.WriteState(json);
   Comment("XauScalp READ-ONLY  (no orders are ever sent)\n",
           "Symbol: ", g_sym, "   Mode: ", g_mode, "\n",
           "TZ: ", g_clock.Describe(), "\n",
           "Spread: ", ok ? XsDbl(tk.ask - tk.bid, 2) : "n/a", "   Equity: ", DoubleToString(eq, 2), "\n",
           "Signals: ", g_signals, "   Risk-approved: ", g_approved,
           "   News calendar: ", NewsCalendarOk(NowUtc()) ? "ok" : "MISSING (signals rejected)", "\n",
           "Last: ", g_last_status, "\n",
           "Reasons: ", g_last_reasons, "\n",
           "Error: ", g_last_error);
}
//+------------------------------------------------------------------+
