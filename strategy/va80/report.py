"""VA80 v1 report writers (W15-0041). One list of blocks -> four files with identical numbers:

    .txt   the raw report (project rule: always written)
    .md    the text for the monday Result doc ("AT-n - title - RESULT")
    .html  the styled page for the artifact (negatives in brackets AND red, every number)
    .json  everything, machine readable, plus the SHA-256 of every input

Money and points never carry a minus sign: a negative is (bracketed). Nothing here is ranked: the grid and the
variants are listed in their registered order.
"""
from __future__ import annotations

import html as H
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from strategy.va80 import costs as C
from strategy.va80 import spec as S
from strategy.va80.study import LEVELS, money

TITLE = "VA80 v1 -- Dalton's 80% rule on ES 1-minute: training-side run"
REG = "REGISTERED_va80.md (W15-0025; Amendment 1 build details, Amendment 2 IBKR costs, Amendment 3 study layer)"


@dataclass(frozen=True)
class N:
    """A number cell. Negative -> (bracketed); the HTML renderer also turns it red."""
    v: float
    d: int = 0
    pre: str = ""
    suf: str = ""

    @property
    def neg(self) -> bool:
        return self.v is not None and not math.isnan(self.v) and self.v < 0 and round(abs(self.v), self.d) > 0

    def text(self) -> str:
        if self.v is None or (isinstance(self.v, float) and math.isnan(self.v)):
            return "n/a"
        t = f"{self.pre}{abs(self.v):,.{self.d}f}{self.suf}"
        return f"({t})" if self.neg else t


def D(v, d=0):
    return N(float(v), d, "$")


def pts(v, d=2):
    return N(float(v), d)


def pct(v, d=1):
    return N(float(v), d, "", "%")


def hhmm(m) -> str:
    return f"{int(m) // 60:02d}:{int(m) % 60:02d}"


# ------------------------------------------------------------------ the blocks
def _crit_rows(crit):
    return [[str(k), label, "PASS" if ok else "FAIL", detail] for k, (label, ok, detail) in crit["crit"].items()]


def _book_rows(b, label_vehicle):
    L = lambda f: [f(b[lv]) for lv in LEVELS]
    return [
        ["Gross"] + L(lambda s: D(s["gross"])), ["Costs (IBKR)"] + L(lambda s: D(s["costs"])),
        ["Net"] + L(lambda s: D(s["net"])), ["Trades"] + L(lambda s: s["trades"]),
        ["Wins"] + L(lambda s: s["wins"]), ["Losses"] + L(lambda s: s["losses"]),
        ["Win %"] + L(lambda s: pct(s["win_pct"])), ["Mean win"] + L(lambda s: D(s["mean_win"], 2)),
        ["Mean loss"] + L(lambda s: D(s["mean_loss"], 2)),
        ["Target exits"] + L(lambda s: s["exits"][S.TARGET]), ["Stop exits"] + L(lambda s: s["exits"][S.STOP]),
        ["Time exits"] + L(lambda s: s["exits"][S.TIME]), ["Worst drawdown"] + L(lambda s: D(s["max_dd"])),
    ]


def _claim_row(label, c):
    return [label, c["n"], pct(c["edge_pct"]), pct(c["stop_pct"]), pct(c["neither_pct"]),
            "yes" if c["reproduced"] else "no"]


def _plain(es) -> str:
    b, c = es["book"]["mid"], es["crt"]
    cmp_ = "above" if b["net"] > c["summary"]["p95"] else "not above"
    nd = len(c["net_mid"])
    return (f"Over the training years the rule traded {es['trades']} times on ES. At IBKR mid costs on 1 MES the book's "
            f"net result was {money(b['net'])} (gross {money(b['gross'])}, costs {money(b['costs'])}), winning {b['win_pct']:.1f}% of trades. "
            f"Entering the same sessions at random times, same side, same target and stop rule, {nd:,} times: the 95th percentile "
            f"of net is {money(c['summary']['p95'])}; the rule's net is {cmp_} it (at the {c['va80_pct']:.0f}th percentile). "
            f"The far edge was reached on {es['claim']['all']['edge_pct']:.1f}% of all triggered setups "
            f"(the claim is 80%; reproduced if at least 70%). Verdict by the registered bar: {es['verdict']}.")


def blocks(res: dict, inputs: dict | None = None) -> list:
    es = res["ES"]
    B = [("h1", TITLE),
         ("p", "TRAINING SIDE ONLY: 2010-06-07 to 2023-12-29. The holdout (2024-01-02 onward) was not read and is not spent. "
               f"Registered before any value area was computed: {REG}. Every rule, cell and threshold is the registered one."),
         ("h2", "In plain terms"), ("p", _plain(es)),
         ("h2", f"VERDICT: {es['verdict']}")]
    if es["verdict"] == "NOT READ":
        B.append(("p", f"Fewer than {S.MIN_TRADES} trades: the study is NOT READ, not failed (criterion 7). The counts are the finding."))
    elif es["crit"]["closed"]:
        B.append(("p", "Criterion 2 failed: the study is CLOSED whatever else passed (sec 4)."))
    elif es["verdict"] == "PASS":
        B.append(("p", "All seven criteria hold. This only means the holdout MAY be spent, once, by Ben's decision (sec 6); nothing was spent here."))
    B += [("h2", "Seven criteria (ES, 1 MES, IBKR mid, training side)"),
          ("table", ["#", "Criterion", "Result", "Value"], _crit_rows(es["crit"]))]
    cl = es["claim"]
    B += [("h2", "The 80% check (claim check, reported first, not a pass criterion)"),
          ("p", "Of all triggered setups, the share that trade AT the far edge before 16:00 / hit the stop level first / do neither. "
                "A setup that had already rotated traded at the far edge before the entry, so it counts as reached. "
                "Beside it, the same split for the random-time (C-RT) entries."),
          ("table", ["Set", "n", "At far edge", "Stop level first", "Neither", "Reproduced (>= 70%)"],
           [_claim_row("All triggered (rotated included)", cl["all"]), _claim_row("The trades alone (not yet rotated)", cl["trades"]),
            _claim_row("C-RT entries (all draws)", es["crt"]["claim"])]),
          ("p", f"Triggered setups already rotated: {cl['rotated']} of {cl['all']['n']}.")]
    B += [("h2", f"Book at low / mid / high friction (1 {es['vehicle']}, ES, training side)"),
          ("p", "Costs per side: fee plus 0 / 1 / 2 ticks on every market entry, stop and time exit; a resting target fill pays the fee only. "
                f"Fee {C.FEE_PER_SIDE[es['vehicle']]:.2f} per side, tick ${C.TICK_VALUE[es['vehicle']]:.2f}. Mid is the headline."),
          ("table", ["", "Low", "Mid (headline)", "High"], _book_rows(es["book"], es["vehicle"]))]
    yr, sd = es["by_year"], es["by_side"]
    years = sorted(yr["net"])
    B += [("h2", "By year and by side (net at mid)"),
          ("table", ["Year", "Trades", "Net mid", "Share of net"],
           [[y, yr["trades"][y], D(yr["net"][y]),
             pct(100.0 * yr["net"][y] / es["book"]["mid"]["net"]) if es["book"]["mid"]["net"] > 0 else "n/a"] for y in years]),
          ("table", ["Side", "Trades", "Wins", "Gross", "Net mid"],
           [[k, v["trades"], v["wins"], D(v["gross"]), D(v["net"])] for k, v in sd.items()])]
    d, h = es["distances"], es["halves"]
    B += [("h2", "Target and stop distances (points from the entry) and the two halves"),
          ("table", ["", "p10", "median", "p90"],
           [["Target distance", pts(d["target"]["p10"]), pts(d["target"]["p50"]), pts(d["target"]["p90"])],
            ["Stop distance", pts(d["stop"]["p10"]), pts(d["stop"]["p50"]), pts(d["stop"]["p90"])]]),
          ("p", f"Halves split at the median entry date {h['median_date']}: early {money(h['early'])} ({h['early_n']} trades), "
                f"late {money(h['late'])} ({h['late_n']} trades).")]
    cr, nd = es["crt"], es["cnd"]
    B += [("h2", f"Controls: {len(cr['net_mid']):,} seeded draws, net at mid"),
          ("table", ["Control", "p5", "p50", "p95", "p99", "VA80 net", "VA80 percentile"],
           [["C-RT random time (scored)"] + [D(cr["summary"][k]) for k in ("p5", "p50", "p95", "p99")]
            + [D(es["book"]["mid"]["net"]), pct(cr["va80_pct"], 0)],
            ["C-ND no-setup days (reported)"] + [D(nd["summary"][k]) for k in ("p5", "p50", "p95", "p99")]
            + [D(es["book"]["mid"]["net"]), pct(nd["va80_pct"], 0)]]),
          ("p", f"C-RT: same sessions, same side, entry at a random 1-minute bar 10:00-15:00 whose prior bar closed inside the value area "
                f"and before the far edge traded; same target and stop rule. Draws with no candidate bar on a session: "
                f"{cr['unused_mean']:.1f} per draw on average. C-ND: {nd['sessions']} sessions that opened inside the value area.")]
    g = es["grid"]
    B += [("h2", "The 27 neighbour cells (net at mid; listed in registered order, never ranked)"),
          ("table", ["Acceptance brackets", "Bracket min", "Value-area share", "Trades", "Net mid", ""],
           [[c[0], c[1], pct(100 * c[2], 0), v["trades"], D(v["net_mid"]), "primary" if c == S.CENTRE else ""]
            for c, v in g["cells"].items()]),
          ("p", f"{g['positive']} of 27 cells net > $0 at mid (criterion 6 needs {S.GRID_MIN_POSITIVE}).")]
    nq = res.get("NQ")
    vrows = [["Primary (ES, 1 MES)", es["trades"]] + [D(es["book"][lv]["net"]) for lv in LEVELS] + [pct(es["book"]["mid"]["win_pct"])]]
    for key, label in (("reclaim", "Reclaim (Imre): first 1-min close back inside"), ("one_bracket", "One bracket (grid cell 1 x 30 x 70%)"),
                       ("no_stop", "No stop: target or 16:00 only"), ("poc_half", "POC half: half out at the POC")):
        v = es["variants"][key]
        vrows.append([label, v["trades"]] + [D(v["net"][lv]) for lv in LEVELS] + [pct(v["win_pct"])])
    vrows.append(["Primary on 1 ES (same trades, ES fees)", es["trades"]] + [D(es["full"][lv]["net"]) for lv in LEVELS]
                 + [pct(es["full"]["mid"]["win_pct"])])
    if nq:
        vrows.append(["NQ, 1 MNQ", nq["trades"]] + [D(nq["book"][lv]["net"]) for lv in LEVELS] + [pct(nq["book"]["mid"]["win_pct"])])
        vrows.append(["NQ, 1 NQ", nq["trades"]] + [D(nq["full"][lv]["net"]) for lv in LEVELS] + [pct(nq["full"]["mid"]["win_pct"])])
    B += [("h2", "Reported variants (never ranked, cannot spend the holdout)"),
          ("table", ["Variant", "Trades", "Net low", "Net mid", "Net high", "Win %"], vrows)]
    if nq:
        B += [("h2", "NQ (reported): the 80% check"),
              ("table", ["Set", "n", "At far edge", "Stop level first", "Neither", "Reproduced (>= 70%)"],
               [_claim_row("All triggered (rotated included)", nq["claim"]["all"]),
                _claim_row("The trades alone (not yet rotated)", nq["claim"]["trades"])])]
    y = es["counts"]["yearly"].reset_index()
    B += [("h2", "Counts per year (ES)"),
          ("table", [str(c) for c in y.columns], [[x if not isinstance(x, (np.integer, np.floating)) else int(x) for x in row]
                                                  for row in y.to_numpy().tolist()])]
    sk = es["skipped_dates"]
    B += [("h2", "Sessions skipped for data (ES)"),
          ("p", f"{len(sk)} session(s) skipped for a missing 09:30 bar or a gap over 5 minutes (each also removes the next session's profile): "
                + (", ".join(sk) if sk else "none") + f". Skipped for a contract roll: {len(es['skipped_roll_dates'])}.")]
    s = es["sample"]
    B += [("h2", f"{len(s)} sample trades (ES, 1 MES, mid), spread over the years"),
          ("table", ["Date", "Side", "VAH", "VAL", "Entry", "Entry price", "Exit", "Net $"],
           [[r.date, "long" if r.side == S.LONG else "short", pts(r.vah), pts(r.val), hhmm(r.entry_minute), pts(r.entry_px),
             r.reason, D(r.net, 2)] for r in s.itertuples()])]
    B += [("h2", "IBKR costs used (Amendment 2, per side)"),
          ("table", ["Vehicle", "All-in fee", "Tick $", "Low", "Mid", "High"],
           [[v, D(C.FEE_PER_SIDE[v], 2), D(C.TICK_VALUE[v], 2)] + [D(C.side_cost(v, lv, "market_or_stop"), 2) for lv in LEVELS]
            for v in ("MES", "ES", "MNQ", "NQ")])]
    B += [("h2", "Method and caveats"),
          ("p", "The value area is built from 1-minute bars with each bar's volume spread evenly over its low-high ticks: an approximation "
                "of a true volume profile (sec 8). A far edge that is close and a stop that is far give a high hit rate and a poor payoff at "
                "the same time, so the 80% check and the book are read together with the distances above. Net is gross dollars less IBKR "
                "fees and ticks (Amendment 2); no commission schedule other than IBKR's was used. One run on the training side; the holdout "
                "ledger holdout_va80.json was not touched."),
          ("p", "Source files: strategy/va80/{profile,engine,controls,grid,variants,costs,study,report,run}.py; registration "
                "docs/research/REGISTERED_va80.md. Confirm the IBKR fees against Ben's first futures fills; if they differ the result is "
                "re-costed under a new amendment, not re-run as a new hypothesis.")]
    if inputs:
        B += [("h2", "Inputs (SHA-256)"), ("table", ["Input", "SHA-256"], [[k, v] for k, v in sorted(inputs.items())])]
    return B


# ------------------------------------------------------------------ renderers
def _s(c) -> str:
    return c.text() if isinstance(c, N) else str(c)


def render_txt(res: dict, inputs: dict | None = None) -> str:
    out = []
    for kind, *a in blocks(res, inputs):
        if kind == "h1":
            out += [a[0], "=" * len(a[0])]
        elif kind == "h2":
            out += ["", a[0], "-" * min(len(a[0]), 100)]
        elif kind == "p":
            out.append(a[0])
        else:
            cols, rows = a
            cells = [[_s(c) for c in r] for r in rows]
            w = [max(len(str(c)), *(len(r[i]) for r in cells)) if cells else len(str(c)) for i, c in enumerate(cols)]
            line = lambda r: "  " + "  ".join(x.ljust(w[i]) if i == 0 else x.rjust(w[i]) for i, x in enumerate(r))
            out += [line([str(c) for c in cols]), line(["-" * x for x in w])] + [line(r) for r in cells]
    return "\n".join(out) + "\n"


def render_md(res: dict, inputs: dict | None = None) -> str:
    out = []
    for kind, *a in blocks(res, inputs):
        if kind == "h1":
            out.append(f"# {a[0]}")
        elif kind == "h2":
            out += ["", f"## {a[0]}"]
        elif kind == "p":
            out += ["", a[0]]
        else:
            cols, rows = a
            esc = lambda c: _s(c).replace("|", "/")
            out += ["", "| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
            out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


_BR = re.compile(r"\(\$[\d,]+(?:\.\d+)?\)")

CSS = """body{font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#1c2330;background:#fff}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:2rem;border-bottom:1px solid #d7dbe3;padding-bottom:.2rem}
table{border-collapse:collapse;margin:.6rem 0;font-size:.9rem}th,td{padding:.25rem .7rem;border-bottom:1px solid #e6e9ef;text-align:right}
th:first-child,td:first-child{text-align:left}th{background:#f3f5f9}.neg{color:#c0262d}.pass{color:#1d7a46;font-weight:600}.fail{color:#c0262d;font-weight:600}
.verdict{font-size:1.2rem}p{margin:.5rem 0}@media (prefers-color-scheme:dark){body{background:#12151b;color:#e3e7ee}th{background:#1b2029}
th,td{border-color:#2a303b}h2{border-color:#2a303b}.neg{color:#ff6b72}}"""


def _hs(c) -> str:
    if isinstance(c, N):
        return f'<td class="neg">{H.escape(c.text())}</td>' if c.neg else f"<td>{H.escape(c.text())}</td>"
    t = H.escape(str(c))
    t = _BR.sub(lambda m: f'<span class="neg">{m.group(0)}</span>', t)
    cls = {"PASS": ' class="pass"', "FAIL": ' class="fail"'}.get(str(c), "")
    return f"<td{cls}>{t}</td>"


def render_html(res: dict, inputs: dict | None = None) -> str:
    body = []
    for kind, *a in blocks(res, inputs):
        if kind == "h1":
            body.append(f"<h1>{H.escape(a[0])}</h1>")
        elif kind == "h2":
            cls = ' class="verdict"' if a[0].startswith("VERDICT") else ""
            body.append(f"<h2{cls}>{H.escape(a[0])}</h2>")
        elif kind == "p":
            body.append("<p>" + _BR.sub(lambda m: f'<span class="neg">{m.group(0)}</span>', H.escape(a[0])) + "</p>")
        else:
            cols, rows = a
            body.append("<table><thead><tr>" + "".join(f"<th>{H.escape(str(c))}</th>" for c in cols) + "</tr></thead><tbody>"
                        + "".join("<tr>" + "".join(_hs(c) for c in r) + "</tr>" for r in rows) + "</tbody></table>")
    return (f"<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{H.escape(TITLE)}</title><style>{CSS}</style></head><body>{''.join(body)}</body></html>\n")


# ------------------------------------------------------------------ json and files
def _clean(x):
    if isinstance(x, dict):
        return {("|".join(str(i) for i in k) if isinstance(k, tuple) else str(k)): _clean(v) for k, v in x.items()}
    if isinstance(x, pd.DataFrame):
        return _clean(x.reset_index().to_dict(orient="records") if x.index.name or not isinstance(x.index, pd.RangeIndex)
                      else x.to_dict(orient="records"))
    if isinstance(x, (list, tuple)):
        return [_clean(i) for i in x]
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, np.generic):
        return _clean(x.item())
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def to_json(res: dict, inputs: dict | None = None) -> str:
    d = _clean(res)
    if inputs is not None:
        d["inputs"] = inputs
    return json.dumps(d, indent=1, default=str)


def write_all(res: dict, out_txt: Path, inputs: dict | None = None) -> list[Path]:
    """Writes <stem>.txt (the --out path), .md, .html, .json. Returns [txt, md, html, json]."""
    out_txt = Path(out_txt)
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    files = [(out_txt, render_txt(res, inputs)), (out_txt.with_suffix(".md"), render_md(res, inputs)),
             (out_txt.with_suffix(".html"), render_html(res, inputs)), (out_txt.with_suffix(".json"), to_json(res, inputs))]
    for p, text in files:
        p.write_text(text, encoding="utf-8")
    return [p for p, _ in files]
