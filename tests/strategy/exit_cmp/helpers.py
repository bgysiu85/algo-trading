from strategy.chartmark import data as D
from strategy.chartmark import engine as E
from strategy.chartmark import spec as V1
from strategy.exit_cmp.entries import Entry
from strategy.exit_cmp.walk import Study
from tests.strategy.chartmark.synth import walk


def world(seed=3, n=5000, roll_every=None, drift=0.01, vol=0.2):
    fr = walk(n=n, seed=seed, drift=drift, vol=vol, roll_every=roll_every)
    ind = D.indicators(fr)
    trades, _ = E.simulate(fr, ind, V1.BASE)
    entries = [Entry(t.entry_j, t.entry_px, t.a0, t.stop0, t.placed_j, t.gap_fill, t.stop_from_entry_bar) for t in trades]
    return fr, ind, trades, entries, Study(fr, ind, entries)
