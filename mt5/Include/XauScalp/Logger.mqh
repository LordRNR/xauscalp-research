//+------------------------------------------------------------------+
//| Logger.mqh - structured logs in Common\Files\xauscalp\           |
//|  decisions_<tag>.csv : one row per (day, session) decision       |
//|  state_<tag>.json    : current status for the dashboard          |
//| No personal data (no login, no name) is written.                 |
//|                                                                  |
//| STATUS: COMPILED 2026-11-14 via XauScalp_ReadOnly.mq5, 0 errors. |
//|         Compiling proves syntax only; not yet run in the Tester. |
//+------------------------------------------------------------------+
#ifndef XAUSCALP_LOGGER_MQH
#define XAUSCALP_LOGGER_MQH

#include "OrbSignal.mqh"
#include "RiskGuard.mqh"

string XsDbl(const double v, const int digits = 5)
{
   return (v == EMPTY_VALUE || !MathIsValidNumber(v)) ? "" : DoubleToString(v, digits);
}
string XsTime(const datetime t) { return t == 0 ? "" : TimeToString(t, TIME_DATE | TIME_SECONDS); }

class CDecisionLog
{
private:
   string m_csv, m_json;

public:
   bool Init(const string tag)
   {
      FolderCreate("xauscalp", FILE_COMMON);
      m_csv = "xauscalp\\decisions_" + tag + ".csv";
      m_json = "xauscalp\\state_" + tag + ".json";
      int h = FileOpen(m_csv, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
      if(h == INVALID_HANDLE) return false;
      if(FileSize(h) == 0)
         FileWrite(h, "logged_server", "mode", "tz_policy", "session", "day", "anchor_utc",
                   "bar_server", "bar_utc", "status", "direction", "or_bars", "or_high",
                   "or_low", "atr_m5", "or_width_atr", "bar_close", "spread_now",
                   "spread_bar", "sl_dist", "tp_dist", "cost", "cost_frac", "entry", "sl",
                   "tp", "risk_approved", "volume", "risk_money", "loss_per_lot", "margin",
                   "risk_reasons");
      FileClose(h);
      return true;
   }

   void Write(const string mode, const string tz, const OrbRecord &r, const XsRiskResult &k,
              const bool risk_evaluated)
   {
      int h = FileOpen(m_csv, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | FILE_COMMON, ',');
      if(h == INVALID_HANDLE) { Print("log open failed ", GetLastError()); return; }
      FileSeek(h, 0, SEEK_END);
      FileWrite(h, XsTime(TimeTradeServer()), mode, tz, r.session, r.day, XsTime(r.anchor_utc),
                XsTime(r.bar_server), XsTime(r.bar_utc), r.status, r.direction, r.or_bars,
                XsDbl(r.or_high), XsDbl(r.or_low), XsDbl(r.atr), XsDbl(r.or_width_atr, 3), XsDbl(r.bar_close),
                XsDbl(r.spread_now), XsDbl(r.spread_bar), XsDbl(r.sl_dist), XsDbl(r.tp_dist), XsDbl(r.cost),
                XsDbl(r.cost_frac, 4), XsDbl(r.entry), XsDbl(r.sl), XsDbl(r.tp),
                risk_evaluated ? (k.approved ? "1" : "0") : "",
                risk_evaluated ? XsDbl(k.volume, 2) : "", risk_evaluated ? XsDbl(k.risk_money, 2) : "",
                risk_evaluated ? XsDbl(k.loss_per_lot, 2) : "", risk_evaluated ? XsDbl(k.margin, 2) : "",
                risk_evaluated ? k.reasons : "");
      FileClose(h);
   }

   void WriteState(const string json)
   {
      int h = FileOpen(m_json, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
      if(h == INVALID_HANDLE) return;
      FileWriteString(h, json);
      FileClose(h);
   }
};

#endif
