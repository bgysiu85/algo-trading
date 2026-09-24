"""tests/common/test_news_events.py

G3 sanity check (REGISTERED_news_events.md §0): the classifier must flag
every event a human already read off the probe's hand-read sample
(claude/raw/w03_0010_news_probe_20260924.txt) as the same type a human
assigned it, and must score the two named false positives (G2a) as NOT flagged.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from common import news_events as N

ET = ZoneInfo("America/New_York")


# --- G2(b): normalization -------------------------------------------------------

def test_normalize_html_entity():
    # the live-websocket sample in the probe: "...Stole Information of &#39;A"
    assert N.normalize_headline("Stole Information of &#39;A") == "Stole Information of 'A"


def test_normalize_unicode_hyphen():
    # DCOY's headline used U+2011 (non-breaking hyphen), not ASCII '-'
    raw = "Decoy Therapeutics Announces 1\u2011For\u20111 2 Reverse Stock Split Effective March 6"
    assert "\u2011" not in N.normalize_headline(raw)


def test_normalize_empty():
    assert N.normalize_headline(None) == ""
    assert N.normalize_headline("") == ""


# --- G2(a): the two named false positives -----------------------------------------

def test_g2a_bundle_offering_not_flagged():
    # GM/PCG, probe sample §3 -- a product bundle, not a securities offering.
    h = ("PG&E And GM Energy Announce Bundle Offering New GM EV Buyers "
        "No-Cost Home Charger, $15 Mon")
    assert N.classify_headline(h) is None


def test_g2a_regained_compliance_not_flagged():
    # IMCC, probe sample §3 -- the OPPOSITE of a new deficiency notice.
    h = ("IM Cannabis Says It Received Nasdaq Notice Of Regained Compliance "
        "With Minimum Bid Price R")
    assert N.classify_headline(h) is None


# --- G3: the probe's hand-read headline sample, §3 top-10 ------------------------

def test_g3_headline_sample_section3():
    c = N.classify_headline
    assert c("Viking Therapeutics Stock Drops In After Hours on Proposed Public Offerings") == "OFFERING_PROPOSED"
    assert c("Sequans Communications Receives NYSE Non-Compliance Notice Regarding Market Capitalization") == "DELIST_NOTICE"
    assert c("Granite Point Mortgage Trust Announces 1-For-10 Reverse Stock Split, Effective Oct. 5") == "REVERSE_SPLIT"
    assert c("GMEX Robotics Announces 1-For-9 Reverse Stock Split Effective September 28") == "REVERSE_SPLIT"
    assert c("IM Cannabis Says It Received Nasdaq Notice Of Regained Compliance With Minimum Bid Price R") is None
    assert c("Republic Power Group Announces 1-For-16 Reverse Share Split, Effective September 25") == "REVERSE_SPLIT"
    assert c("Brightline Interactive Announces 1-For-8 Reverse Stock Split, Effective September 28, 2026") == "REVERSE_SPLIT"
    assert c("Maase Announces ~$50M PIPE Agreement For 3,878,856 Shares Priced At $12.89 Per Share") == "OFFERING_PRICED"
    assert c("PG&E And GM Energy Announce Bundle Offering New GM EV Buyers No-Cost Home Charger, $15 Mon") is None
    assert c("Green Circle Decarbonize Technology Announces 1-For-6 Share Consolidation, Effective Octob") == "REVERSE_SPLIT"


def test_g3_headline_sample_section1_per_symbol():
    c = N.classify_headline
    assert c("Wheeler Real Estate Investment Trust Announces 1-For-9 Reverse Stock Split Effec") == "REVERSE_SPLIT"
    assert c("Professional Diversity Network Prices $2M Public Offering Of 7.14M Units At $0.2") == "OFFERING_PRICED"
    assert c("Smartkem Announces 1-For-50 Reverse Stock Split To Support Continued Nasdaq Trad") == "REVERSE_SPLIT"
    # the U+2011 case, run through the real classifier end to end
    assert c("Decoy Therapeutics Announces 1\u2011For\u201112 Reverse Stock Split Effective March 6") == "REVERSE_SPLIT"
    assert c("TNL Mediagene To Implement 1-for-8 Share Consolidation Effective September 8") == "REVERSE_SPLIT"
    assert c("Greenland Mines Prices Its $20M Public Offering Of 4M Shares") == "OFFERING_PRICED"
    assert c("Haoxi Health Technology Announces 1-For-20 Reverse Share Split Effective August") == "REVERSE_SPLIT"
    assert c("KIDZ AI Announces 1-For-15 Reverse Stock Split Of Outstanding Class A And Class") == "REVERSE_SPLIT"


def test_g3_websocket_sample_not_a_false_positive():
    # unrelated news (a data breach story); must not accidentally match anything
    h = "Kash Patel Among Those Exposed: ShinyHunters Says It Hacked FBI Website, Stole Information of &#39;A"
    assert N.classify_headline(h) is None


def test_headline_other_negative():
    assert N.classify_headline("PQR Receives FDA Clearance for Device") is None
    assert N.classify_headline("") is None
    assert N.classify_headline(None) is None


# --- filing classification, §3's exact form/item lists -------------------------

def test_trigger_a_forms():
    for form in ("S-1", "S-1/A", "S-3", "424B4", "424B5", "EFFECT"):
        assert N.classify_filing(form, "") == frozenset({"TRIGGER_A"})


def test_424b3_is_active_shelf_never_trigger_a():
    # §3: "424B3 is excluded from Trigger A" -- WHLR filed 70 in 90 days.
    assert N.classify_filing("424B3", "") == frozenset({"ACTIVE_SHELF_CANDIDATE"})


def test_proxy_forms_are_proposed_rs_never_trigger_b():
    for form in ("DEF 14A", "PRE 14A", "DEFA14A"):
        assert N.classify_filing(form, "") == frozenset({"PROPOSED_RS_CANDIDATE"})
    # PRE 14C / DEF 14C are not in §3's named PROPOSED_RS set at all
    assert N.classify_filing("DEF 14C", "") == frozenset()


def test_8k_item_5_03_is_trigger_b():
    assert N.classify_filing("8-K", "3.03,5.03") == frozenset({"TRIGGER_B"})
    assert N.classify_filing("8-K", "5.03") == frozenset({"TRIGGER_B"})


def test_8k_items_1_01_3_02_are_trigger_a():
    assert N.classify_filing("8-K", "1.01") == frozenset({"TRIGGER_A"})
    assert N.classify_filing("8-K", "3.02") == frozenset({"TRIGGER_A"})
    assert N.classify_filing("8-K", "1.01,3.02") == frozenset({"TRIGGER_A"})


def test_8k_both_triggers_at_once():
    # GRML's own filing, probe sample §4: items "1.01,3.02,5.03" in ONE 8-K.
    assert N.classify_filing("8-K", "1.01,3.02,5.03") == frozenset({"TRIGGER_A", "TRIGGER_B"})


def test_8k_uninteresting_items_no_trigger():
    # 3.01 (listing deficiency) and 3.03 (holders' rights) alone are not
    # scored by §3 -- SMTK's and KIFZ's own rows in the probe sample.
    assert N.classify_filing("8-K", "3.01") == frozenset()
    assert N.classify_filing("8-K", "3.03") == frozenset()
    assert N.classify_filing("8-K", "") == frozenset()


def test_10q_and_earnings_forms_no_trigger():
    assert N.classify_filing("10-Q", "") == frozenset()
    assert N.classify_filing("424B1", "") == frozenset()   # not in §3's Trigger A list


# --- G3: the probe's hand-read EDGAR sample, symbol by symbol ---------------------

def test_g3_edgar_sample_whlr():
    # WHLR: four 424B3 (ACTIVE_SHELF) + one 8-K "3.03,5.03" (TRIGGER_B).
    rows = [("424B3", ""), ("424B3", ""), ("424B3", ""), ("424B3", ""),
           ("8-K", "3.03,5.03")]
    got = [N.classify_filing(f, i) for f, i in rows]
    assert got == [frozenset({"ACTIVE_SHELF_CANDIDATE"})] * 4 + [frozenset({"TRIGGER_B"})]


def test_g3_edgar_sample_ipdn():
    assert N.classify_filing("8-K", "3.03,5.03") == frozenset({"TRIGGER_B"})
    assert N.classify_filing("8-K", "1.01") == frozenset({"TRIGGER_A"})
    assert N.classify_filing("424B4", "") == frozenset({"TRIGGER_A"})
    assert N.classify_filing("EFFECT", "") == frozenset({"TRIGGER_A"})
    assert N.classify_filing("S-1/A", "") == frozenset({"TRIGGER_A"})


def test_g3_edgar_sample_dcoy():
    assert N.classify_filing("8-K", "1.01,3.02") == frozenset({"TRIGGER_A"})
    assert N.classify_filing("DEF 14A", "") == frozenset({"PROPOSED_RS_CANDIDATE"})
    assert N.classify_filing("DEFA14A", "") == frozenset({"PROPOSED_RS_CANDIDATE"})
    assert N.classify_filing("PRE 14A", "") == frozenset({"PROPOSED_RS_CANDIDATE"})
    assert N.classify_filing("EFFECT", "") == frozenset({"TRIGGER_A"})


def test_g3_edgar_sample_kidz():
    assert N.classify_filing("8-K", "1.01,3.02") == frozenset({"TRIGGER_A"})
    assert N.classify_filing("8-K", "3.03,5.03") == frozenset({"TRIGGER_B"})
    assert N.classify_filing("DEF 14A", "") == frozenset({"PROPOSED_RS_CANDIDATE"})
    assert N.classify_filing("8-K", "3.03") == frozenset()
    assert N.classify_filing("PRE 14A", "") == frozenset({"PROPOSED_RS_CANDIDATE"})


# --- G2(d): EDGAR timestamp parsing ------------------------------------------------

def test_parse_edgar_accepted_treated_as_eastern_not_utc():
    # the probe sample's WHLR filing prints as "2026-09-17T20:18:43"
    dt = N.parse_edgar_accepted("2026-09-17T20:18:43.000Z")
    assert dt.tzinfo is not None
    assert (dt.hour, dt.minute, dt.second) == (20, 18, 43)
    assert dt.tzname() in ("EDT", "EST")


def test_parse_alpaca_created_at_is_real_utc():
    dt = N.parse_alpaca_created_at("2026-09-23T21:06:00Z")
    # 21:06 UTC in September (EDT, UTC-4) is 17:06 ET
    assert (dt.hour, dt.minute) == (17, 6)


# --- events + point-in-time windowing -----------------------------------------------

def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


def test_events_from_filings_grml_both_triggers():
    rows = [{"form": "8-K", "items": "1.01,3.02,5.03", "accepted": "2026-09-04T21:25:10Z"}]
    ev = N.events_from_filings("GRML", rows)
    kinds = {e.kind for e in ev}
    assert kinds == {"TRIGGER_A", "TRIGGER_B"}
    assert all(e.symbol == "GRML" for e in ev)


def test_events_from_headlines_maps_to_triggers():
    rows = [{"headline": "XYZ Announces 1-For-10 Reverse Stock Split", "created_at": "2026-09-23T13:00:00Z"},
           {"headline": "ABC Announces Proposed Public Offering", "created_at": "2026-09-23T13:00:00Z"},
           {"headline": "DEF Receives Nasdaq Minimum Bid Deficiency Notice", "created_at": "2026-09-23T13:00:00Z"}]
    ev = N.events_from_headlines("XYZ", rows)
    kinds = [e.kind for e in ev]
    assert kinds == ["TRIGGER_B", "TRIGGER_A", "DELIST_NOTICE"]


def test_trigger_a_window_2_days():
    ev = [N.Event(ts=_et(2026, 9, 20, 10, 0), kind="TRIGGER_A", source="EDGAR",
                 symbol="X", detail="424B5")]
    inside = N.label_at(ev, _et(2026, 9, 22, 9, 0))     # < 2 days later
    outside = N.label_at(ev, _et(2026, 9, 22, 11, 0))   # > 2 days later
    assert inside["trigger_a"] is True
    assert outside["trigger_a"] is False


def test_trigger_b_window_30_days():
    ev = [N.Event(ts=_et(2026, 8, 1, 10, 0), kind="TRIGGER_B", source="EDGAR",
                 symbol="X", detail="8-K")]
    inside = N.label_at(ev, _et(2026, 8, 30, 9, 0))     # 28.96 days later
    outside = N.label_at(ev, _et(2026, 9, 2, 9, 0))     # 32 days later
    assert inside["trigger_b"] is True
    assert outside["trigger_b"] is False


def test_active_shelf_needs_three_in_90_days():
    base = _et(2026, 9, 1, 10, 0)
    two = [N.Event(ts=base, kind="ACTIVE_SHELF_CANDIDATE", source="EDGAR",
                 symbol="X", detail="424B3") for _ in range(2)]
    three = two + [N.Event(ts=base, kind="ACTIVE_SHELF_CANDIDATE", source="EDGAR",
                          symbol="X", detail="424B3")]
    at = _et(2026, 9, 2, 10, 0)
    assert N.label_at(two, at)["active_shelf"] is False
    assert N.label_at(three, at)["active_shelf"] is True


def test_sources_filter_edgar_only_excludes_headline_events():
    ev = [N.Event(ts=_et(2026, 9, 20, 10, 0), kind="TRIGGER_A", source="ALPACA",
                 symbol="X", detail="OFFERING_PRICED")]
    assert N.label_at(ev, _et(2026, 9, 20, 12, 0), sources=N.EDGAR_ONLY)["trigger_a"] is False
    assert N.label_at(ev, _et(2026, 9, 20, 12, 0), sources=N.EDGAR_PLUS_HEADLINES)["trigger_a"] is True


def test_veto_is_trigger_a_or_b():
    at = _et(2026, 9, 20, 12, 0)
    ev_a = [N.Event(ts=at, kind="TRIGGER_A", source="EDGAR", symbol="X", detail="424B5")]
    ev_b = [N.Event(ts=at, kind="TRIGGER_B", source="EDGAR", symbol="X", detail="8-K")]
    ev_none: list[N.Event] = []
    assert N.label_at(ev_a, at)["veto"] is True
    assert N.label_at(ev_b, at)["veto"] is True
    assert N.label_at(ev_none, at)["veto"] is False


def test_delist_and_atm_never_veto():
    at = _et(2026, 9, 20, 12, 0)
    ev = [N.Event(ts=at, kind="DELIST_NOTICE", source="ALPACA", symbol="X", detail="DELIST_NOTICE"),
         N.Event(ts=at, kind="ATM", source="ALPACA", symbol="X", detail="ATM")]
    got = N.label_at(ev, at)
    assert got["veto"] is False
    assert got["delist_notice_recent"] is True
    assert got["atm_recent"] is True


def test_recency_bucket():
    ev = [N.Event(ts=_et(2026, 9, 20, 10, 0), kind="TRIGGER_A", source="EDGAR",
                 symbol="X", detail="424B5")]
    assert N.recency_bucket(ev, "TRIGGER_A", _et(2026, 9, 20, 18, 0)) == "0-1 day"
    assert N.recency_bucket(ev, "TRIGGER_A", _et(2026, 9, 24, 10, 0)) == "2-7"
    assert N.recency_bucket(ev, "TRIGGER_A", _et(2026, 10, 25, 10, 0)) == "31-90"
    assert N.recency_bucket(ev, "TRIGGER_B", _et(2026, 9, 20, 18, 0)) == "none"
