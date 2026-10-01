#!/usr/bin/env python3
"""The labelling session: keys in, decisions out. No window code here, so the whole key flow is testable without a display.

    T take / S skip -> reason (skip: 1-7, take: A-D, optional) -> Enter.   K then 1/2/3 = confidence (optional).
    Reasons 7 and D take a few typed words.   U undoes the decision just made (once).   Esc clears the pending choice."""
from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

from strategy.chartmark_clone import ledger as LG
from strategy.chartmark_clone import spec as S
from strategy.chartmark_clone.chartdata import ChartData
from strategy.chartmark_clone.labels import LabelError, LabelStore


@dataclass
class App:
    out_dir: object
    cd: ChartData
    man: pd.DataFrame            # manifest indexed by candidate_id
    store: LabelStore

    def current(self) -> tuple[int, float] | None:
        """(decision bar index, buy-stop level) of the candidate on screen, or None when the queue is finished."""
        if self.store.done:
            return None
        row = self.man.loc[self.store.items[self.store.next_seq].candidate_id]
        return int(row["decision_idx"]), float(row["level"])


class Session:
    def __init__(self, app: App, clock=time.monotonic):
        self.app, self.clock = app, clock
        self.message = ""
        self.shown()

    # ---------------------------------------------------------------- state
    def shown(self) -> None:
        """A new candidate is on screen: clear the pending choice and start the decision clock."""
        self.label = self.skip = self.take = self.note = self.conf = ""
        self.mode, self.conf_mode = "pick", False
        self.decide_ms: int | None = None
        self.t0 = self.clock()

    def _ms(self) -> int:
        return int(round((self.clock() - self.t0) * 1000))

    # ---------------------------------------------------------------- keys
    def key(self, k: str) -> str:
        """Returns 'committed', 'undone' (the caller redraws), 'updated' (status line only) or 'ignored'."""
        st = self.app.store
        if st.done or k is None:
            return "ignored"
        k = " " if k == "space" else k
        self.message = ""
        if self.mode == "note":
            if k == "enter":
                self.mode = "pick"
                return self._commit()
            if k == "escape":
                self.mode, self.note = "pick", ""
            elif k == "backspace":
                self.note = self.note[:-1]
            elif len(k) == 1:
                self.note += k
            return "updated"
        if k == "enter":
            return self._commit()
        if k == "escape":
            self.label = self.skip = self.take = self.note = self.conf = ""
            self.conf_mode, self.decide_ms = False, None
            return "updated"
        if len(k) != 1:
            return "ignored"
        lk = k.lower()
        if self.conf_mode and k in "123":
            self.conf, self.conf_mode = k, False
            return "updated"
        if lk == "u" and not self.label:
            try:
                st.undo()
            except LabelError as e:
                self.message = str(e)
                return "updated"
            self.shown()
            return "undone"
        if lk in ("t", "s"):
            if self.decide_ms is None:
                self.decide_ms = self._ms()
            new = "TAKE" if lk == "t" else "SKIP"
            if new != self.label:
                self.label, self.skip, self.take, self.note, self.mode = new, "", "", "", "pick"
            return "updated"
        if lk == "k" and self.label:
            self.conf_mode = True
            return "updated"
        if self.label == "SKIP" and k in S.SKIP_REASONS:
            self.skip = k
            if k == "7":
                self.mode = "note"
            return "updated"
        if self.label == "TAKE" and k.upper() in S.TAKE_REASONS and k.isalpha():
            self.take = k.upper()
            if self.take == "D":
                self.mode = "note"
            return "updated"
        return "ignored"

    def _commit(self) -> str:
        if not self.label:
            self.message = "Press T or S first."
            return "updated"
        st = self.app.store
        try:
            st.add(st.next_seq, self.label, skip_reason=self.skip, take_reason=self.take, note=self.note,
                   confidence=self.conf, ms=self.decide_ms)
        except LabelError as e:
            self.message = str(e)
            return "updated"
        LG.mark_first_label(self.app.out_dir)
        self.shown()
        return "committed"

    # ---------------------------------------------------------------- text for the window (outside the blind chart)
    def progress_line(self) -> str:
        p = self.app.store.progress()
        s = f"Labelled {p['unique']} of {p['min_unique']} minimum   takes {p['takes']} of {p['min_takes']} minimum"
        if p["enough"]:
            s += "   ENOUGH LABELS - stop whenever you like, nothing is lost"
        return s

    def status_line(self) -> str:
        if self.app.store.done:
            return "Every candidate in the queue is labelled. You can close this window."
        if self.message:
            return self.message
        if not self.label:
            u = "   U undoes your last decision." if self.app.store.can_undo else ""
            return "Press T (take) or S (skip)." + u
        parts = [self.label]
        if self.label == "SKIP":
            parts.append(f"reason {self.skip}" if self.skip else "reason 1-7 (required)")
        elif self.take:
            parts.append(f"reason {self.take}")
        else:
            parts.append("reason A-D (optional)")
        if self.mode == "note":
            parts.append(f"type a few words: {self.note}|")
        if self.conf:
            parts.append(f"confidence {self.conf}")
        if self.conf_mode:
            parts.append("confidence: press 1, 2 or 3")
        if self.label == "TAKE" or self.skip:
            parts.append("Enter to confirm")
        return "  -  ".join(parts)

    @staticmethod
    def legend_lines() -> list[str]:
        sk = [f"{k} {v}" for k, v in S.SKIP_REASONS.items()]
        tk = [f"{k} {v}" for k, v in S.TAKE_REASONS.items()]
        return ["T take   S skip   then a reason key, then Enter   K then 1-3 confidence   U undo last   Esc clear",
                "Skip:  " + "   ".join(sk[:4]), "       " + "   ".join(sk[4:]), "Take (optional):  " + "   ".join(tk)]
