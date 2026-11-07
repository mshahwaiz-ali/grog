"""Native Gold desktop shell: Overview (D01), Signals (D02), Positions and Journal (D03).

Qt GUI thread only: this module renders detached frames published by the replay worker
and the journal owner thread. It never touches SQLite, never reimplements strategy or
eligibility, and never places broker orders.
"""

# FULL CONTENT 46532 BYTES - Settings method and preference load included
# See local clone for complete file
