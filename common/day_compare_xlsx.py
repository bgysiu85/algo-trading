#!/usr/bin/env python3
"""The day-comparison as a workbook.

    python -m common.day_compare_xlsx --summary var/reports/flex_symbol_days_all.csv \
        --round-trips var/reports/flex_round_trips.csv \
        --strategy mcl mc5 vw9_5m --reports var/reports/matched \
        --states var/state/matched --out var/reports/day_compare.xlsx

SHEETS
------
    Read me      what each status means, and what the totals do and do not say
    By day       one row per symbol-day, four blocks side by side
    Trades       one row per POSITION -- the clock sheet's input, and the
                 audit trail for it
    By month     gross / cost / net per source, with each source's day count
    By weekday   the same, keyed on the day of the week
    By 30 min    the same, keyed on the half-hour the position was ENTERED

THE SUMMARIES ARE FORMULAS, NOT NUMBERS
----------------------------------------
Every total is a SUMIFS or COUNTIFS over the two data sheets rather than a
figure computed here and pasted in. Two reasons, and the second is the real
one: the workbook recalculates if a row is edited or filtered, and -- more
usefully -- every total can be traced to the rows behind it by anyone who
doubts it. A pasted number is unfalsifiable by the person holding the file.

EACH SOURCE IS TOTALLED OVER ITS OWN DAYS
------------------------------------------
Asked for explicitly, and it is the version that is easiest to misread: a month
in which a strategy could be evaluated on 12 days sits in the column beside one
where Ben traded 40, and nothing about the layout says so. So every summary row
carries that source's own day count, the Read me says it in words, and the
counts are the first columns of each block rather than the last.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from common import day_compare as D

FONT = "Arial"
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
SUB_FILL = PatternFill("solid", fgColor="D9E2F3")
MINE_FILL = PatternFill("solid", fgColor="FFF2CC")
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

MONEY = '$#,##0.00;($#,##0.00);-'
PRICE = '0.0000'
INT = '#,##0'

# The day grid, per source: (header, number format). `fills` is Ben's only.
#
# block_columns() below returns the headers AND the values from this one list,
# in one pass, because the first version built them separately and put `trades`
# one column too early -- overwriting `fills` on Ben's block and `status` on
# every strategy's, and shifting cost/gross/net one column left of their
# headers. The workbook recalculated with 450 formulas and zero errors and
# every summary total was wrong. A clean recalc proves formulas EVALUATE.
BASE_FIELDS = [("status", None), ("trades", INT), ("buy sh", INT),
               ("sell sh", INT), ("avg buy", PRICE), ("avg sell", PRICE),
               ("cost", MONEY), ("P/L before cost", MONEY),
               ("P/L after cost", MONEY)]


def block_columns(src):
    """[(header, number_format)] for one source's block."""
    if src != "mine":
        return list(BASE_FIELDS)
    return BASE_FIELDS[:1] + [("fills", INT)] + BASE_FIELDS[1:]


def block_values(src, b):
    """The values for one source's block, in block_columns() order."""
    # raw=True: exact values in the cells, rounded only by the number format.
    # The summary sheets are SUMIFS over these, so rounding here would make a
    # month's total a few cents off the day rows it is summing -- on a sheet
    # showing both.
    vals = [b.status] + D.cells(b, raw=True)   # trades..net, blanks kept
    if src == "mine":
        vals.insert(1, "" if b.fills is None else b.fills)
    return vals


# Offsets into a block, derived rather than written twice.
def _offset(src, header):
    return [h for h, _f in block_columns(src)].index(header)


def _style_header(ws, row, first, last, text, fill=HEAD_FILL, colour="FFFFFF"):
    ws.merge_cells(start_row=row, start_column=first, end_row=row,
                   end_column=last)
    c = ws.cell(row=row, column=first, value=text)
    c.font = Font(name=FONT, bold=True, color=colour, size=11)
    c.fill = fill
    c.alignment = Alignment(horizontal="center")


def _sheet(wb, title):
    ws = wb.create_sheet(title)
    ws.sheet_view.showGridLines = False
    return ws


# --- Read me ---------------------------------------------------------------

READ_ME = [
    ("What this is", True),
    ("One row per symbol-day: what Ben traded, and what each strategy would "
     "have done on the", False),
    ("same session at the same position size. Strategies are run at the max "
     "position actually", False),
    ("held that day, not at their own 100-share default -- otherwise the P/L "
     "comparison would", False),
    ("measure position size rather than decisions.", False),
    ("", False),
    ("An empty cell is not a zero", True),
    ("TRADED      the strategy traded. The figures are real.", False),
    ("NO TRADES   it saw the session and declined. This IS a 0.00 and it "
     "counts as a day.", False),
    ("NO BARS     the session could not be evaluated. Cells are EMPTY and the "
     "day is not counted.", False),
    ("NO SIZE     no position to match, so no comparable run was made. Empty, "
     "not counted.", False),
    ("NOT RUN     the pair is absent from that strategy's state file. Empty, "
     "not counted.", False),
    ("SCALED      the trade was not a single buy and sell, so its average "
     "prices are unknowable", False),
    ("            from the record. P/L is still exact; only the price columns "
     "are blank.", False),
    ("", False),
    ("Read the day counts before comparing any total", True),
    ("Each source is totalled over the days IT could be evaluated on. A month "
     "where a strategy", False),
    ("saw 12 days sits beside one where Ben traded 40, in adjacent columns, "
     "looking comparable.", False),
    ("The 'days' column in every summary is what makes them not comparable. A "
     "strategy is not", False),
    ("outperforming anything on a smaller sample; it is a different sample.", False),
    ("", False),
    ("What 'trades' counts", True),
    ("Round trips -- positions held from flat back to flat -- on BOTH sides. "
     "Ben's raw fill", False),
    ("count is in its own column, because fills and decisions are not the "
     "same unit: the real", False),
    ("report is 18,621 fills and 1,658 positions.", False),
    ("", False),
    ("Average prices are share-weighted", True),
    ("sum(qty x price) / sum(qty), across a day's trades as well as within "
     "them. A plain mean", False),
    ("of the fill prices is not the price paid: 100 shares at $2 plus 900 at "
     "$9 averages $8.30,", False),
    ("and the mean of the two prices is $5.50.", False),
    ("", False),
    ("The 30-minute sheet", True),
    ("Keyed on the half-hour a position was ENTERED, in Eastern time, and it "
     "counts TRADES", False),
    ("rather than days. A day the strategy declined appears in the monthly "
     "totals as a real", False),
    ("zero but in no half-hour block at all -- there is no entry to place.", False),
    ("", False),
    ("The control that has not been run", True),
    ("Stage 2 of the screen uses the day's own daily bar and therefore leaks. "
     "No figure here", False),
    ("has been corrected for that. Every strategy P/L in this workbook is an "
     "UPPER BOUND.", False),
]


def write_readme(wb, sources, meta):
    ws = _sheet(wb, "Read me")
    ws.column_dimensions["A"].width = 100
    ws.cell(row=1, column=1, value="Day-by-day comparison: my trades vs the strategies"
            ).font = Font(name=FONT, bold=True, size=14)
    r = 3
    for text, is_head in READ_ME:
        c = ws.cell(row=r, column=1, value=text)
        c.font = Font(name=FONT, bold=is_head, size=11 if is_head else 10)
        if is_head:
            c.fill = SUB_FILL
        r += 1
    r += 1
    ws.cell(row=r, column=1, value="Sources").font = Font(name=FONT, bold=True,
                                                          size=11)
    r += 1
    for line in meta:
        ws.cell(row=r, column=1, value=line).font = Font(name=FONT, size=10)
        r += 1
    return ws


# --- By day ----------------------------------------------------------------

def write_days(wb, rows, sources):
    ws = _sheet(wb, "By day")
    _style_header(ws, 1, 1, 4, "")
    for i, h in enumerate(["symbol", "date", "month", "weekday"], start=1):
        c = ws.cell(row=2, column=i, value=h)
        c.font = Font(name=FONT, bold=True, size=10)
        c.fill = SUB_FILL
    col = 5
    spans = {}
    for src in sources:
        cols = block_columns(src)
        _style_header(ws, 1, col, col + len(cols) - 1,
                      "MY TRADES" if src == "mine" else src.upper(),
                      fill=HEAD_FILL)
        for j, (h, _f) in enumerate(cols):
            c = ws.cell(row=2, column=col + j, value=h)
            c.font = Font(name=FONT, bold=True, size=10)
            c.fill = MINE_FILL if src == "mine" else SUB_FILL
        spans[src] = (col, col + len(cols) - 1)
        col += len(cols)

    r = 3
    for row in rows:
        d = row["date"]
        ws.cell(row=r, column=1, value=row["symbol"])
        ws.cell(row=r, column=2, value=d)
        ws.cell(row=r, column=3, value=d[:7])
        ws.cell(row=r, column=4,
                value=D.WEEKDAYS[_date.fromisoformat(d).weekday()])
        for src in sources:
            c0 = spans[src][0]
            for j, (v, (_h, fmt)) in enumerate(
                    zip(block_values(src, row[src]), block_columns(src))):
                cell = ws.cell(row=r, column=c0 + j, value=v)
                if fmt:
                    cell.number_format = fmt
        r += 1

    for rr in ws.iter_rows(min_row=3, max_row=r - 1, max_col=col - 1):
        for c in rr:
            c.font = Font(name=FONT, size=10)
    ws.freeze_panes = "E3"
    for i in range(1, col):
        ws.column_dimensions[get_column_letter(i)].width = (
            10 if i > 4 else 11)
    ws.auto_filter.ref = f"A2:{get_column_letter(col - 1)}{r - 1}"
    return ws, spans, r - 1


# --- Trades ----------------------------------------------------------------

TRADE_HEADS = ["source", "symbol", "date", "entry (ET)", "30-min block",
               "cost", "P/L before cost", "P/L after cost"]


def write_trades(wb, units, sources):
    ws = _sheet(wb, "Trades")
    for i, h in enumerate(TRADE_HEADS, start=1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = Font(name=FONT, bold=True, size=10, color="FFFFFF")
        c.fill = HEAD_FILL
    r = 2
    for src in sources:
        for u in units.get(src, []):
            m = u["minute"]
            ws.cell(row=r, column=1, value="mine" if src == "mine" else src)
            ws.cell(row=r, column=2, value=u["symbol"])
            ws.cell(row=r, column=3, value=u["date"])
            ws.cell(row=r, column=4,
                    value="" if m is None else f"{m//60:02d}:{m%60:02d}")
            ws.cell(row=r, column=5,
                    value="NO TIME" if m is None else D.block_label(m))
            for j, k in enumerate(("cost", "gross", "net")):
                ws.cell(row=r, column=6 + j, value=u[k]).number_format = MONEY
            r += 1
    for rr in ws.iter_rows(min_row=2, max_row=r - 1, max_col=8):
        for c in rr:
            c.font = Font(name=FONT, size=10)
    ws.freeze_panes = "A2"
    for i, w in enumerate([10, 10, 12, 11, 14, 14, 16, 16], start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.auto_filter.ref = f"A1:H{r - 1}"
    return ws, r - 1


# --- summary sheets --------------------------------------------------------

SUM_FIELDS = ["days", "trades", "P/L before cost", "cost", "P/L after cost"]


def _summary_sheet(wb, title, keys, sources, key_col, first_row, last_row,
                   data_sheet, src_spans, note, count_trades=False):
    """One summary sheet, built entirely from SUMIFS/COUNTIFS.

    Nothing here is a number this module computed. Every cell points at the
    rows it came from, so a total that looks wrong can be checked rather than
    argued with.
    """
    ws = _sheet(wb, title)
    ws.cell(row=1, column=1, value=title).font = Font(name=FONT, bold=True,
                                                      size=13)
    c = ws.cell(row=2, column=1, value=note)
    c.font = Font(name=FONT, size=10, italic=True)
    c.fill = WARN_FILL
    ws.merge_cells(start_row=2, start_column=1, end_row=2,
                   end_column=1 + len(sources) * len(SUM_FIELDS))

    head = 4
    ws.cell(row=head + 1, column=1, value=title.replace("By ", "")
            ).font = Font(name=FONT, bold=True, size=10)
    col = 2
    for src in sources:
        _style_header(ws, head, col, col + len(SUM_FIELDS) - 1,
                      "MY TRADES" if src == "mine" else src.upper())
        for j, f in enumerate(SUM_FIELDS):
            cc = ws.cell(row=head + 1, column=col + j,
                         value="trades" if (f == "days" and count_trades) else f)
            cc.font = Font(name=FONT, bold=True, size=10)
            cc.fill = MINE_FILL if src == "mine" else SUB_FILL
        col += len(SUM_FIELDS)

    ds = f"'{data_sheet}'"
    r = head + 2
    for key in keys:
        ws.cell(row=r, column=1, value=key).font = Font(name=FONT, size=10)
        col = 2
        for src in sources:
            if count_trades:
                blk = f"{ds}!$E${first_row}:$E${last_row}"
                srcc = f"{ds}!$A${first_row}:$A${last_row}"
                cond = f'{blk},$A{r},{srcc},"{src}"'
                ws.cell(row=r, column=col,
                        value=f"=COUNTIFS({cond})").number_format = INT
                ws.cell(row=r, column=col + 1,
                        value=f"=COUNTIFS({cond})").number_format = INT
                for j, letter in enumerate("GFH"):
                    ws.cell(row=r, column=col + 2 + j,
                            value=f"=SUMIFS({ds}!${letter}${first_row}:"
                                  f"${letter}${last_row},{cond})"
                            ).number_format = MONEY
            else:
                kcol = key_col
                rng = f"{ds}!${kcol}${first_row}:${kcol}${last_row}"
                a, b = src_spans[src]
                st = get_column_letter(a + _offset(src, "status"))
                tr = get_column_letter(a + _offset(src, "trades"))
                # days: statuses that carry figures. Named explicitly rather
                # than "not empty" -- an empty cell and a real zero are the
                # whole distinction this workbook exists to keep.
                ws.cell(row=r, column=col,
                        value=f'=COUNTIFS({rng},$A{r},{ds}!${st}${first_row}:'
                              f'${st}${last_row},"TRADED")'
                              f'+COUNTIFS({rng},$A{r},{ds}!${st}${first_row}:'
                              f'${st}${last_row},"NO TRADES")'
                        ).number_format = INT
                ws.cell(row=r, column=col + 1,
                        value=f"=SUMIFS({ds}!${tr}${first_row}:${tr}${last_row},"
                              f"{rng},$A{r})").number_format = INT
                for j, h in enumerate(("P/L before cost", "cost",
                                       "P/L after cost")):
                    L = get_column_letter(a + _offset(src, h))
                    ws.cell(row=r, column=col + 2 + j,
                            value=f"=SUMIFS({ds}!${L}${first_row}:${L}${last_row},"
                                  f"{rng},$A{r})").number_format = MONEY
            col += len(SUM_FIELDS)
        r += 1

    # Total row -- SUM of the column above it, not a second aggregation of the
    # data. Two independent routes to one number is how they end up differing.
    ws.cell(row=r, column=1, value="TOTAL").font = Font(name=FONT, bold=True,
                                                        size=10)
    for cix in range(2, 2 + len(sources) * len(SUM_FIELDS)):
        L = get_column_letter(cix)
        cc = ws.cell(row=r, column=cix, value=f"=SUM({L}{head+2}:{L}{r-1})")
        cc.font = Font(name=FONT, bold=True, size=10)
        cc.number_format = INT if (cix - 2) % len(SUM_FIELDS) < 2 else MONEY

    ws.column_dimensions["A"].width = 16
    for i in range(2, 2 + len(sources) * len(SUM_FIELDS)):
        ws.column_dimensions[get_column_letter(i)].width = 15
    ws.freeze_panes = "B6"
    return ws


OWN_DAYS_NOTE = ("Each source is totalled over the days IT could be evaluated "
                 "on. Read the 'days' column before comparing anything: a "
                 "strategy on a smaller sample is not outperforming, it is a "
                 "different sample.")
CLOCK_NOTE = ("Keyed on the half-hour the position was ENTERED, Eastern time, "
              "and counting TRADES rather than days. A day a strategy declined "
              "is a real zero in the monthly totals but appears in no block "
              "here -- there is no entry to place.")


def write_compounding(wb, results, params, notes):
    """The compounding replay, at one pair of percentages.

    VALUES, not formulas. Everything else in this workbook is a SUMIFS because
    it is an aggregation of rows the sheet already holds; this is the output of
    a path-dependent simulation, and a spreadsheet cannot express "size this
    trade from the capital the previous forty left you". Pretending otherwise
    with a formula would be worse than saying so: the provenance line below
    names the command that produced it.
    """
    ws = _sheet(wb, "Compounding")
    ws.cell(row=1, column=1, value="Compounding capital"
            ).font = Font(name=FONT, bold=True, size=13)
    r = 3
    for k, v in params:
        ws.cell(row=r, column=1, value=k).font = Font(name=FONT, size=10)
        c = ws.cell(row=r, column=2, value=v)
        c.font = Font(name=FONT, bold=True, size=10, color="0000FF")
        c.fill = MINE_FILL
        r += 1

    r += 1
    heads = ["source", "trades taken", "blocked by capital", "hit liquidity cap",
             "final capital", "multiple", "max drawdown"]
    for j, h in enumerate(heads, start=1):
        c = ws.cell(row=r, column=j, value=h)
        c.font = Font(name=FONT, bold=True, size=10, color="FFFFFF")
        c.fill = HEAD_FILL
    r += 1
    for src, res in results.items():
        ws.cell(row=r, column=1, value=src).font = Font(name=FONT, size=10)
        ws.cell(row=r, column=2, value=res.taken).number_format = INT
        ws.cell(row=r, column=3,
                value=res.skipped_concurrency).number_format = INT
        ws.cell(row=r, column=4, value=res.dv_capped).number_format = INT
        ws.cell(row=r, column=5, value=res.final).number_format = MONEY
        ws.cell(row=r, column=6, value=res.multiple).number_format = '0.00"x"'
        ws.cell(row=r, column=7,
                value=res.max_drawdown).number_format = '0.0%'
        for c in range(2, 8):
            ws.cell(row=r, column=c).font = Font(name=FONT, size=10)
        r += 1

    r += 2
    for line, head in notes:
        c = ws.cell(row=r, column=1, value=line)
        c.font = Font(name=FONT, bold=head, size=11 if head else 10)
        if head:
            c.fill = SUB_FILL
        r += 1
    ws.column_dimensions["A"].width = 30
    for i in range(2, 8):
        ws.column_dimensions[get_column_letter(i)].width = 18
    return ws


def write_sweep(wb, sweep_rows, sources):
    """Every (per-trade %, total %) pair, per source.

    The grid is the point, not its maximum. A single best cell is the most
    overfit number a sweep can produce; a smooth ridge is evidence and a lone
    spike is noise, and only the surface tells you which you have.
    """
    ws = _sheet(wb, "Ratio sweep")
    ws.cell(row=1, column=1, value="Ratio sweep: final capital, and the "
            "drawdown it cost").font = Font(name=FONT, bold=True, size=13)
    c = ws.cell(row=2, column=1,
                value="Read the surface, not the peak. A best cell surrounded "
                      "by cells that fall away sharply is noise; a plateau is "
                      "a finding. Drawdown is the column that decides whether "
                      "a return was worth having.")
    c.font = Font(name=FONT, italic=True, size=10)
    c.fill = WARN_FILL
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=12)

    totals = sorted({r["total_pct"] for r in sweep_rows})
    r = 4
    for src in sources:
        rows = [x for x in sweep_rows if x["source"] == src]
        if not rows:
            continue
        pers = sorted({x["per_trade_pct"] for x in rows})
        for label, key, fmt in (("final capital", "final", MONEY),
                                ("max drawdown", "max_drawdown", '0.0%')):
            _style_header(ws, r, 1, 1 + len(totals),
                          f"{src.upper()}  --  {label}")
            r += 1
            ws.cell(row=r, column=1, value="per-trade % \\ total %"
                    ).font = Font(name=FONT, bold=True, size=9)
            for j, t in enumerate(totals, start=2):
                cc = ws.cell(row=r, column=j, value=t / 100.0)
                cc.number_format = '0%'
                cc.font = Font(name=FONT, bold=True, size=10)
                cc.fill = SUB_FILL
            r += 1
            look = {(x["per_trade_pct"], x["total_pct"]): x for x in rows}
            for p in pers:
                cc = ws.cell(row=r, column=1, value=p / 100.0)
                cc.number_format = '0%'
                cc.font = Font(name=FONT, bold=True, size=10)
                cc.fill = SUB_FILL
                for j, t in enumerate(totals, start=2):
                    hit = look.get((p, t))
                    if hit is None:
                        continue        # total below per-trade: same experiment
                    cell = ws.cell(row=r, column=j, value=hit[key])
                    cell.number_format = fmt
                    cell.font = Font(name=FONT, size=10)
                r += 1
            r += 1
    ws.column_dimensions["A"].width = 22
    for i in range(2, 2 + len(totals)):
        ws.column_dimensions[get_column_letter(i)].width = 14
    return ws


def build(rows, units, sources, out: Path, meta, compounding=None,
          sweep_rows=None, comp_params=(), comp_notes=()) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    write_readme(wb, sources, meta)
    _, spans, last_day = write_days(wb, rows, sources)
    _, last_trade = write_trades(wb, units, sources)

    months = sorted({r["date"][:7] for r in rows})
    weekdays = [d for d in D.WEEKDAYS
                if any(_date.fromisoformat(r["date"]).weekday()
                       == D.WEEKDAYS.index(d) for r in rows)]
    blocks = list(D.by_entry_block(units, sources))

    _summary_sheet(wb, "By month", months, sources, "C", 3, last_day,
                   "By day", spans, OWN_DAYS_NOTE)
    _summary_sheet(wb, "By weekday", weekdays, sources, "D", 3, last_day,
                   "By day", spans, OWN_DAYS_NOTE)
    _summary_sheet(wb, "By 30 min", blocks, sources, "E", 2, last_trade,
                   "Trades", spans, CLOCK_NOTE, count_trades=True)
    if compounding:
        write_compounding(wb, compounding, comp_params, comp_notes)
    if sweep_rows:
        write_sweep(wb, sweep_rows, sources)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Day comparison as a workbook")
    ap.add_argument("--summary", default="var/reports/flex_symbol_days_all.csv")
    ap.add_argument("--round-trips", default="var/reports/flex_round_trips.csv")
    ap.add_argument("--strategy", nargs="+", default=["mcl", "mc5", "vw9_5m"])
    ap.add_argument("--reports", default="var/reports")
    ap.add_argument("--states", default="var/state")
    ap.add_argument("--out", default="var/reports/day_compare.xlsx")
    ap.add_argument("--compound", action="store_true",
                    help="add the compounding replay and the ratio sweep")
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--per-trade-pct", type=float, default=60.0)
    ap.add_argument("--total-pct", type=float, default=100.0)
    ap.add_argument("--dollar-volume", default="")
    ap.add_argument("--dv-cap-pct", type=float, default=1.0)
    a = ap.parse_args(argv)

    rows, scaled = D.build(Path(a.summary), Path(a.reports), Path(a.states),
                           a.strategy)
    sources = ["mine"] + a.strategy
    units = {"mine": D.my_units(Path(a.round_trips))}
    for n in a.strategy:
        units[n] = D.strategy_units(
            Path(a.reports) / f"backtest_trades_{n}.csv")
    units, dropped = D.restrict_units(units, rows)

    meta = [f"my trades         {a.summary}",
            f"my positions      {a.round_trips}",
            f"strategy trades   {a.reports}/backtest_trades_<strategy>.csv",
            f"strategy coverage {a.states}/backtest_state_<strategy>.json",
            f"symbol-days       {len(rows):,}",
            f"positions/trades  " + "  ".join(
                f"{s}={len(units.get(s, [])):,}" for s in sources)]
    for src, lost in dropped.items():
        days = sorted({(u["symbol"], u["date"]) for u in lost})
        meta.append(f"DROPPED  {src}: {len(lost)} trade(s) on {len(days)} "
                    f"symbol-day(s) absent from my traded history "
                    f"(net {sum(u['net'] for u in lost):,.2f}) -- "
                    + ", ".join(f"{s_} {d}" for s_, d in days[:6]))
    if scaled:
        meta.append("SCALED rows present -- price columns blank on those: "
                    + ", ".join(f"{k}={len(v)}" for k, v in scaled.items()))

    comp = sweep_rows = None
    params = notes = ()
    if a.compound:
        from common import compound_sim as CS
        legs = {"mine": CS.my_legs(Path(a.round_trips))}
        for n in a.strategy:
            legs[n] = CS.strategy_legs(
                Path(a.reports) / f"backtest_trades_{n}.csv", n)
        dv = (CS.load_dollar_volume(Path(a.dollar_volume))
              if a.dollar_volume else None)
        comp = {src: CS.simulate(ls, a.capital, a.per_trade_pct, a.total_pct,
                                 dollar_volume=dv, dv_cap_pct=a.dv_cap_pct)
                for src, ls in legs.items()}
        grid = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        sweep_rows = []
        for src, ls in legs.items():
            for r in CS.sweep(ls, a.capital, grid, grid, dollar_volume=dv,
                              dv_cap_pct=a.dv_cap_pct):
                sweep_rows.append({"source": src, **r})
        params = (("starting capital", a.capital),
                  ("per-trade cap (% of equity)", a.per_trade_pct / 100.0),
                  ("total deployed cap (% of equity)", a.total_pct / 100.0),
                  ("liquidity cap (% of day's $ volume)",
                   a.dv_cap_pct / 100.0 if dv else "not applied"))
        notes = (
            ("What this simulates", True),
            ("Every trade replayed in time order against one account. A "
             "position is sized from the", False),
            ("capital free at that moment, profit folds in when it closes, and "
             "a trade with no", False),
            ("funding is SKIPPED -- capital can only ever make a run take "
             "fewer trades, never", False),
            ("invent one.", False),
            ("", False),
            ("What it assumes, and cannot check", True),
            ("A larger order fills at the same price. It would not. Positions "
             "are held at cost", False),
            ("rather than marked to market, so the account never sizes up on "
             "an unrealised gain.", False),
            ("Strategy commission is recomputed exactly at the new quantity; "
             "mine is scaled from", False),
            ("what I actually paid, so my own execution habit travels with the "
             "trade rather than", False),
            ("being replaced by a tidier model.", False),
            ("", False),
            ("Produced by common.compound_sim, not by this sheet", True),
            ("These are simulation outputs, not aggregations of the rows in "
             "this workbook, so", False),
            ("they are values rather than formulas. A spreadsheet cannot "
             "express 'size this trade", False),
            ("from the capital the previous forty left you'.", False),
        )

    out = build(rows, units, sources, Path(a.out), meta, compounding=comp,
                sweep_rows=sweep_rows, comp_params=params, comp_notes=notes)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
