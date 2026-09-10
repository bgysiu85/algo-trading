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

import re

import pytest

from common import notify as N


def row(ticker="AOUT", chg=27.47, px=12.76, relvol=65.46, flt=10_589_237.0,
        pmvol=271_202.0):
    return {"ticker": ticker, "premarket_change": chg, "premarket_close": px,
            "premarket_volume": pmvol,
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
    assert "float 10.6m" in msg, "float in k/m, not raw shares (Ben, 09-09)"
    assert "pm vol 271k" in msg, (
        "same label as the drop reason uses for the same column -- two "
        "spellings of one metric is how a reader ends up asking what it is")
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
                        strategy="MCL").splitlines()[1] == "<b>MCL</b>"
    assert N.sell_filled("AOUT", 13.4, 100, 0.35, 63.3, now=NOW,
                         strategy="VW9").splitlines()[1] == "<b>VW9</b>"


def test_an_unknown_strategy_is_left_blank_not_guessed():
    """A fill labelled with the WRONG strategy is worse than one labelled with
    none, so there is no default."""
    lines = N.buy_filled("A", 1.0, 1, 0.1, now=NOW).splitlines()
    assert lines[1] == "<b>BUY A</b>", (
        "no strategy means NO line, not a blank one -- an empty line reads as "
        "a rendering fault")


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
    assert "alive" in msg and "(07:15 ET)" in msg
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


# --- the 2026-09-09 message changes ----------------------------------------

def test_the_first_line_is_the_day_date_and_both_clocks():
    """Ben's format, 2026-09-09: 'Monday 7 Sep 2026 18:30'. He chose local +
    ET after it, so a message can be lined up against the fill CSV (ET) as
    well as read off a phone (AEST/AEDT)."""
    monday = datetime(2026, 9, 7, 4, 30, tzinfo=N.ET)
    assert N.header(monday) == "Monday 7 Sep 2026 18:30 AEST (04:30 ET)"


def test_the_day_number_has_no_leading_zero():
    """%-d is Linux-only and %#d is Windows-only; this runs on Windows."""
    assert N.header(datetime(2026, 9, 7, 4, 30, tzinfo=N.ET)).startswith(
        "Monday 7 Sep")


def test_the_header_tracks_australian_daylight_saving_not_a_fixed_offset():
    """AEST and AEDT sit 14 and 16 hours from ET, and the two countries change
    over on different weekends. A fixed offset is wrong for weeks each year."""
    sep = N.header(datetime(2026, 9, 7, 4, 30, tzinfo=N.ET))
    jan = N.header(datetime(2026, 1, 15, 4, 30, tzinfo=N.ET))
    assert "18:30 AEST" in sep
    assert "20:30 AEDT" in jan
    assert "(04:30 ET)" in sep and "(04:30 ET)" in jan


def test_every_message_type_carries_the_header():
    for msg in (N.buy_filled("A", 1.0, 100, 0.35, now=NOW, strategy="MCL"),
                N.sell_filled("A", 1.0, 100, 0.35, 1.0, now=NOW, strategy="MCL"),
                N.watchlist_change(["A"], [], ["A"], [], [], now=NOW),
                N.heartbeat(1, 1, 0, 0, now=NOW)):
        assert msg.splitlines()[0] == N.header(NOW)


def test_the_strategy_and_the_side_are_on_separate_lines():
    """Ben, 2026-09-09 (second revision): strategy on its own line, side and
    ticker on the next. The ticker stays with the side -- his example shows
    "BUY WYHG" together, and a fill without the symbol is not a fill."""
    buy = N.buy_filled("WYHG", 5.82, 100, 0.35, now=NOW, strategy="MCL")
    assert buy.splitlines()[:3] == [N.header(NOW), "<b>MCL</b>",
                                    "<b>BUY WYHG</b>"]
    sell = N.sell_filled("WYHG", 5.43, 100, 0.35, -40.37, now=NOW,
                         strategy="MCL")
    assert sell.splitlines()[:3] == [N.header(NOW), "<b>MCL</b>",
                                     "<b>SELL WYHG</b>"]


def test_an_order_message_never_contains_a_blank_line():
    """Every line carries a value. A blank one is how a missing field looks."""
    for msg in (N.buy_filled("A", 1.0, 1, 0.1, now=NOW, strategy="MCL"),
                N.buy_filled("A", 1.0, 1, 0.1, now=NOW),
                N.sell_filled("A", 1.0, 1, 0.1, 0.5, now=NOW, strategy="MC5"),
                N.sell_filled("A", 1.0, 1, 0.1, 0.5, now=NOW)):
        assert "" not in msg.splitlines()


def test_share_counts_are_abbreviated_and_money_never_is():
    """A P/L rounded to '1.3k' on a phone cannot be reconciled against the
    fill log, so _money stays exact."""
    assert N._kmb(9_318_299) == "9.3m"
    assert N._kmb(271_202) == "271k"
    assert N._kmb(934) == "934"
    assert N._kmb(None) == "?"
    assert N._kmb(-2_500_000) == "-2.5m"
    assert N._money(1_300.0) == "$1,300.00"
    assert "$1,300.00" in N.sell_filled("A", 13.0, 100, 0.35, 1_300.0, now=NOW)


def test_a_drop_reason_names_the_clause_the_value_and_the_threshold():
    from common.tv_screener import failing_clauses
    why = N.drop_reason(failing_clauses(
        {"premarket_change": 25.0, "premarket_close": 8.0,
         "premarket_volume": 62_000.0}))
    assert why == "pm vol 62k < 100k"


def test_a_drop_reason_reports_every_failing_clause_not_just_the_first():
    from common.tv_screener import failing_clauses
    why = N.drop_reason(failing_clauses(
        {"premarket_change": 4.0, "premarket_close": 41.0,
         "premarket_volume": 62_000.0}))
    assert "pm chg" in why and "price" in why and "pm vol" in why


def test_no_reason_is_reported_rather_than_a_guessed_one():
    """The lookup that finds the reason is a separate request and can fail. A
    guessed cause would be exactly the plausible-looking wrong number this
    project keeps finding weeks later."""
    assert N.drop_reason([], fallback="") == ""
    msg = N.watchlist_change([], ["GONE"], [], [], ["GONE"], now=NOW,
                             reasons={})
    assert "GONE" in msg and "—" not in msg.split("no longer screening:")[1].split("\n")[1]


def test_a_reason_reaches_the_message_when_there_is_one():
    msg = N.watchlist_change([], ["GONE"], [], [], ["GONE"], now=NOW,
                             reasons={"GONE": "pm vol 62k < 100k"})
    # Escaped, because the message is sent with parse_mode=HTML and a bare
    # "<" is what made Telegram reject the whole thing on 2026-09-09.
    assert "GONE  —  pm vol 62k &lt; 100k" in msg


# --- Telegram HTML safety (the 2026-09-09 HTTP 400) -------------------------

ALLOWED_TAGS = re.compile(
    r"</?(b|strong|i|em|u|ins|s|strike|del|a|code|pre|blockquote|tg-spoiler)"
    r"(\s[^<>]*)?>")


def telegram_html_ok(msg: str) -> bool:
    """Would Telegram's HTML parser accept this?

    Its rule is narrow: only a listed set of tags, and every other '<' or '&'
    must be escaped. Anything else is HTTP 400 for the WHOLE message -- not a
    stripped tag, a refusal.
    """
    stripped = ALLOWED_TAGS.sub("", msg)
    if "<" in stripped or ">" in stripped:
        return False
    # An '&' that is not the start of an entity is also a parse error.
    return re.search(r"&(?!(amp|lt|gt|quot|#\d+);)", stripped) is None


def test_the_message_that_caused_the_http_400_is_now_accepted():
    """REGRESSION. drop_reason renders "pm vol 62k < 100k"; sent as HTML that
    is an unclosed tag, and Telegram refused the whole message. Fills kept
    arriving and the watchlist alert died silently -- the message reporting
    that something disappeared was the one that disappeared."""
    msg = N.watchlist_change(["AOUT"], ["OLDNAME"], ["AOUT"], [], ["OLDNAME"],
                             now=NOW, rows=[row()],
                             reasons={"OLDNAME": "pm vol 62k < 100k"})
    assert telegram_html_ok(msg), msg


def test_no_message_this_module_builds_can_be_refused_as_html():
    """The general guard, not just the one case. Every builder, with values
    chosen to break an HTML parser."""
    nasty = "A<B>&C"
    messages = [
        N.buy_filled(nasty, 1.0, 1, 0.1, now=NOW, strategy=nasty),
        N.sell_filled(nasty, 1.0, 1, 0.1, -1.0, now=NOW, strategy=nasty),
        N.heartbeat(1, 1, 0, 0, stats=nasty, now=NOW),
        N.watchlist_change([nasty], [nasty], [nasty], [nasty], [nasty],
                           now=NOW,
                           rows=[{"ticker": nasty, "premarket_change": 1.0,
                                  "premarket_close": 2.0,
                                  "premarket_volume": 3.0,
                                  "relative_volume_10d_calc": 4.0,
                                  "float_shares_outstanding": 5.0}],
                           reasons={nasty: "pm vol 1k < 100k & falling"}),
    ]
    for msg in messages:
        assert telegram_html_ok(msg), msg


def test_the_guard_itself_rejects_what_telegram_rejects():
    """A checker that passes everything proves nothing."""
    assert telegram_html_ok("<b>fine</b>")
    assert not telegram_html_ok("pm vol 62k < 100k")
    assert not telegram_html_ok("a & b")
    assert telegram_html_ok("a &amp; b")


# --- batching ---------------------------------------------------------------
# Ben, 2026-09-10: "an option where the messages will be sent in batches in
# specified intervals, such as every 15 mins or 30 mins".
#
# The safety property is the one worth defending: batching must never delay a
# fill. His machine restarted mid-session the night before, and anything
# sitting in a batch at that moment is gone.

def sent_texts(monkeypatch, n):
    got = []
    monkeypatch.setattr(n, "_post", got.append)
    return got


def test_batching_holds_ordinary_messages_instead_of_sending_them(monkeypatch):
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    got = sent_texts(monkeypatch, n)
    assert n.send("one") is True and n.send("two") is True
    time.sleep(0.1)
    assert got == [], "nothing should have gone out yet"
    assert n._batched == 2


@pytest.mark.parametrize("msg", [
    N.buy_filled("AOUT", 12.76, 100, 0.35, strategy="MCL"),
    N.sell_filled("AOUT", 13.40, 100, 0.35, 63.30, strategy="MCL"),
    N.heartbeat(40, 3, 1, 0, stats="x"),
])
def test_batching_holds_every_kind_of_message_including_fills(msg, monkeypatch):
    """Ben, 2026-09-10: batch the Telegram messages, all of them. Batching
    delays the NOTIFICATION and nothing else -- the order is placed, filled
    and managed by the trader either way, and this queue sits downstream of
    all of it. Asserted through the real formatters so a fill cannot quietly
    acquire an exemption."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    got = sent_texts(monkeypatch, n)
    n.send(msg, force=True)
    time.sleep(0.2)
    assert got == [], "nothing goes out until the interval"
    assert len(n._pending) == 1


def test_force_still_bypasses_the_two_guards_while_batching(monkeypatch):
    """`force` keeps its original meaning -- skip the rate limit and the
    de-duplicator -- and simply no longer decides what waits."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    sent_texts(monkeypatch, n)
    n.send("same", force=True)
    n.send("same", force=True)
    assert n.suppressed == 0
    assert len(n._pending) == 2


def test_the_batch_goes_out_on_the_interval(monkeypatch):
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=0.15)
    got = sent_texts(monkeypatch, n)
    n.send("one")
    n.send("two")
    time.sleep(0.6)
    assert len(got) == 1, "both parts arrive as ONE message"
    assert "one" in got[0] and "two" in got[0]


def test_flush_sends_the_pending_batch_before_shutting_down(monkeypatch):
    """Ending a session on a 30-minute cadence would otherwise discard most of
    the last half hour."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    got = sent_texts(monkeypatch, n)
    n.send("held")
    n.flush(timeout=2.0)
    assert got and "held" in got[0]


def test_batching_off_by_default_is_the_old_behaviour(monkeypatch):
    n = N.Notifier(TOKEN, CHAT)
    got = sent_texts(monkeypatch, n)
    n.send("straight through")
    time.sleep(0.2)
    assert got == ["straight through"]


# --- the 4096-character limit -----------------------------------------------

def test_a_batch_is_split_to_fit_telegrams_limit():
    """A message over 4096 chars is REFUSED WHOLE, not truncated -- so without
    splitting, one busy interval loses every message in it and the failure
    looks like a quiet market."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    parts = ["x" * 1000] * 10
    chunks = n._chunks(parts)
    assert len(chunks) > 1
    assert all(len(c) <= N.TELEGRAM_MAX_CHARS for c in chunks)


def test_splitting_loses_nothing():
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    parts = [f"part{i}" for i in range(200)]
    joined = "".join(n._chunks(parts))
    for p in parts:
        assert p in joined


def test_a_single_oversized_part_is_passed_through_rather_than_cut():
    """Cutting mid-tag produces invalid HTML, which Telegram refuses anyway.
    Splitting one message is a formatting decision for the caller."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    big = "y" * (N.TELEGRAM_MAX_CHARS + 500)
    assert n._chunks([big]) == [big]


def test_a_small_batch_stays_one_message():
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    assert len(n._chunks(["a", "b", "c"])) == 1


# --- which guard applies while batching -------------------------------------

def test_the_rate_limit_is_skipped_while_batching(monkeypatch):
    """The interval exists so a burst cannot hit Telegram's API limits, which
    batching already solves. Enforcing both would throw most of a batch away
    before it was assembled -- making a digest QUIETER than sending live."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    sent_texts(monkeypatch, n)
    for i in range(5):
        assert n.send(f"burst {i}") is True
    assert n.suppressed == 0
    assert len(n._pending) == 5


def test_the_de_duplicator_still_applies_while_batching(monkeypatch):
    """A stuck loop repeating one message is exactly what a batch would
    otherwise pile up unseen."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=3600)
    sent_texts(monkeypatch, n)
    n.send("same")
    n.send("same")
    assert n.suppressed == 1
    assert len(n._pending) == 1


def test_stats_reports_what_is_waiting(monkeypatch):
    """Silence on a 30-minute cadence is ambiguous; the count disambiguates."""
    n = N.Notifier(TOKEN, CHAT, batch_interval_s=1800)
    sent_texts(monkeypatch, n)
    n.send("held")
    s = n.stats()
    assert "batched=1" in s and "waiting=1" in s and "every=1800s" in s


def test_stats_says_nothing_about_batching_when_it_is_off():
    assert "batched" not in N.Notifier(TOKEN, CHAT).stats()


# --- the end-of-session summary ---------------------------------------------
# Ben, 2026-09-10: "a summary ... at the end of the trading session ... the P&L
# of every trade made - Time, share size, buy/sell prices, gross profit,
# commission, net profit ... Total of all the trades".

def sell_row(symbol="BNC", entry=5.41, exit_=5.26, qty=100, pnl=None,
             ts="2026-09-09 07:45:38", status="FILLED", hold="82.8"):
    if pnl is None:
        from common.commissions import order_cost
        pnl = ((exit_ - entry) * qty
               - order_cost(qty, entry, False, "ibkr_tiered")
               - order_cost(qty, exit_, True, "ibkr_tiered"))
    return {"ts_et": ts, "strategy": "MCL", "symbol": symbol, "action": "SELL",
            "reason": "trailing_stop", "status": status,
            "filled_qty": str(qty), "qty": str(qty),
            "entry_price": str(entry), "exit_price": str(exit_),
            "trade_pnl": f"{pnl:.2f}", "hold_minutes": hold}


def buy_row(symbol="BNC", ts="2026-09-09 06:23:01", status="FILLED"):
    return {"ts_et": ts, "strategy": "MCL", "symbol": symbol, "action": "BUY",
            "reason": "entry_signal", "status": status, "filled_qty": "100",
            "qty": "100", "fill_price": "5.41"}


def test_a_round_trip_is_read_off_the_sell_row():
    """The log writes entry, exit and P/L on the sell row only, so a sell row
    IS a completed trade and a lone buy row is an open position."""
    got = N._round_trips([buy_row(), sell_row()])
    assert len(got) == 1
    t = got[0]
    assert t["symbol"] == "BNC" and t["qty"] == 100
    assert t["gross"] == pytest.approx(-15.00)
    assert t["net"] == pytest.approx(t["gross"] - t["commission"])


def test_every_field_ben_asked_for_is_in_the_message():
    text = N.session_summary([buy_row(), sell_row()], now=NOW, strategy="MCL")
    assert "07:45" in text                      # time
    assert "100 sh" in text                     # share size
    assert "$5.41" in text and "$5.26" in text   # buy / sell prices
    assert "gross" in text and "comm" in text and "net" in text


def test_the_totals_are_the_sum_of_the_rows():
    rows = [sell_row("AAA", 10.00, 11.00), sell_row("BBB", 5.00, 4.50)]
    text = N.session_summary(rows, now=NOW)
    trades = N._round_trips(rows)
    assert f"{sum(t['gross'] for t in trades):,.2f}" in text.replace("$", "")
    assert "2 trade(s)   1 up / 1 down" in text


def test_a_trade_that_does_not_reconcile_is_flagged_not_printed_quietly():
    """THE CHECK THAT MAKES THIS TRUSTWORTHY. Commission is not in the log, so
    it is recomputed -- and then verified against the log's own trade_pnl. A
    summary that silently disagreed with the ledger would be worse than none."""
    bad = sell_row(pnl=999.99)
    assert N._round_trips([bad])[0]["reconciles"] is False
    text = N.session_summary([bad], now=NOW)
    assert "do not reconcile" in text and "⚠️" in text


def test_a_reconciling_session_carries_no_warning():
    text = N.session_summary([sell_row()], now=NOW)
    assert "do not reconcile" not in text


def test_an_unclosed_position_is_called_out():
    """A total that silently covers only closed trades, on a session still
    holding something, is a wrong number presented as a right one."""
    text = N.session_summary([buy_row("AAA"), buy_row("BBB"), sell_row("AAA")],
                             now=NOW)
    assert "still open" in text


def test_a_session_with_no_round_trips_says_so():
    text = N.session_summary([buy_row()], now=NOW)
    assert "no completed round trips" in text
    assert "opened and not closed" in text


def test_rows_that_never_filled_are_not_trades():
    """The log records rejects and cap-skips too. Scoring one as a trade would
    invent P/L from a position that never existed."""
    skipped = dict(buy_row(), status="SKIPPED_CONCURRENCY_CAP")
    assert N._round_trips([skipped, dict(sell_row(), status="CANCELLED")]) == []


def test_a_malformed_row_is_skipped_rather_than_crashing_the_summary():
    """This runs at session end. A summary that raises loses the whole
    report over one bad row."""
    junk = dict(sell_row(), entry_price="", trade_pnl="oops")
    assert N._round_trips([junk, sell_row()]) == N._round_trips([sell_row()])


def test_read_fills_treats_a_missing_file_as_empty(tmp_path):
    """A session that placed no orders never creates the file."""
    assert N.read_fills(tmp_path / "nope.csv") == []


def test_the_summary_escapes_what_it_interpolates():
    """A bare '<' in HTML parse mode is rejected for the WHOLE message -- the
    2026-09-09 defect, arriving through a new door."""
    text = N.session_summary([sell_row(symbol="A<B")], now=NOW)
    assert "A<B" not in text and "&lt;" in text


def test_a_buy_row_is_not_a_round_trip_even_if_it_carries_pl_fields():
    """The SELL guard, tested for what it MEANS rather than incidentally.
    Buy rows are currently excluded anyway because they have no entry/exit
    columns — so the guard looks redundant until the schema changes. A
    scale-out or a partial fill that populated those fields on the buy leg
    would otherwise double-count the trade."""
    odd = dict(buy_row(), entry_price="5.41", exit_price="5.26",
               trade_pnl="-16.37")
    assert N._round_trips([odd]) == []
    assert len(N._round_trips([odd, sell_row()])) == 1


# --- configured from the environment, not from the trader -------------------
# Ben, 2026-09-10: keep it out of the trader entirely.

def test_batching_is_off_when_the_variable_is_unset(monkeypatch):
    monkeypatch.delenv(N.BATCH_VAR, raising=False)
    assert N.Notifier.batch_from_env() == 0.0


@pytest.mark.parametrize("raw,secs", [("15", 900.0), ("30", 1800.0),
                                      ("0.5", 30.0)])
def test_the_variable_is_read_in_minutes(raw, secs, monkeypatch):
    """Ben asked for '15 mins or 30 mins'. Seconds would make 15 a quarter of
    a minute and the mistake would look like batching not working."""
    monkeypatch.setenv(N.BATCH_VAR, raw)
    assert N.Notifier.batch_from_env() == secs


@pytest.mark.parametrize("raw", ["", "   ", "0", "-5"])
def test_blank_or_non_positive_means_off(raw, monkeypatch):
    monkeypatch.setenv(N.BATCH_VAR, raw)
    assert N.Notifier.batch_from_env() == 0.0


def test_a_typo_stays_off_and_says_so(monkeypatch, caplog):
    """Silently holding every message for an hour because of a mistyped value
    is the worst reading of an ambiguous setting."""
    monkeypatch.setenv(N.BATCH_VAR, "fifteen")
    with caplog.at_level("WARNING"):
        assert N.Notifier.batch_from_env() == 0.0
    assert N.BATCH_VAR in caplog.text


def test_from_env_still_works_with_no_argument():
    """A caller that does not offer the flag must not have to pass anything:
    the environment decides and the call site is unchanged. (An earlier
    version of this test asserted from_env took NO argument at all; Ben asked
    for a command-line parameter on 2026-09-10, which reverses that.)"""
    import inspect
    sig = inspect.signature(N.Notifier.from_env)
    assert sig.parameters["batch_min"].default is None


def test_from_env_actually_applies_the_variable(monkeypatch):
    """THE TEST THE FEATURE HANGS ON. Reading the variable correctly and then
    not passing it to the Notifier leaves batching silently off, and the only
    symptom is messages arriving immediately -- which looks exactly like not
    having set it."""
    monkeypatch.setattr(N.S, "preload_optional",
                        lambda spec: {N.TOKEN_VAR, N.CHAT_VAR})
    monkeypatch.setattr(N.S, "get",
                        lambda k: TOKEN if k == N.TOKEN_VAR else CHAT)
    monkeypatch.setenv(N.BATCH_VAR, "15")
    assert N.Notifier.from_env().batch_interval_s == 900.0

    monkeypatch.delenv(N.BATCH_VAR)
    assert N.Notifier.from_env().batch_interval_s == 0.0


# --- the flag, Ben 2026-09-10 -----------------------------------------------
# "can it be a parameter passed into the program rather than an environment
# variable?" Both, with the flag winning: PowerShell environment variables have
# to be re-set in every new terminal, which is a trap for a setting whose only
# failure symptom is messages not arriving.

def parser_with_flag():
    import argparse
    ap = argparse.ArgumentParser()
    N.add_batch_arg(ap)
    return ap


def test_not_passing_the_flag_leaves_the_environment_in_charge(monkeypatch):
    monkeypatch.setenv(N.BATCH_VAR, "30")
    a = parser_with_flag().parse_args([])
    assert a.telegram_batch_min is None
    assert N.Notifier.batch_seconds(a.telegram_batch_min) == 1800.0


def test_the_flag_overrides_the_environment(monkeypatch):
    monkeypatch.setenv(N.BATCH_VAR, "30")
    a = parser_with_flag().parse_args(["--telegram-batch-min", "15"])
    assert N.Notifier.batch_seconds(a.telegram_batch_min) == 900.0


def test_passing_zero_turns_batching_off_against_the_environment(monkeypatch):
    """Given-and-zero must beat the environment. Otherwise a run that meant to
    disable batching silently inherits it, and the only symptom is messages
    not arriving — which reads as a broken notifier, not a setting."""
    monkeypatch.setenv(N.BATCH_VAR, "30")
    a = parser_with_flag().parse_args(["--telegram-batch-min", "0"])
    assert N.Notifier.batch_seconds(a.telegram_batch_min) == 0.0


def test_the_flag_is_in_minutes():
    a = parser_with_flag().parse_args(["--telegram-batch-min", "15"])
    assert a.telegram_batch_min == 15.0
    assert N.Notifier.batch_seconds(15.0) == 900.0


def test_a_negative_flag_means_off_rather_than_a_negative_interval():
    assert N.Notifier.batch_seconds(-5) == 0.0


@pytest.mark.parametrize("module", ["brokers.ibkr.trader", "common.tv_feed"])
def test_both_senders_accept_the_flag(module):
    """One shared helper rather than a copy per program: two copies of a
    numeric option are two chances for one to end up in seconds.

    Read off each program's REAL parser. tv_feed built its inside main(), so
    it grew a build_parser() to be checkable -- the same shape trader.py and
    history_probe.py already use, and for the same reason: a test that
    rebuilds the parser is asserting about itself."""
    import importlib
    m = importlib.import_module(module)
    a = m.build_parser().parse_args(["--telegram-batch-min", "15"])
    assert a.telegram_batch_min == 15.0
    assert m.build_parser().parse_args([]).telegram_batch_min is None


def test_from_env_applies_an_explicit_batch_argument(monkeypatch):
    """Accepting the flag and then not forwarding it leaves batching silently
    off — and the only symptom is messages arriving immediately, which looks
    exactly like not having passed it."""
    monkeypatch.setattr(N.S, "preload_optional",
                        lambda spec: {N.TOKEN_VAR, N.CHAT_VAR})
    monkeypatch.setattr(N.S, "get",
                        lambda k: TOKEN if k == N.TOKEN_VAR else CHAT)
    monkeypatch.setenv(N.BATCH_VAR, "30")
    assert N.Notifier.from_env(15).batch_interval_s == 900.0
    assert N.Notifier.from_env(0).batch_interval_s == 0.0
    assert N.Notifier.from_env().batch_interval_s == 1800.0
