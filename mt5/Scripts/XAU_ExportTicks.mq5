//+------------------------------------------------------------------+
//| XAU_ExportTicks.mq5                                              |
//| PHASE 1. Exports YOUR broker's real Bid/Ask ticks with           |
//| CopyTicksRange(COPY_TICKS_INFO) to                               |
//| Common\Files\<symbol>_ticks_<from>_<to>.csv. Read-only.          |
//|                                                                  |
//| time_msc_server = milliseconds since 1970 in SERVER time.        |
//| UTC conversion is done in Python with a verified policy          |
//| (xauscalp.data.server_time); never assumed here.                 |
//| Tick history depth depends on the server; the script reports     |
//| days with no ticks so gaps are visible.                          |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14, MetaEditor CLI (macOS/Wine), 0 err. |
//|         Compiling proves syntax only; not yet run in the Tester. |
//+------------------------------------------------------------------+
#property copyright "xauscalp"
#property version   "1.00"
#property script_show_inputs

input string   InpSymbol = "XAUUSD";               // Symbol exactly as in Market Watch
input datetime InpFrom   = D'2025.10.01 00:00';    // From (server time)
input datetime InpTo     = D'2025.11.01 00:00';    // To (server time; default stays BEFORE the holdout)

void OnStart()
{
   if(!SymbolSelect(InpSymbol, true)) { Print("symbol not found: ", InpSymbol); return; }
   datetime now = TimeCurrent();
   datetime to  = (InpTo < now) ? InpTo : now;
   string fname = InpSymbol + "_ticks_" + IntegerToString((long)InpFrom) + "_" +
                  IntegerToString((long)to) + ".csv";
   int fh = FileOpen(fname, FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
   if(fh == INVALID_HANDLE) { Print("FileOpen failed ", GetLastError()); return; }
   int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   FileWrite(fh, "#server_minus_gmt_seconds_at_export", (long)(TimeTradeServer() - TimeGMT()));
   FileWrite(fh, "#tz_policy", "UNKNOWN");
   FileWrite(fh, "#server", AccountInfoString(ACCOUNT_SERVER));
   FileWrite(fh, "#symbol", InpSymbol);
   FileWrite(fh, "#terminal_build", (long)TerminalInfoInteger(TERMINAL_BUILD));
   FileWrite(fh, "time_msc_server", "bid", "ask", "flags");

   long total = 0;
   int empty_days = 0;
   for(datetime a = InpFrom; a < to; a += 86400)          // one day per request
   {
      datetime b = (a + 86400 < to) ? a + 86400 : to;
      MqlTick ticks[];
      ResetLastError();
      int n = CopyTicksRange(InpSymbol, ticks, COPY_TICKS_INFO,
                             (ulong)a * 1000, (ulong)b * 1000 - 1);
      if(n < 0)
      {
         Print("CopyTicksRange error ", GetLastError(), " at ", TimeToString(a));
         continue;
      }
      if(n == 0) { empty_days++; continue; }
      for(int i = 0; i < n; i++)
         FileWrite(fh, (long)ticks[i].time_msc, DoubleToString(ticks[i].bid, digits),
                   DoubleToString(ticks[i].ask, digits), (long)ticks[i].flags);
      total += n;
   }
   FileClose(fh);
   Print("Exported ", total, " ticks (", empty_days, " days without ticks: weekends, ",
         "holidays or beyond server tick history) to Common\\Files\\", fname);
}
