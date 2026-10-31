//+------------------------------------------------------------------+
//| GrogReferenceExporter.mq5 — READ-ONLY XAUUSD tick exporter       |
//| Transport: GROG-MT5-REF/1 (docs/09-architecture.md section 5.1)  |
//|                                                                  |
//| STATUS: AUTHORED OFFLINE, NEVER COMPILED, NEVER RUN IN MT5.      |
//| Revised by M09-H integrity hardening (2026-10-31). It has not    |
//| been tested against any terminal, server or account; every MT5   |
//| behavior it relies on is UNVERIFIED until M09-B acceptance       |
//| (docs/10 section 9). Do not rely on it before then.              |
//|                                                                  |
//| Read-only by construction: it only reads ticks, symbol/session   |
//| properties and terminal connection state, and appends bytes to   |
//| files. It includes no trade library and calls no trading,        |
//| position, order or account-changing function. Algo trading may   |
//| stay disabled in the terminal.                                   |
//+------------------------------------------------------------------+
#property copyright "Grog project (private)"
#property version   "0.2"

input string InpSourceId       = "mt5demo";    // Grog source_id (safe chars only, no "__")
input int    InpWarmupDays     = 20;           // first-start catch-up depth (days of ticks)
input int    InpTimerMs        = 1000;         // poll + heartbeat interval
input int    InpChunkMinutes   = 60;           // catch-up CopyTicksRange window
input int    InpChunksPerTimer = 4;            // catch-up windows per timer event
input long   InpRotateBytes    = 64*1024*1024; // rotate file after this size
input string InpSubDir         = "grog";       // under Common Files

// Engineering constants (not trading thresholds; docs/09 section 5.1).
#define EXPORT_ATTEMPTS  3     // CopyTicksRange attempts per window before a G gap record
#define RETRY_SLEEP_MS   500   // pause between attempts
#define EXPORTER_VERSION "0.2"

string   g_symbol;
int      g_digits;
int      g_file = INVALID_HANDLE;
string   g_session_stamp;
int      g_part = 0;
long     g_seq = 0;
long     g_last_msc = 0;        // last WRITTEN tick time_msc (trade-server clock)
int      g_last_count = 0;      // ticks written at g_last_msc
bool     g_was_connected = false;
bool     g_write_failed = false; // a short/failed write stops all output for good
int      g_last_error = 0;
string   g_state_file;
bool     g_cu_active = false;   // a catch-up block (B ... E) is open
long     g_cu_next = 0;         // next window start (inclusive)
long     g_cu_end = 0;          // block end (exclusive)
long     g_cu_ticks = 0;        // T lines written inside the open block (the E count)

//--- helpers --------------------------------------------------------
long ServerOffsetSeconds()
  {
   // UNVERIFIED: the CURRENT offset only; MT5 offers no historical offset (docs/09 5.1).
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

bool ValidSourceId(string s)
  {
   int n = StringLen(s);
   if(n < 1 || n > 64)
      return false;
   for(int i = 0; i < n; i++)
     {
      ushort c = StringGetCharacter(s, i);
      bool alnum = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z');
      if(i == 0 && !alnum)
         return false;
      if(!alnum && c != '.' && c != '_' && c != '-')
         return false;
     }
   return StringFind(s, "__") < 0;   // "__" separates the file-name fields
  }

bool SafeField(string s)
  {
   return StringLen(s) > 0 && StringFind(s, ",") < 0 && StringFind(s, "\n") < 0 &&
          StringFind(s, "\r") < 0;
  }

// One record = "<kind>,<seq><rest>\n", written as UTF-8 bytes with a single LF (FILE_BIN:
// text mode would write CR LF, FILE_ANSI the system code page). Every write is checked.
bool WriteRecord(string kind, string rest)
  {
   if(g_file == INVALID_HANDLE || g_write_failed)
      return false;
   g_seq++;
   string line = kind + "," + IntegerToString(g_seq) + rest + "\n";
   uchar bytes[];
   int n = StringToCharArray(line, bytes, 0, WHOLE_ARRAY, CP_UTF8) - 1; // drop the NUL
   if(n <= 0 || FileWriteArray(g_file, bytes, 0, n) != (uint)n)
     {
      g_write_failed = true;   // the watermark is never advanced past unwritten data
      Print("GrogReferenceExporter: write failed, error ", GetLastError(), "; output stopped");
      return false;
     }
   FileFlush(g_file);
   return true;
  }

string PartName(int part)
  {
   return InpSourceId + "__" + g_session_stamp + "__" + StringFormat("%06d", part) + ".grogref";
  }

// A session stamp whose first file does not exist yet (a same-second restart moves on).
string NewSessionStamp()
  {
   datetime t = TimeGMT();
   for(int i = 0; i < 3600; i++)
     {
      string s = Stamp(t + i);
      if(!FileIsExist(InpSubDir + "\\" + InpSourceId + "__" + s + "__000001.grogref", FILE_COMMON))
         return s;
     }
   return "";
  }

bool OpenPart()
  {
   g_part++;
   string name = InpSubDir + "\\" + PartName(g_part);
   if(FileIsExist(name, FILE_COMMON))   // never reopen, and so never truncate, a file
     {
      Print("GrogReferenceExporter: ", name, " already exists; output stopped");
      g_write_failed = true;
      return false;
     }
   g_file = FileOpen(name, FILE_WRITE | FILE_BIN | FILE_COMMON | FILE_SHARE_READ);
   if(g_file == INVALID_HANDLE)
     {
      Print("GrogReferenceExporter: cannot open ", name, " error ", GetLastError());
      g_write_failed = true;
      return false;
     }
   g_seq = 0;
   return WriteRecord("M", ",GROG-MT5-REF/1,MQL5_EXPORTER," + InpSourceId + "," +
                      AccountInfoString(ACCOUNT_SERVER) + "," + g_symbol + "," +
                      IntegerToString(g_digits) + "," + IntegerToString(ServerOffsetSeconds()) +
                      "," + EXPORTER_VERSION);
  }

void RotateIfNeeded()
  {
   if(g_file == INVALID_HANDLE || (long)FileSize(g_file) < InpRotateBytes)
      return;
   WriteRecord("Z", "," + PartName(g_part + 1));
   FileClose(g_file);
   g_file = INVALID_HANDLE;
   OpenPart();
  }

// Sessions may wrap past midnight (from > to); the previous day's wrapping session counts
// after midnight. The broker session table itself is UNVERIFIED (M09-B).
bool InSession(ENUM_DAY_OF_WEEK day, long secs, bool previous_day, int &found)
  {
   datetime from, to;
   for(uint i = 0; i < 10; i++)
     {
      if(!SymbolInfoSessionQuote(g_symbol, day, i, from, to))
         break;
      found++;
      long f = (long)from % 86400, t = (long)to % 86400;
      if(t == 0)
         t = 86400;
      if(f < t)
        {
         if(!previous_day && secs >= f && secs < t)
            return true;
        }
      else
        {
         if(!previous_day && secs >= f)
            return true;
         if(previous_day && secs < t)
            return true;
        }
     }
   return false;
  }

string SessionState()
  {
   MqlDateTime d;
   TimeToStruct(TimeTradeServer(), d);
   long secs = d.hour * 3600 + d.min * 60 + d.sec;
   int today = d.day_of_week;
   int yday = (today + 6) % 7;
   int found = 0;
   if(InSession((ENUM_DAY_OF_WEEK)today, secs, false, found))
      return "OPEN";
   if(InSession((ENUM_DAY_OF_WEEK)yday, secs, true, found))
      return "OPEN";
   return found > 0 ? "CLOSED" : "UNKNOWN";
  }

void Heartbeat()
  {
   // TimeTradeServer() has 1 s resolution: a heartbeat threshold must exceed 1 s.
   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   WriteRecord("H", "," + IntegerToString((long)TimeTradeServer() * 1000) + "," +
               (connected ? "1" : "0") + "," + SessionState() + "," +
               IntegerToString(ServerOffsetSeconds()));
  }

//--- tick export ----------------------------------------------------
// CopyTicksRange returns ticks with time_msc in [from_msc, to_msc] (BOTH inclusive). A set
// _LastError counts as a failure even when ticks were returned (possibly partial history).
int FetchTicks(long from_msc, long to_msc, MqlTick &ticks[])
  {
   for(int attempt = 1; attempt <= EXPORT_ATTEMPTS; attempt++)
     {
      ResetLastError();
      int n = CopyTicksRange(g_symbol, ticks, COPY_TICKS_INFO, (ulong)from_msc, (ulong)to_msc);
      int err = GetLastError();
      if(n >= 0 && err == 0)
         return n;
      g_last_error = err;
      Print("GrogReferenceExporter: CopyTicksRange attempt ", attempt, " failed, n=", n,
            " error ", err);
      if(attempt < EXPORT_ATTEMPTS)
         Sleep(RETRY_SLEEP_MS);
     }
   return -1;
  }

// Writes ticks (skipping the first `skip` ticks at g_last_msc that were already written);
// returns the T lines written or -1 after a write failure.
int WriteTicks(MqlTick &ticks[], int n, string mode, int skip)
  {
   int written = 0;
   for(int i = 0; i < n; i++)
     {
      if(skip > 0 && ticks[i].time_msc == g_last_msc)
        {
         skip--;
         continue;
        }
      if(!WriteRecord("T", "," + mode + "," + IntegerToString(ticks[i].time_msc) + "," +
                      Price(ticks[i].bid) + "," + Price(ticks[i].ask) + "," +
                      IntegerToString((long)ticks[i].flags)))
         return -1;
      if(ticks[i].time_msc == g_last_msc)
         g_last_count++;
      else
        {
         g_last_msc = ticks[i].time_msc;
         g_last_count = 1;
        }
      written++;
      RotateIfNeeded();
      if(g_write_failed)
         return -1;
     }
   return written;
  }

// A catch-up block starts at the watermark INCLUSIVE (Grog drops the identical re-delivery
// of that millisecond); its windows are contiguous and non-overlapping.
void StartCatchUp(long from_msc)
  {
   g_cu_active = true;
   g_cu_next = from_msc;
   g_cu_end = (long)TimeTradeServer() * 1000 + 1000;
   g_cu_ticks = 0;
   g_last_msc = from_msc;
   g_last_count = 0;
   WriteRecord("B", "," + IntegerToString(from_msc));
  }

// Timer-driven: at most InpChunksPerTimer windows per timer event, so heartbeats continue.
void CatchUpStep()
  {
   long step = (long)InpChunkMinutes * 60 * 1000;
   for(int k = 0; k < InpChunksPerTimer && g_cu_active && !g_write_failed; k++)
     {
      long a = g_cu_next;
      long b = a + step;
      if(b > g_cu_end)
         b = g_cu_end;
      long to_msc = b - 1;   // CopyTicksRange is inclusive: the next window starts at b
      MqlTick ticks[];
      int n = FetchTicks(a, to_msc, ticks);
      if(n < 0)   // retries exhausted: an explicit, irrecoverable gap (never silent)
         WriteRecord("G", "," + IntegerToString(a) + "," + IntegerToString(to_msc) + "," +
                     IntegerToString(g_last_error));
      else
        {
         int w = WriteTicks(ticks, n, "B", 0);
         if(w < 0)
            return;
         g_cu_ticks += w;
        }
      g_cu_next = b;
      if(g_cu_next >= g_cu_end)
        {
         WriteRecord("E", "," + IntegerToString(g_last_msc) + "," + IntegerToString(g_cu_ticks));
         g_cu_active = false;
         SaveState();
        }
     }
  }

// Live poll from the watermark; a failed poll is retried from the same watermark next time.
void LivePoll()
  {
   long now_msc = (long)TimeTradeServer() * 1000 + 1000;
   MqlTick ticks[];
   int n = FetchTicks(g_last_msc, now_msc, ticks);
   if(n <= 0)
      return;
   if(WriteTicks(ticks, n, "L", g_last_count) > 0)
      SaveState();
  }

//--- exporter watermark (restart catch-up start) ----------------------
bool SaveState()
  {
   if(g_write_failed) return false;   // never advance past data that was not fully written
   string tmp = g_state_file + ".tmp";
   int h = FileOpen(tmp, FILE_WRITE | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE)
     {
      Print("GrogReferenceExporter: cannot write ", tmp, " error ", GetLastError());
      return false;
     }
   uchar bytes[];
   int n = StringToCharArray(IntegerToString(g_last_msc) + "\n", bytes, 0, WHOLE_ARRAY, CP_UTF8) - 1;
   bool ok = n > 0 && FileWriteArray(h, bytes, 0, n) == (uint)n;
   FileClose(h);
   if(!ok || !FileMove(tmp, FILE_COMMON, g_state_file, FILE_COMMON | FILE_REWRITE))
     {
      Print("GrogReferenceExporter: watermark not saved, error ", GetLastError());
      return false;
     }
   return true;
  }

// 0 = no watermark yet (first start); -1 = unreadable or corrupt (refuse to start).
long LoadState()
  {
   if(!FileIsExist(g_state_file, FILE_COMMON))
      return 0;
   int h = FileOpen(g_state_file, FILE_READ | FILE_BIN | FILE_COMMON);
   if(h == INVALID_HANDLE)
      return -1;
   int size = (int)FileSize(h);
   uchar bytes[];
   uint got = (size > 0) ? FileReadArray(h, bytes, 0, size) : 0;
   FileClose(h);
   if(size < 2 || size > 24 || got != (uint)size || bytes[size - 1] != 10)
      return -1;
   string text = CharArrayToString(bytes, 0, size - 1, CP_UTF8);
   for(int i = 0; i < StringLen(text); i++)
     {
      ushort c = StringGetCharacter(text, i);
      if(c < '0' || c > '9')
         return -1;
     }
   long v = StringToInteger(text);
   return v > 0 ? v : -1;
  }

//--- event handlers ---------------------------------------------------
int OnInit()
  {
   if(!ValidSourceId(InpSourceId) || InpWarmupDays <= 0 || InpTimerMs <= 0 ||
      InpChunkMinutes <= 0 || InpChunksPerTimer <= 0 || InpRotateBytes <= 0 ||
      StringLen(InpSubDir) == 0)
     {
      Print("GrogReferenceExporter: invalid input parameters");
      return INIT_PARAMETERS_INCORRECT;
     }
   g_symbol = _Symbol;
   g_digits = (int)SymbolInfoInteger(g_symbol, SYMBOL_DIGITS);
   if(!SafeField(AccountInfoString(ACCOUNT_SERVER)) || !SafeField(g_symbol))
     {
      Print("GrogReferenceExporter: server or symbol name not representable in the transport");
      return INIT_FAILED;
     }
   g_state_file = InpSubDir + "\\" + InpSourceId + ".exporter-state";
   long start = LoadState();
   if(start < 0)
     {
      Print("GrogReferenceExporter: watermark ", g_state_file,
            " unreadable or corrupt; refusing a silent re-warm-up (inspect or remove it)");
      return INIT_FAILED;
     }
   if(start == 0)
      start = ((long)TimeTradeServer() - (long)InpWarmupDays * 86400) * 1000;
   g_session_stamp = NewSessionStamp();
   if(g_session_stamp == "" || !OpenPart())
      return INIT_FAILED;
   g_was_connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   StartCatchUp(start);
   Heartbeat();
   if(!EventSetMillisecondTimer(InpTimerMs))
      return INIT_FAILED;
   return INIT_SUCCEEDED;
  }

void OnTimer()
  {
   if(g_write_failed)
      return;                        // output stopped: no heartbeat, Grog shows OFFLINE
   bool connected = (bool)TerminalInfoInteger(TERMINAL_CONNECTED);
   if(g_cu_active)
     {
      if(connected)
         CatchUpStep();
     }
   else if(connected && !g_was_connected)
      StartCatchUp(g_last_msc);      // reconnect: catch-up from the watermark
   else if(connected)
      LivePoll();
   g_was_connected = connected;
   Heartbeat();                      // written even when no tick arrived
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
      if(g_cu_active)   // close the open block with the count actually written
         WriteRecord("E", "," + IntegerToString(g_last_msc) + "," + IntegerToString(g_cu_ticks));
      WriteRecord("Z", ",-");
      FileClose(g_file);
     }
   SaveState();
  }
//+------------------------------------------------------------------+
