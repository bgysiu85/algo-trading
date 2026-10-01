#!/usr/bin/env python3
"""The matplotlib window. The blind chart is drawn by render.draw_candidate; this adds the status lines (outside the chart)
and routes key presses to the Session. Matplotlib's own key bindings (s = save, k = log scale, q = quit, ...) are switched
off so T / S / K / U mean what the tool says."""
from __future__ import annotations

from strategy.chartmark_clone import render as R
from strategy.chartmark_clone.session import App, Session


class LabelWindow:
    def __init__(self, fig, app: App, session: Session | None = None):
        self.fig, self.app = fig, app
        self.session = session or Session(app)
        self._texts: list = []
        self.cid = fig.canvas.mpl_connect("key_press_event", self.on_key)
        self.redraw()

    def redraw(self) -> None:
        """Draw the candidate on screen (or the finished message) and the status lines."""
        cur = self.app.current()
        if cur is None:
            self.fig.clf()
            self.fig.set_facecolor("white")
        else:
            R.draw_candidate(self.fig, self.app.cd, *cur)
        self._texts = []
        self.update_status(draw=False)
        self.fig.canvas.draw_idle()

    def update_status(self, draw: bool = True) -> None:
        for t in self._texts:
            try:
                t.remove()
            except (ValueError, NotImplementedError):
                pass
        s = self.session
        self._texts = [
            self.fig.text(0.012, 0.118, s.progress_line(), fontsize=9, family="monospace", color="#222222", weight="bold"),
            self.fig.text(0.012, 0.090, s.status_line(), fontsize=10, family="monospace", color="#7a1f2e" if s.message
                          else "#1a5e46", weight="bold"),
        ]
        y = 0.062
        for line in s.legend_lines():
            self._texts.append(self.fig.text(0.012, y, line, fontsize=7.3, family="monospace", color="#555555"))
            y -= 0.0145
        if draw:
            self.fig.canvas.draw_idle()

    def on_key(self, event) -> None:
        res = self.session.key(getattr(event, "key", None))
        if res in ("committed", "undone"):
            self.redraw()
        elif res == "updated":
            self.update_status()


def run(app: App) -> None:
    import matplotlib
    import matplotlib.pyplot as plt

    for k in [k for k in matplotlib.rcParams if k.startswith("keymap.")]:
        matplotlib.rcParams[k] = []                                # no built-in shortcuts: T / S / K / U are ours
    fig = plt.figure(figsize=R.FIGSIZE, dpi=R.DPI)
    try:
        fig.canvas.manager.set_window_title("Label")
    except AttributeError:
        pass
    win = LabelWindow(fig, app)                                    # noqa: F841  (keeps the key handler alive)
    plt.show()
