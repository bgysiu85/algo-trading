"""Telegram notifications: formatting, rate limiting, and above all fail-safety.

No network anywhere in here. The transport is one small method (_post) so
everything with a decision in it is testable offline.

The rule these tests exist to defend, from claude/messaging_alert_channels.md
and from the fact that MCL's trailing stop lives inside the running process:
**a notification must never be able to affect trading.** Outside RTH there is
no broker-side stop, so a send that blocks the event loop or raises into it
can leave a position unprotected. Every failure mode below therefore asserts
that the caller is unharmed, not merely that the message was correct.
"""
from __future__ import annotations

import time
from datetime import datetime

import pytest

from common import notify as N


def row(ticker="AOUT", chg=27.47, px=12.76, relvol=65.46, flt=10_589_237.0):
    return {"ticker": ticker, "premarket_change": chg, "premarket_close": px,
            "relative_volume_10d_calc": relvol, "float_shares_outstanding": flt}


NOW = datetime(2026, 9, 8, 7, 15, 0, tzinfo=N.ET)

# A structurally valid but fake token. The earlier placeholder here was "t",
# which the format check added after the 2026-09-05 leak now (correctly)
# refuses -- a notifier that cannot possibly work must not start.
TOKEN = "1234567890:AAFtesttesttesttesttesttesttesttest"
CHAT = "1234567890"


# --- unconfigured is a normal state ----------------------------------------

def test_unconfigured_notifier_is_a_silent_no_op():
    """Not having set a token must never stop a session from trading."""
    n = N.Notifier()
    assert n.enabled is False
    assert n.send("anything") is False
    assert n._thread is None, "an unconfigured notifier must not spawn a thread"
    n.flush()


def test_partial_configuration_counts_as_unconfigured():
    assert N.Notifier(token="abc").enabled is False
    assert N.Notifier(chat_id="123").enabled is False


# --- fail-safety: the point of the whole design ----------------------------

def test_a_failing_transport_never_raises_into_the_caller(monkeypatch):
    n = N.Notifier(TOKEN, CHAT)
    monkeypatch.setattr(n, "_post",
                        lambda text: (_ for _ in ()).throw(OSError("network")))
    for i in range(5):
        n.send(f"msg {i}", force=True)
    n.flush(timeout=3.0)
    assert n.failed >= 1
    assert n.sent == 0


def test_the_sender_thread_survives_an_exception_urllib_would_not_wrap(monkeypatch):
    """The drain loop catches broadly on purpose: if the thread dies, every
    later notification is lost silently for the rest of the session."""
    n = N.Notifier(TOKEN, CHAT)
    calls = []

    def boom(text):
        calls.append(text)
        if len(calls) == 1:
            raise KeyboardInterrupt("something exotic")

    monkeypatch.setattr(n, "_post", boom)
    n.send("first", force=True)
    n.flush(timeout=3.0)
    n.send("second", force=True)
    n.flush(timeout=3.0)
    assert calls == ["first", "second"], "the thread stopped after one failure"


def test_a_full_queue_drops_rather_than_blocking(monkeypatch):
    """The caller is an asyncio trading loop. Blocking it is the failure this
    guards: a dropped alert is an annoyance, a stalled trader is a loss."""
    n = N.Notifier(TOKEN, CHAT)
    monkeypatch.setattr(n, "_post", lambda text: time.sleep(60))
    t0 = time.monotonic()
    for i in range(N.QUEUE_MAX + 50):
        n.send(f"m{i}", force=True)
    assert time.monotonic() - t0 < 2.0, "send() blocked the caller"
    assert n.dropped > 0


# --- rate limiting and de-duplication --------------------------------------

def test_identical_messages_are_suppressed_inside_the_window(monkeypatch):
    n = N.Notifier(TOKEN, CHAT)
    monkeypatch.setattr(n, "_post", lambda text: None)
    assert n.send("same") is True
    assert n.send("same") is False
    assert n.suppressed == 1


def test_a_burst_of_different_messages_is_rate_limited(monkeypatch):
    """The screener-bug case the guidance calls out: fifty alerts in a minute
    gets the channel muted, which is worse than no alerts."""
    n = N.Notifier(TOKEN, CHAT)
    monkeypatch.setattr(n, "_post", lambda text: None)
    queued = sum(1 for i in range(50) if n.send(f"different {i}"))
    assert queued == 1
    assert n.suppressed == 49


def test_force_bypasses_both_guards(monkeypatch):
    """Fills and the heartbeat must never be swallowed -- a suppressed fill is
    a trade you do not know happened, and a suppressed heartbeat makes a dead
    feed look like a quiet market."""
    n = N.Notifier(TOKEN, CHAT)
    monkeypatch.setattr(n, "_post", lambda text: None)
    assert all(n.send("identical fill", force=True) for _ in range(5))
    assert n.suppressed == 0


# --- message content -------------------------------------------------------

def test_watchlist_message_carries_the_trigger_values():
    """"AAPL long" tells you nothing three hours later" -- the readings have to
    be in the message or the alert is unreconstructable on a phone."""
    msg = N.watchlist_change(["AOUT"], ["OLD"], ["AOUT"], ["PRICEY"], ["OLD"],
                             now=NOW, rows=[row()])
    assert "AOUT" in msg and "OLD" in msg and "PRICEY" in msg
    assert "+27.5%" in msg and "$12.76" in msg
    assert "relvol 65.5" in msg
    assert "10,589,237" in msg
    assert "07:15:00 ET" in msg, "every alert needs an explicit timezone"


def test_watchlist_message_survives_missing_fields():
    """A screener row with a null column must not blow up the notifier and
    take the send thread with it."""
    msg = N.watchlist_change(["X"], [], ["X"], [], [], now=NOW,
                             rows=[{"ticker": "X", "premarket_change": None,
                                    "premarket_close": None}])
    assert "X" in msg and "?" in msg


def test_all_three_tiers_are_always_shown_even_when_empty():
    msg = N.watchlist_change([], ["A"], [], [], ["A"], now=NOW)
    assert "HOT (0)" in msg and "WARM (0)" in msg and "COLD (1)" in msg


def test_fill_messages_name_the_strategy():
    """With MCL, MC5 and VW9 in the repo, a fill on a phone has to say which
    one fired it."""
    assert N.buy_filled("AOUT", 12.76, 100, 0.35, now=NOW,
                        strategy="MCL").startswith("<b>MCL · BUY AOUT</b>")
    assert N.sell_filled("AOUT", 13.4, 100, 0.35, 63.3, now=NOW,
                         strategy="VW9").startswith("<b>VW9 · SELL AOUT</b>")


def test_an_unknown_strategy_is_left_blank_not_guessed():
    """A fill labelled with the WRONG strategy is worse than one labelled with
    none, so there is no default."""
    assert N.buy_filled("A", 1.0, 1, 0.1, now=NOW).startswith("<b>BUY A</b>")


def test_the_trader_reads_the_name_from_its_strategy_module():
    """Not hard-coded in the trader: a second trader must not inherit the
    first one's label."""
    from brokers.ibkr import trader as M
    from strategy.mcl import mcl as S
    assert M.STRATEGY_NAME == S.STRATEGY_NAME == "MCL"


def test_every_strategy_module_names_itself():
    from strategy.mcl import mcl
    from strategy.mc5 import mc5
    from strategy.vw9 import backtest as vw9
    names = {mcl.STRATEGY_NAME, mc5.STRATEGY_NAME, vw9.STRATEGY_NAME}
    assert names == {"MCL", "MC5", "VW9"}, "names must be distinct per strategy"


def test_buy_message_totals_add_up():
    msg = N.buy_filled("AOUT", 12.76, 100, 0.35, now=NOW)
    assert "$1,276.00" in msg          # cost
    assert "$0.35" in msg              # commission
    assert "$1,276.35" in msg          # total = cost + commission


def test_sell_message_shows_proceeds_and_round_trip_net():
    msg = N.sell_filled("AOUT", 13.40, 100, 0.35, 63.30, now=NOW)
    assert "$1,340.00" in msg          # proceeds
    assert "$0.35" in msg
    assert "$63.30" in msg
    assert "this leg" in msg and "round trip" in msg, (
        "the two commission figures must be distinguishable or the message "
        "reads as double counting")


def test_a_losing_sell_is_visually_distinct():
    win = N.sell_filled("A", 10.0, 100, 0.35, 50.0, now=NOW)
    lose = N.sell_filled("A", 10.0, 100, 0.35, -50.0, now=NOW)
    assert win != lose
    assert "-$50.00" in lose or "$-50.00" in lose


def test_heartbeat_states_that_the_feed_is_alive():
    msg = N.heartbeat(12, 3, 2, 7, stats="telegram sent=4", now=NOW)
    assert "alive" in msg and "07:15:00 ET" in msg
    assert "12" in msg


# --- the trader wiring -----------------------------------------------------

def test_trader_defaults_to_a_disabled_notifier():
    """Constructing a trader in a test or a dry run must not resolve
    credentials or start a thread."""
    from brokers.ibkr import trader as M
    assert M.MCLPaperTrader.__init__.__defaults__[-1] is None


@pytest.mark.parametrize("action", ["BUY", "SELL"])
def test_notify_fill_cannot_raise_into_the_trading_path(action, monkeypatch):
    from brokers.ibkr import trader as M

    class Exploding:
        enabled = True

        def send(self, *a, **k):
            raise RuntimeError("telegram exploded")

    tr = M.MCLPaperTrader.__new__(M.MCLPaperTrader)
    tr.tg = Exploding()
    # Must return normally. If this raises, a fill has just been placed and
    # the exception unwinds through the order path.
    tr.notify_fill("AAA", action, 5.0, 100, {"trade_pnl": 12.34})


# --- the 2026-09-05 incident: a live token reached a chat window -----------
#
# The chain: BotFather presents the token inside a sentence, so the value that
# got pasted was "API: <token>"; the space made an invalid URL; urllib put the
# WHOLE URL -- token included -- in its exception message; the notifier logged
# that verbatim; the log was pasted into a chat. Four links, each individually
# reasonable. These tests break the two that are this module's fault.

def test_a_malformed_token_is_refused_at_construction():
    n = N.Notifier("API: 8743043831:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                   "1234567890")
    assert n.enabled is False
    assert n.problems and "not a valid Telegram bot token" in n.problems[0]
    assert "label" in n.problems[0], "the message must name the actual cause"


def test_a_valid_token_is_accepted():
    n = N.Notifier("8743043831:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                   "1234567890")
    assert n.enabled is True and n.problems == []


def test_surrounding_whitespace_is_stripped_not_rejected():
    n = N.Notifier("  8743043831:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n",
                   " 1234567890 ")
    assert n.enabled is True


def test_a_phone_number_in_the_chat_id_is_caught():
    """No Telegram chat id starts with 0. A 10-digit value beginning 04 is an
    Australian mobile, and would otherwise fail as an opaque 'chat not found'
    only once a real alert fired."""
    n = N.Notifier("8743043831:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "0427963107")
    assert n.enabled is False
    assert "phone number" in n.problems[0]


def test_the_token_can_never_reach_a_log(monkeypatch, caplog):
    """The link that actually leaked. urllib's InvalidURL message contains the
    full request URL, and the URL contains the token."""
    secret = "8743043831:AAFsecretsecretsecretsecretsecret"
    n = N.Notifier(secret, "1234567890")

    def leaky(text):
        raise ValueError(f"URL can't contain control characters. "
                         f"'/bot{secret}/sendMessage'")

    monkeypatch.setattr(n, "_post", leaky)
    with caplog.at_level("WARNING"):
        n.send("x", force=True)
        n.flush(timeout=3.0)
    logged = caplog.text
    assert secret not in logged, "the bot token was written to the log"
    assert "<TOKEN>" in logged
    assert "AAFsecretsecretsecretsecretsecret" not in logged


def test_scrub_catches_the_secret_half_on_its_own():
    """Even if only the part after the colon appears, it is still the secret."""
    n = N.Notifier("8743043831:AAFsecretsecretsecretsecretsecret", "1")
    out = n._scrub("something AAFsecretsecretsecretsecretsecret leaked")
    assert "AAFsecret" not in out
