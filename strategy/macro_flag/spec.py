"""MFLAG-v1 fixed numbers. REGISTERED_macro_flag_v1.md (W15-0023 step 3). Nothing here is tuned.

Every constant below is copied from the registration; a test pins the flag cells to the 12 of run 2b.
"""
from __future__ import annotations

# sec 2.1 -- the 12 flag cells of impact-map run 2b (commit 7caade4). Nothing added or dropped.
FLAG_CELLS: dict[str, tuple[str, ...]] = {
    "ES": ("NFP",),
    "CL": ("NFP",),
    "6A": ("NFP", "FOMC"),
    "6E": ("FOMC",),
    "6J": ("NFP", "FOMC"),
    "GC": ("NFP", "FOMC"),
    "SI": ("NFP", "FOMC"),
    "MTN": ("NFP",),
}
MARKETS = ("ES", "RTY", "CL", "NG", "6A", "6B", "6E", "6J", "GC", "SI", "HG", "MTN")
FLAG_MARKETS = tuple(FLAG_CELLS)                       # the "same 8 markets" of criterion 7
SCHEDULED = ("CPI", "NFP", "FOMC")                     # placebo / no-map events
ENERGY = ("CL", "NG")                                  # EIA is a relevant event only for these (no-map variant)
EIA = "EIA_WPSR"
ALL_EVENTS = ("CPI", "NFP", "FOMC", "EIA_WPSR")

# sec 4 / sec 5
MIN_FLAGGED = 60
HOST_TRADES = 1175                                     # G5
HOST_NET_MID_ROUNDED = -847                            # G5: ($847)
EQUITY = 22129.0
CR_DRAWS = 1000                                        # sec 3, C-R
PERM_DRAWS = 5000                                      # sec 4 criterion 7
CR_SEED_TAG = 23                                       # np.random.default_rng([crc32(str(d)), crc32(market), 23])
PERM_SEED_TAG = 24                                     # not given in the registration; disclosed in the report
HOLDOUT_P = 90                                         # sec 6 holdout pass: >= p90 of C-R
LOCK_FROM = "2022-01-01"

FRICTIONS = ("low", "mid", "high")


def placebo_cells() -> dict[str, tuple[str, ...]]:
    """sec 3, C-P: the 24 of the 36 CPI/NFP/FOMC cells that are NOT flag cells."""
    out = {}
    for m in MARKETS:
        evs = tuple(e for e in SCHEDULED if e not in FLAG_CELLS.get(m, ()))
        if evs:
            out[m] = evs
    return out


def nomap_cells() -> dict[str, tuple[str, ...]]:
    """sec 2.4 'No map': every market on NFP + FOMC + CPI, plus EIA for CL and NG."""
    return {m: SCHEDULED + ((EIA,) if m in ENERGY else ()) for m in MARKETS}


def per_event_cells(event: str) -> dict[str, tuple[str, ...]]:
    return {m: (event,) for m, evs in FLAG_CELLS.items() if event in evs}
