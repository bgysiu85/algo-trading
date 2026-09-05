from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from common.analysis import load_sessions, LIVE
from common.scale_grid import SLIP_PER_SHARE
from common.trail_study import paired_bootstrap
from strategy.mcl import mcl as S
ET = ZoneInfo("America/New_York")
sessions = load_sessions(Path("bar_cache"))
dates = sorted({d for _,d,_ in sessions}); split = dates[len(dates)//2]

def run(ss, **kw):
    per, trades = {}, []
    for sym, d, df in ss:
        for t in S.backtest_session(df, datetime.strptime(d,"%Y-%m-%d").date(), ET, **LIVE, **kw):
            r = t.net - t.shares_traded*SLIP_PER_SHARE
            per[sym] = per.get(sym,0.0)+r; trades.append((r, t.bars_held, d))
    return per, trades

def dtop(d,k): return sum(sorted(d.values(),reverse=True)[k:])
base, bt = run(sessions, trail_pct=5.0)
def stats(per, tr):
    holds=sorted(h for _,h,_ in tr)
    return (len(tr), sum(per.values()), dtop(per,5), min(r for r,_,_ in tr),
            holds[int(len(holds)*0.95)])
def half(per, tr, lo, hi):
    return sum(r for r,_,d in tr if lo <= d < hi)
n,net,d5,w,p95 = stats(base,bt)
print(f"{'rule':<26}{'tr':>5}{'net':>9}{'delta':>8}{'P(>0)':>7}{'d5Δ':>8}"
      f"{'worst':>8}{'p95hold':>8}{'earlyΔ':>8}{'lateΔ':>8}")
print(f"{'baseline 5% intrabar':<26}{n:>5}${net:>8,.0f}{'':>8}{'':>7}{d5:>+8,.0f}"
      f"{w:>8,.0f}{p95:>8}")
be = half(base,bt,"0000","9999")
be_e = half(base,bt,"0000",split); be_l = half(base,bt,split,"9999")
rows=[("confirm %d bars"%k, dict(trail_pct=5.0, trail_confirm_bars=k)) for k in (3,5,8,12,20,40)]
rows += [("%g%% intrabar (control)"%t, dict(trail_pct=t)) for t in (10.0,15.0,20.0)]
for tag,kw in rows:
    c,ct = run(sessions, **kw)
    syms=sorted(set(base)|set(c)); b={s:base.get(s,0.) for s in syms}; cc={s:c.get(s,0.) for s in syms}
    tot,lo,hi,p = paired_bootstrap(b,cc,10000); delta={s:cc[s]-b[s] for s in syms}
    n2,net2,_,w2,p952 = stats(c,ct)
    print(f"{tag:<26}{n2:>5}${net2:>8,.0f}{tot:>+8,.0f}{p:>6.1f}%{dtop(delta,5):>+8,.0f}"
          f"{w2:>8,.0f}{p952:>8}"
          f"{half(c,ct,'0000',split)-be_e:>+8,.0f}{half(c,ct,split,'9999')-be_l:>+8,.0f}")
