//+------------------------------------------------------------------+
//| XAU_SymbolSpecs.mq5 - READ-ONLY dump of contract specifications   |
//| for several symbols at once (one CSV), on whatever server the     |
//| terminal is connected to (MetaQuotes-Demo, a prop-firm trial...). |
//|                                                                  |
//| Writes Common\Files\xauscalp\symbol_specs_<tag>.csv. It does NOT  |
//| send, modify or check any order (only OrderCalcMargin, a pure     |
//| calculation). It does NOT write the account login.               |
//| Commission is NOT exposed by the MQL5 API: read it from the firm's|
//| contract page / first statement and add it by hand (see docs).    |
//|                                                                  |
//| STATUS: COMPILED 2026-11-15, 0 errors, 0 warnings. Not yet run.   |
//+------------------------------------------------------------------+
#property copyright "xauscalp"
#property version   "1.00"
#property script_show_inputs
#property description "READ-ONLY. Dumps symbol specs (contract size, lots, tick value, swaps...) to CSV."

input string InpSymbols = "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,XAUUSD,XAGUSD"; // Exact names as in Market Watch
input string InpTag     = "specs";                                           // File tag (e.g. mqdemo, ftmo)

string F(const double v) { return MathIsValidNumber(v) ? DoubleToString(v, 8) : ""; }

void OnStart()
{
   string list[];
   int n = StringSplit(InpSymbols, ',', list);
   if(n <= 0) { Print("no symbols"); return; }
   FolderCreate("xauscalp", FILE_COMMON);
   string fname = "xauscalp\\symbol_specs_" + InpTag + ".csv";
   int h = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(h == INVALID_HANDLE) { Print("cannot open ", fname, " error ", GetLastError()); return; }
   FileWrite(h, "#specs_version", "1.0");
   FileWrite(h, "#company", AccountInfoString(ACCOUNT_COMPANY));
   FileWrite(h, "#server", AccountInfoString(ACCOUNT_SERVER));
   FileWrite(h, "#account_currency", AccountInfoString(ACCOUNT_CURRENCY));
   FileWrite(h, "#leverage", (string)AccountInfoInteger(ACCOUNT_LEVERAGE));
   FileWrite(h, "#margin_mode", EnumToString((ENUM_ACCOUNT_MARGIN_MODE)AccountInfoInteger(ACCOUNT_MARGIN_MODE)));
   FileWrite(h, "#account_trade_mode", EnumToString((ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE)));
   FileWrite(h, "#time_server", TimeToString(TimeTradeServer(), TIME_DATE | TIME_SECONDS));
   FileWrite(h, "symbol", "found", "digits", "point", "contract_size", "volume_min", "volume_step",
             "volume_max", "volume_limit", "tick_size", "tick_value", "tick_value_profit", "tick_value_loss",
             "currency_base", "currency_profit", "currency_margin", "bid", "ask", "spread_points",
             "stops_level", "freeze_level", "swap_long", "swap_short", "swap_mode", "margin_1lot",
             "trade_mode", "calc_mode");
   for(int i = 0; i < n; i++)
   {
      string s = list[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(s == "") continue;
      if(!SymbolSelect(s, true))
      {
         FileWrite(h, s, 0);
         Print("symbol not found: ", s);
         continue;
      }
      Sleep(500);                                           // let the first quote arrive
      MqlTick tk;
      bool ok = SymbolInfoTick(s, tk);
      double margin = 0;
      if(!(ok && OrderCalcMargin(ORDER_TYPE_BUY, s, 1.0, tk.ask, margin))) margin = EMPTY_VALUE;
      FileWrite(h, s, 1, (int)SymbolInfoInteger(s, SYMBOL_DIGITS), F(SymbolInfoDouble(s, SYMBOL_POINT)),
                F(SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE)), F(SymbolInfoDouble(s, SYMBOL_VOLUME_MIN)),
                F(SymbolInfoDouble(s, SYMBOL_VOLUME_STEP)), F(SymbolInfoDouble(s, SYMBOL_VOLUME_MAX)),
                F(SymbolInfoDouble(s, SYMBOL_VOLUME_LIMIT)), F(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE)),
                F(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE)), F(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE_PROFIT)),
                F(SymbolInfoDouble(s, SYMBOL_TRADE_TICK_VALUE_LOSS)), SymbolInfoString(s, SYMBOL_CURRENCY_BASE),
                SymbolInfoString(s, SYMBOL_CURRENCY_PROFIT), SymbolInfoString(s, SYMBOL_CURRENCY_MARGIN),
                ok ? F(tk.bid) : "", ok ? F(tk.ask) : "", (int)SymbolInfoInteger(s, SYMBOL_SPREAD),
                (int)SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL), (int)SymbolInfoInteger(s, SYMBOL_TRADE_FREEZE_LEVEL),
                F(SymbolInfoDouble(s, SYMBOL_SWAP_LONG)), F(SymbolInfoDouble(s, SYMBOL_SWAP_SHORT)),
                EnumToString((ENUM_SYMBOL_SWAP_MODE)SymbolInfoInteger(s, SYMBOL_SWAP_MODE)), F(margin),
                EnumToString((ENUM_SYMBOL_TRADE_MODE)SymbolInfoInteger(s, SYMBOL_TRADE_MODE)),
                EnumToString((ENUM_SYMBOL_CALC_MODE)SymbolInfoInteger(s, SYMBOL_TRADE_CALC_MODE)));
   }
   FileClose(h);
   Print("XAU_SymbolSpecs: wrote Common\\Files\\", fname, " (", n, " symbols). Read-only; no orders.");
}
