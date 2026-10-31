# Producer-byte fixture (GROG-MT5-REF/1)

`syn__20261001T000000Z__000001.grogref` holds exactly the bytes the revised exporter's
`WriteRecord` is specified to produce (docs/09 §5.1): UTF-8 (note the non-ASCII server name),
one LF per line, no CR, `<kind>,<seq><fields>`. It declares producer `FIXTURE`: SIMULATED test
data, never reference prices. It was written by hand from the contract — **no MT5 terminal
produced it**; real exporter bytes are UNVERIFIED until M09-B.

Content: a catch-up block from the watermark with two identical same-ms ticks (both kept),
a BID-only tick, `E` count 3, heartbeats, two live ticks (ASK-only / BID-only with the other
side populated and unchanged) and a clean `Z`.
