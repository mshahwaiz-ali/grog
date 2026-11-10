//+------------------------------------------------------------------+
//| GrogClockProbe.mq5 - one-shot, READ-ONLY MT5 clock comparison     |
//| Inspect an actual fresh XAUUSD tick against UTC and server time. |
//| No trade calls, file writes, history requests, or settings edits. |
//| Does not establish historical DST rules; use only as evidence.   |
//+------------------------------------------------------------------+
#property strict
#property script_show_inputs

input string InpSymbol = "XAUUSD";

void OnStart()
  {
   if(!TerminalInfoInteger(TERMINAL_CONNECTED))
     {
      Print("GROG_CLOCK_PROBE STATUS=NOT_CONNECTED");
      return;
     }

   MqlTick tick;
   ResetLastError();
   if(!SymbolInfoTick(InpSymbol, tick))
     {
      Print("GROG_CLOCK_PROBE STATUS=NO_TICK SYMBOL=", InpSymbol,
            " ERROR=", GetLastError());
      return;
     }

   long gmt_ms = (long)TimeGMT() * 1000;
   long server_ms = (long)TimeTradeServer() * 1000;
   long tick_ms = (long)tick.time_msc;
   long age_server_ms = server_ms - tick_ms;
   long age_gmt_ms = gmt_ms - tick_ms;

   bool server_recent = age_server_ms >= -30000 && age_server_ms <= 30000;
   bool gmt_recent = age_gmt_ms >= -30000 && age_gmt_ms <= 30000;

   string basis = "INDETERMINATE_STALE_OR_CLOCK_MISMATCH";
   if(server_recent && !gmt_recent)
      basis = "SERVER_CLOCK_CANDIDATE";
   else if(gmt_recent && !server_recent)
      basis = "UTC_CLOCK_CANDIDATE";
   else if(server_recent && gmt_recent)
      basis = "CANNOT_DISTINGUISH_ZERO_OFFSET";

   Print("GROG_CLOCK_PROBE STATUS=COMPLETE",
         " SYMBOL=", InpSymbol,
         " SERVER=", AccountInfoString(ACCOUNT_SERVER),
         " GMT_MS=", gmt_ms,
         " SERVER_MS=", server_ms,
         " TICK_MS=", tick_ms,
         " SERVER_OFFSET_MS=", server_ms - gmt_ms,
         " TICK_AGE_VS_SERVER_MS=", age_server_ms,
         " TICK_AGE_VS_GMT_MS=", age_gmt_ms,
         " BID=", DoubleToString(tick.bid, (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)),
         " ASK=", DoubleToString(tick.ask, (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS)),
         " BASIS=", basis);
  }
