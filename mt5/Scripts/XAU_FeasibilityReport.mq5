//+------------------------------------------------------------------+
//| XAU_FeasibilityReport.mq5                                        |
//| PHASE 0. Read-only feasibility audit of the gold symbol on YOUR  |
//| broker and account. It NEVER sends an order: OrderCheck only     |
//| validates a hypothetical request on the server side.             |
//|                                                                  |
//| Output: MQL5\Files (Common folder) xau_feasibility.csv + Experts |
//| log. Feed the CSV to: python -m xauscalp.mt5_report <path>       |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14, MetaEditor CLI (macOS/Wine), 0 err. |
//|         Compiling proves syntax only; not yet run in the Tester. |
//| Compile it in MetaEditor (F7) and report any error.              |
//+------------------------------------------------------------------+
#property copyright "xauscalp"
#property version   "1.00"
#property script_show_inputs

input string InpSymbol       = "XAUUSD";  // Symbol name exactly as in Market Watch (suffixes!)
input double InpRiskPct      = 0.5;       // Risk per trade (% of equity) used for the table
input int    InpSpreadDays   = 30;        // Days of M1 history used for spread statistics

int g_file = INVALID_HANDLE;

//--- write one key/value line to file and log ------------------------
void Out(const string key, const string value)
{
   string v = value;
   StringReplace(v, ",", ";");            // keep CSV well-formed
   if(g_file != INVALID_HANDLE)
      FileWrite(g_file, key, v);
   Print(key, " = ", v);
}
void OutD(const string key, const double value, const int digits = 8) { Out(key, DoubleToString(value, digits)); }
void OutL(const string key, const long value) { Out(key, IntegerToString(value)); }

//--- pick a filling mode the symbol supports ----------------------------
ENUM_ORDER_TYPE_FILLING PickFilling(const string sym)
{
   long modes = SymbolInfoInteger(sym, SYMBOL_FILLING_MODE);
   if((modes & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
   if((modes & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
   return ORDER_FILLING_RETURN;
}

//--- percentile of a sorted array ---------------------------------------
double Pct(const double &a[], const double q)
{
   int n = ArraySize(a);
   if(n == 0) return EMPTY_VALUE;
   int k = (int)MathFloor(q * (n - 1));
   return a[k];
}

void OnStart()
{
   string sym = InpSymbol;
   if(!SymbolSelect(sym, true))
   {
      Print("ERROR: symbol ", sym, " not found. Check the exact name in Market Watch.");
      return;
   }
   g_file = FileOpen("xau_feasibility.csv", FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(g_file == INVALID_HANDLE)
      Print("WARNING: cannot open output file, error ", GetLastError(), ". Logging only.");

   Out("report_version", "0.10");
   Out("generated_server_time", TimeToString(TimeTradeServer(), TIME_DATE | TIME_SECONDS));
   Out("generated_gmt", TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS));
   OutL("server_minus_gmt_seconds", (long)(TimeTradeServer() - TimeGMT()));

   //=== ACCOUNT (no name / no personal data is written) ====================
   ENUM_ACCOUNT_TRADE_MODE tmode = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   Out("account_trade_mode", EnumToString(tmode));
   Out("account_is_demo", tmode == ACCOUNT_TRADE_MODE_DEMO ? "true" : "false");
   Out("account_company", AccountInfoString(ACCOUNT_COMPANY));
   Out("account_server", AccountInfoString(ACCOUNT_SERVER));
   Out("account_currency", AccountInfoString(ACCOUNT_CURRENCY));
   OutL("account_leverage", AccountInfoInteger(ACCOUNT_LEVERAGE));
   Out("account_margin_mode",
       EnumToString((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)));
   OutD("account_balance", AccountInfoDouble(ACCOUNT_BALANCE), 2);
   OutD("account_equity", AccountInfoDouble(ACCOUNT_EQUITY), 2);
   OutD("account_margin_free", AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2);
   OutD("account_margin_so_call", AccountInfoDouble(ACCOUNT_MARGIN_SO_CALL), 2);
   OutD("account_margin_so_so", AccountInfoDouble(ACCOUNT_MARGIN_SO_SO), 2);
   Out("account_trade_allowed", AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) ? "true" : "false");
   Out("terminal_trade_allowed", TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) ? "true" : "false");

   //=== SYMBOL SPECIFICATION ================================================
   Out("symbol", sym);
   Out("symbol_description", SymbolInfoString(sym, SYMBOL_DESCRIPTION));
   Out("symbol_path", SymbolInfoString(sym, SYMBOL_PATH));
   Out("symbol_calc_mode",
       EnumToString((ENUM_SYMBOL_CALC_MODE)SymbolInfoInteger(sym, SYMBOL_TRADE_CALC_MODE)));
   Out("symbol_trade_mode",
       EnumToString((ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(sym, SYMBOL_TRADE_MODE)));
   Out("symbol_exec_mode",
       EnumToString((ENUM_SYMBOL_TRADE_EXECUTION)SymbolInfoInteger(sym, SYMBOL_TRADE_EXEMODE)));
   OutL("symbol_filling_flags", SymbolInfoInteger(sym, SYMBOL_FILLING_MODE));
   Out("currency_base", SymbolInfoString(sym, SYMBOL_CURRENCY_BASE));
   Out("currency_profit", SymbolInfoString(sym, SYMBOL_CURRENCY_PROFIT));
   Out("currency_margin", SymbolInfoString(sym, SYMBOL_CURRENCY_MARGIN));
   int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   OutL("digits", digits);
   double point = SymbolInfoDouble(sym, SYMBOL_POINT);
   OutD("point", point);
   OutD("contract_size", SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE));
   double vmin  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double vmax  = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   double vstep = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   OutD("volume_min", vmin); OutD("volume_max", vmax); OutD("volume_step", vstep);
   OutD("tick_size", SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_SIZE));
   OutD("tick_value", SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE));
   OutD("tick_value_profit", SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_PROFIT));
   OutD("tick_value_loss", SymbolInfoDouble(sym, SYMBOL_TRADE_TICK_VALUE_LOSS));
   OutL("stops_level_points", SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL));
   OutL("freeze_level_points", SymbolInfoInteger(sym, SYMBOL_TRADE_FREEZE_LEVEL));
   Out("spread_float", SymbolInfoInteger(sym, SYMBOL_SPREAD_FLOAT) ? "true" : "false");
   OutL("spread_now_points", SymbolInfoInteger(sym, SYMBOL_SPREAD));
   Out("swap_mode", EnumToString((ENUM_SYMBOL_SWAP_MODE)SymbolInfoInteger(sym, SYMBOL_SWAP_MODE)));
   OutD("swap_long", SymbolInfoDouble(sym, SYMBOL_SWAP_LONG));
   OutD("swap_short", SymbolInfoDouble(sym, SYMBOL_SWAP_SHORT));
   Out("swap_3days", EnumToString((ENUM_DAY_OF_WEEK)SymbolInfoInteger(sym, SYMBOL_SWAP_ROLLOVER3DAYS)));
   OutD("margin_initial", SymbolInfoDouble(sym, SYMBOL_MARGIN_INITIAL));
   OutD("margin_maintenance", SymbolInfoDouble(sym, SYMBOL_MARGIN_MAINTENANCE));
   double mr_init = 0, mr_maint = 0;
   if(SymbolInfoMarginRate(sym, ORDER_TYPE_BUY, mr_init, mr_maint))
   {
      OutD("margin_rate_buy_initial", mr_init);
      OutD("margin_rate_buy_maintenance", mr_maint);
   }
   Out("commission_note", "Not exposed by SymbolInfo. Check broker spec or DEAL_COMMISSION of a demo trade.");

   //--- trading sessions (server time) -----------------------------------
   for(int d = 0; d < 7; d++)
   {
      datetime from = 0, to = 0;
      string s = "";
      for(int k = 0; k < 4 && SymbolInfoSessionTrade(sym, (ENUM_DAY_OF_WEEK)d, k, from, to); k++)
         s += TimeToString(from, TIME_MINUTES) + "-" + TimeToString(to, TIME_MINUTES) + " ";
      Out("session_" + EnumToString((ENUM_DAY_OF_WEEK)d), s == "" ? "closed" : s);
   }

   //=== MONEY: margin and P/L via the broker's own calculators =============
   MqlTick tick;
   if(!SymbolInfoTick(sym, tick) || tick.ask <= 0)
   {
      Print("ERROR: no current tick for ", sym, " (market closed?). Run again while it is open.");
      if(g_file != INVALID_HANDLE) FileClose(g_file);
      return;
   }
   OutD("bid", tick.bid, digits); OutD("ask", tick.ask, digits);
   OutD("spread_now_price", tick.ask - tick.bid, digits);

   double vols[4];
   vols[0] = vmin; vols[1] = 2 * vmin; vols[2] = 0.10; vols[3] = 1.00;
   for(int i = 0; i < 4; i++)
   {
      double margin = 0, pl = 0;
      string tag = DoubleToString(vols[i], 3);
      if(OrderCalcMargin(ORDER_TYPE_BUY, sym, vols[i], tick.ask, margin))
         OutD("margin_for_" + tag + "_lots", margin, 2);
      else
         Out("margin_for_" + tag + "_lots", "ERR " + IntegerToString(GetLastError()));
      // P/L in ACCOUNT currency for a 1.00 move in price (USD per oz on most brokers)
      if(OrderCalcProfit(ORDER_TYPE_BUY, sym, vols[i], tick.ask, tick.ask + 1.0, pl))
         OutD("profit_per_1usd_move_" + tag + "_lots", pl, 4);
   }

   //--- equity needed so that MIN volume risks <= InpRiskPct --------------
   double sl_dist[7] = {0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0};
   for(int i = 0; i < 7; i++)
   {
      double loss = 0;
      if(OrderCalcProfit(ORDER_TYPE_BUY, sym, vmin, tick.ask, tick.ask - sl_dist[i], loss))
      {
         double need = MathAbs(loss) / (InpRiskPct / 100.0);
         string tag = DoubleToString(sl_dist[i], 1);
         OutD("minvol_loss_at_sl_" + tag, MathAbs(loss), 2);
         OutD("equity_needed_sl_" + tag + "_risk_" + DoubleToString(InpRiskPct, 2) + "pct", need, 2);
      }
   }

   //--- server-side validation of a hypothetical MIN-volume BUY (NOT sent) -
   MqlTradeRequest req;
   MqlTradeCheckResult chk;
   ZeroMemory(req); ZeroMemory(chk);
   req.action       = TRADE_ACTION_DEAL;
   req.symbol       = sym;
   req.volume       = vmin;
   req.type         = ORDER_TYPE_BUY;
   req.price        = tick.ask;
   req.sl           = NormalizeDouble(tick.ask - 3.0, digits);
   req.tp           = NormalizeDouble(tick.ask + 3.0, digits);
   req.deviation    = 20;
   req.type_filling = PickFilling(sym);
   req.magic        = 0;
   bool ok = OrderCheck(req, chk);
   Out("ordercheck_ok", ok ? "true" : "false");
   OutL("ordercheck_retcode", chk.retcode);
   Out("ordercheck_comment", chk.comment);
   OutD("ordercheck_margin", chk.margin, 2);
   OutD("ordercheck_margin_free_after", chk.margin_free, 2);

   //=== SPREAD STATISTICS from M1 history (spread field, in points) ========
   MqlRates rates[];
   datetime t_to = TimeCurrent();
   datetime t_from = t_to - InpSpreadDays * 86400;
   int n = CopyRates(sym, PERIOD_M1, t_from, t_to, rates);
   OutL("spread_sample_m1_bars", n);
   if(n > 100)
   {
      double sp[];
      ArrayResize(sp, n);
      double by_hour_sum[24]; int by_hour_cnt[24];
      ArrayInitialize(by_hour_sum, 0); ArrayInitialize(by_hour_cnt, 0);
      for(int i = 0; i < n; i++)
      {
         sp[i] = rates[i].spread * point;              // price units
         MqlDateTime dt; TimeToStruct(rates[i].time, dt);  // SERVER time
         by_hour_sum[dt.hour] += sp[i]; by_hour_cnt[dt.hour]++;
      }
      ArraySort(sp);
      OutD("spread_m1_p50_price", Pct(sp, 0.50), digits);
      OutD("spread_m1_p90_price", Pct(sp, 0.90), digits);
      OutD("spread_m1_p99_price", Pct(sp, 0.99), digits);
      for(int h = 0; h < 24; h++)
         if(by_hour_cnt[h] > 0)
            OutD("spread_mean_server_hour_" + IntegerToString(h, 2, '0'), by_hour_sum[h] / by_hour_cnt[h], digits);
      Out("spread_note", "MqlRates.spread is typically the MIN spread of the bar on many servers: treat as optimistic.");
   }

   if(g_file != INVALID_HANDLE)
   {
      FileClose(g_file);
      Print("Report written to Common\\Files\\xau_feasibility.csv (", TerminalInfoString(TERMINAL_COMMONDATA_PATH), ")");
   }
}
//+------------------------------------------------------------------+
