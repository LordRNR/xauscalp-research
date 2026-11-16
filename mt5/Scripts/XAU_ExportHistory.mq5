//+------------------------------------------------------------------+
//| XAU_ExportHistory.mq5                                            |
//| PHASE 1. Exports YOUR broker's M1 bars (incl. spread field) to   |
//| Common\Files\<symbol>_M1_<from>_<to>.csv for Python research.    |
//| Read-only: never trades.                                         |
//|                                                                  |
//| Times are SERVER time. MQL5 exposes only the CURRENT server-GMT  |
//| offset (TimeTradeServer()-TimeGMT(), GMT from the local clock);  |
//| there is no API for historical server offsets. The header keeps  |
//| that value as metadata ONLY; Python converts to UTC with an      |
//| explicit, verified policy (xauscalp.data.server_time).           |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14, MetaEditor CLI (macOS/Wine), 0 err. |
//|         Compiling proves syntax only; not yet run in the Tester. |
//+------------------------------------------------------------------+
#property copyright "xauscalp"
#property version   "1.00"
#property script_show_inputs

input string   InpSymbol = "XAUUSD";               // Symbol exactly as in Market Watch
input datetime InpFrom   = D'2021.01.01 00:00';    // From (server time; 2021 overlaps Dukascopy)
input datetime InpTo     = D'2030.01.01 00:00';    // To (server time; clipped to now)

void OnStart()
{
   if(!SymbolSelect(InpSymbol, true)) { Print("symbol not found: ", InpSymbol); return; }
   datetime now = TimeCurrent();
   datetime to = (InpTo < now) ? InpTo : now;
   string fname = InpSymbol + "_M1_" + TimeToString(InpFrom, TIME_DATE) + "_" +
                  TimeToString(to, TIME_DATE) + ".csv";
   StringReplace(fname, ".", "");      // dates contain dots
   StringReplace(fname, "csv", ".csv");
   int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE) { Print("FileOpen failed ", GetLastError()); return; }

   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   FileWrite(fh, "#server_minus_gmt_seconds_at_export", (long)(TimeTradeServer() - TimeGMT()));
   FileWrite(fh, "#tz_policy", "UNKNOWN");   // never assume; verify in Python
   FileWrite(fh, "#export_utc_from_local_clock", TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS));
   FileWrite(fh, "#server", AccountInfoString(ACCOUNT_SERVER));
   FileWrite(fh, "#symbol", InpSymbol);
   FileWrite(fh, "#terminal_build", (long)TerminalInfoInteger(TERMINAL_BUILD));
   FileWrite(fh, "#point", DoubleToString(SymbolInfoDouble(InpSymbol, SYMBOL_POINT), 8));
   FileWrite(fh, "time_server", "open", "high", "low", "close", "tick_volume", "spread_points");

   long total = 0;
   // chunk by 30 days: CopyRates is limited by the terminal's max-bars setting
   for(datetime a = InpFrom; a < to; a += 30 * 86400)
   {
      datetime b = (a + 30 * 86400 - 60 < to) ? a + 30 * 86400 - 60 : to;
      MqlRates r[];
      int n = CopyRates(InpSymbol, PERIOD_M1, a, b, r);
      if(n < 0) { Print("CopyRates error ", GetLastError(), " at ", TimeToString(a)); continue; }
      for(int i = 0; i < n; i++)
         FileWrite(fh, TimeToString(r[i].time, TIME_DATE | TIME_MINUTES),
                   DoubleToString(r[i].open, digits), DoubleToString(r[i].high, digits),
                   DoubleToString(r[i].low, digits), DoubleToString(r[i].close, digits),
                   (long)r[i].tick_volume, r[i].spread);
      total += n;
   }
   FileClose(fh);
   Print("Exported ", total, " M1 bars to Common\\Files\\", fname,
         ". If the count is low, raise Tools>Options>Charts>Max bars and scroll the M1 chart back.");
}
