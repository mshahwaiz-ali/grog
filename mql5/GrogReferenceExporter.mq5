//+------------------------------------------------------------------+
//| GrogReferenceExporter.mq5 — READ-ONLY XAUUSD tick exporter       |
//| Transport: GROG-MT5-REF/1 (docs/09-architecture.md section 5.1)  |
//|                                                                  |
//| STATUS: AUTHORED OFFLINE, NEVER COMPILED, NEVER RUN IN MT5.      |
//| It has not been tested against any terminal, server or account.  |
//| Do not rely on it until M09-B acceptance (docs/10 section 9).    |
//|                                                                  |
//| Read-only by construction: it only reads ticks, symbol/session   |
//| properties and terminal connection state, and appends text lines |
//| to files. It includes no trade library and calls no trading,     |
//| position, order or account-changing function. Algo trading may   |
//| stay disabled in the terminal.                                   |
//+------------------------------------------------------------------+
#property copyright "Grog project (private)"
#property version   "0.1"
#property strict

input string InpSourceId     = "mt5demo";   // Grog source_id (safe chars only)
input int    InpWarmupDays   = 20;          // first-start catch-up depth (days of ticks)
input int    InpTimerMs      = 1000;        // poll + heartbeat interval
input int    InpChunkMinutes = 60;          // catch-up CopyTicksRange window
input long   InpRotateBytes  = 64*1024*1024; // rotate file after this size
input string InpSubDir       = "grog";      // under Common Files

string   g_symbol;
int      g_digits;
int      g_file = INVALID_HANDLE;
string   g_session_stamp;
int      g_part = 0;
long     g_seq = 0;
long     g_last_msc = 0;      // last exported tick time_msc (trade-server clock)
int      g_last_count = 0;    // ticks already exported at g_last_msc
bool     g_was_connected = false;
string   g_state_file;

//--- helpers --------------------------------------------------------
long ServerOffsetSeconds()
  {
   return (long)(TimeTradeServer() - TimeGMT());
  }

string Stamp(datetime t)
  {
   MqlDateTime d;
   TimeToStruct(t, d);
   return StringFormat("%04d%02d%02dT%02d%02d%02dZ", d.year, d.mon, d.day, d.hour, d.min, d.sec);
  }

string Price(double v)
  {
   if(v <= 0.0)
      return "";
   return DoubleToString(v, g_digits);
  }

void WriteLine(string body)
  {
   if(g_file == INVALID_HANDLE)
      return;
   g_seq++;
   FileWriteString(g_file, StringFormat("%s\n", StringFormat(body, g_seq)));
   FileFlush(g_file);
  }

string FileName(int part)
  {
   return StringFormat("%s\\%s__%s__%06d.grogref", InpSubDir, InpSourceId, g_session_stamp, part);
  }

void OpenPart()
  {
   g_part++;
   g_seq = 0;
   string name = FileName(g_part);
   g_file = FileOpen(name, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON | FILE_SHARE_READ);
   if(g_file == INVALID_HANDLE)
     {
      Print("GrogReferenceExporter: cannot open ", name, " error ", GetLastError());
      return;
     }
   WriteLine(StringFormat("M,%%d,GROG-MT5-REF/1,MQL5_EXPORTER,%s,%s,%s,%d,%d,0.1",
                          InpSourceId, AccountInfoString(ACCOUNT_SERVER), g_symbol, g_digits,
                          ServerOffsetSeconds()));
  }

void RotateIfNeeded()
  {
   if(g_file == INVALID_HANDLE || (long)FileSize(g_file) < InpRotateBytes)
      return;
   string next = StringFormat("%s__%s__%06d.grogref", InpSourceId, g_session_stamp, g_part + 1);
   WriteLine("Z,%d," + next);
   FileClose(g_file);
   g_file = INVALID_HANDLE;
   OpenPart();
  }

string SessionState()
  {
   datetime now = TimeTradeServer();
   MqlDateTime d;
   TimeToStruct(now, d);
   datetime from, to;
   long secs = d.hour * 3600 + d.min * 60 + d.sec;
   bool any = false;
   for(uint i = 0; i < 10; i++)
     {
      if(!SymbolInfoSessionQuote(g_symbol, (ENUM_DAY_OF_WEEK)d.day_of_week, i, from, to))
         break;
      any = true;
      long f = (long)from % 86400, t = (long)to % 86400;
      if(t == 0)
         t = 86400;
      if(secs >= f && secs < t)
         return "OPEN";
     }
   return any ? "CLOSED" : "UNKNOWN";
  }

void Heartbeat()
  {
   long server_msc = (long)TimeTradeServer() * 1000;
   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   WriteLine(StringFormat("H,%%d,%I64d,%d,%s,%d", server_msc, connected ? 1 : 0, SessionState(),
                          ServerOffsetSeconds()));
  }

//--- tick export ----------------------------------------------------
// Exports ticks with time_msc in [from_msc, to_msc). mode "L": skips the ticks at g_last_msc
// that were already exported (no re-delivery in the live stream). mode "B": inclusive overlap,
// Grog de-duplicates inside the catch-up block.
int ExportRange(long from_msc, long to_msc, string mode)
  {
   MqlTick ticks[];
   int n = CopyTicksRange(g_symbol, ticks, COPY_TICKS_INFO, (ulong)from_msc, (ulong)to_msc);
   if(n < 0)
     {
      Print("GrogReferenceExporter: CopyTicksRange error ", GetLastError());
      return -1;
     }
   int skip = (mode == "L" && from_msc == g_last_msc) ? g_last_count : 0;
   int written = 0;
   for(int i = 0; i < n; i++)
     {
      if(skip > 0 && ticks[i].time_msc == g_last_msc)
        {
         skip--;
         continue;
        }
      WriteLine(StringFormat("T,%%d,%s,%I64d,%s,%s,%u", mode, ticks[i].time_msc,
                             Price(ticks[i].bid), Price(ticks[i].ask), ticks[i].flags));
      if(ticks[i].time_msc == g_last_msc)
         g_last_count++;
      else
        {
         g_last_msc = ticks[i].time_msc;
         g_last_count = 1;
        }
      written++;
      RotateIfNeeded();
     }
   return written;
  }

void CatchUp(long from_msc)
  {
   long now_msc = (long)TimeTradeServer() * 1000 + 1000;
   WriteLine(StringFormat("B,%%d,%I64d", from_msc));
   long total = 0;
   long step = (long)InpChunkMinutes * 60 * 1000;
   g_last_msc = from_msc;
   g_last_count = 0;
   for(long a = from_msc; a < now_msc; a += step)
     {
      int w = ExportRange(a, MathMin(a + step, now_msc), "B");
      if(w > 0)
         total += w;
     }
   WriteLine(StringFormat("E,%%d,%I64d,%I64d", g_last_msc, total));
   SaveState();
  }

//--- exporter cursor (restart catch-up start) -------------------------
void SaveState()
  {
   int h = FileOpen(g_state_file, FILE_WRITE | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return;
   FileWriteString(h, StringFormat("%I64d\n", g_last_msc));
   FileClose(h);
  }

long LoadState()
  {
   if(!FileIsExist(g_state_file, FILE_COMMON))
      return 0;
   int h = FileOpen(g_state_file, FILE_READ | FILE_TXT | FILE_ANSI | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return 0;
   long v = StringToInteger(FileReadString(h));
   FileClose(h);
   return v;
  }

//--- event handlers ---------------------------------------------------
int OnInit()
  {
   g_symbol = _Symbol;
   g_digits = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);
   g_session_stamp = Stamp(TimeGMT());
   g_state_file = StringFormat("%s\\%s.exporter-state", InpSubDir, InpSourceId);
   OpenPart();
   if(g_file == INVALID_HANDLE)
      return INIT_FAILED;
   long start = LoadState();
   if(start <= 0)
      start = ((long)TimeTradeServer() - (long)InpWarmupDays * 86400) * 1000;
   g_was_connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   CatchUp(start);
   Heartbeat();
   EventSetMillisecondTimer(InpTimerMs);
   return INIT_SUCCEEDED;
  }

void OnTimer()
  {
   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   if(connected && !g_was_connected)
      CatchUp(g_last_msc);          // reconnect: bounded inclusive catch-up
   else if(connected)
     {
      long now_msc = (long)TimeTradeServer() * 1000 + 1000;
      if(ExportRange(g_last_msc, now_msc, "L") > 0)
         SaveState();
     }
   g_was_connected = connected;
   Heartbeat();                     // written even when no tick arrived
  }

void OnTick()
  {
   // Intentionally empty: OnTick events can be coalesced, so ticks are taken from
   // CopyTicksRange on the timer instead. Nothing here may ever trade.
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   if(g_file != INVALID_HANDLE)
     {
      WriteLine("Z,%d,-");
      FileClose(g_file);
     }
   SaveState();
  }
//+------------------------------------------------------------------+
