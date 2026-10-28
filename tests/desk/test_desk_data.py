"""Tests for the desk's Python half: indicators, snapshot, fetch, fundamentals,
prepare. Nothing here touches IBKR, SEC or the repo's var/ -- everything runs on
synthetic data in tmp_path."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from desk import config as cfgmod
from desk import fetch_bars, fundamentals, indicators as ind, prepare as prep, snapshot


def make_bars(n=300, start="2025-01-02", seed=1, drift=0.0005):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    ret = rng.normal(drift, 0.015, n)
    close = 100 * np.exp(np.cumsum(ret))
    high = close * (1 + rng.uniform(0.001, 0.02, n))
    low = close * (1 - rng.uniform(0.001, 0.02, n))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    vol = rng.integers(500_000, 2_000_000, n).astype(float)
    return pd.DataFrame({"date": idx, "open": open_, "high": high, "low": low, "close": close, "volume": vol})


# ------------------------------------------------------------------ config

def test_ticker_and_date_validation():
    assert cfgmod.norm_ticker(" mpc ") == "MPC"
    assert cfgmod.norm_ticker("BRK.B") == "BRK.B"
    for bad in ("../x", "A B", "", "1ABC", "a" * 20, "MPC;rm"):
        with pytest.raises(ValueError):
            cfgmod.norm_ticker(bad)
    assert cfgmod.norm_date("2026-10-28") == "2026-10-28"
    for bad in ("2026-13-45", "28/10/2026", "2026-10-28 "[:9]):
        with pytest.raises(ValueError):
            cfgmod.norm_date(bad)


def test_default_run_date_is_the_us_date_not_the_sydney_date():
    # 23:30 Sydney on 28 Oct (UTC+11) = 12:30 UTC 28 Oct = 08:30 New York 28 Oct;
    # 08:00 Sydney on 29 Oct = 21:00 UTC 28 Oct = 17:00 New York 28 Oct.
    now = datetime(2026, 10, 28, 21, 0, tzinfo=timezone.utc)      # Sydney: 29 Oct 08:00
    assert cfgmod.default_run_date(now) == "2026-10-28"


def test_shipped_config_is_sane():
    cfg = cfgmod.load_config()
    assert len(cfg["tickers"]) == 20 and len(set(cfg["tickers"])) == 20
    for t in cfg["tickers"]:
        assert cfgmod.norm_ticker(t) == t
    assert cfg["ibkr"]["port"] in fetch_bars.PAPER_PORTS
    assert cfg["paper_rules"]["long_only"] is True
    # client ids already in use elsewhere in the repo must not be reused
    assert cfg["ibkr"]["client_id"] not in (17, 55, 77, 88)


# -------------------------------------------------------------- indicators

def test_sma_ema_known_values():
    s = pd.Series([1.0, 2, 3, 4, 5])
    assert ind.sma(s, 3).iloc[-1] == pytest.approx(4.0)
    assert np.isnan(ind.sma(s, 3).iloc[1])
    e = ind.ema(pd.Series([2.0] * 30), 10)
    assert e.iloc[-1] == pytest.approx(2.0)


def test_rsi_extremes_and_midpoint():
    up = pd.Series(np.arange(1.0, 60.0))
    assert ind.rsi(up).iloc[-1] == pytest.approx(100.0)
    dn = pd.Series(np.arange(60.0, 1.0, -1.0))
    assert ind.rsi(dn).iloc[-1] == pytest.approx(0.0, abs=1e-6)
    zig = pd.Series([10.0, 11.0] * 40)
    assert 40 < ind.rsi(zig).iloc[-1] < 60


def test_atr_constant_range():
    n = 60
    high = pd.Series([11.0] * n)
    low = pd.Series([9.0] * n)
    close = pd.Series([10.0] * n)
    assert ind.atr(high, low, close).iloc[-1] == pytest.approx(2.0)


def test_bollinger_flat_series_has_zero_width():
    mid, up, lo = ind.bollinger(pd.Series([5.0] * 30))
    assert mid.iloc[-1] == up.iloc[-1] == lo.iloc[-1] == 5.0


def test_vwma_weights_by_volume():
    c = pd.Series([10.0] * 19 + [20.0])
    v = pd.Series([1.0] * 19 + [981.0])
    out = ind.vwma(c, v, 20).iloc[-1]
    assert 19.0 < out < 20.0
    assert ind.vwma(c, pd.Series([0.0] * 20), 20).iloc[-1] != ind.vwma(c, pd.Series([0.0] * 20), 20).iloc[-1]  # NaN


def test_macd_histogram_is_line_minus_signal():
    c = make_bars()["close"]
    line, sig, hist = ind.macd(c)
    assert (hist - (line - sig)).abs().max() < 1e-12


# ---------------------------------------------------------------- snapshot

def test_snapshot_matches_independent_calculation():
    df = make_bars()
    s = snapshot.build_snapshot(df, "TEST", "2026-10-28")
    c = df["close"]
    assert s["price"]["close"] == pytest.approx(round(c.iloc[-1], 4))
    assert s["indicators"]["sma50"] == pytest.approx(round(c.iloc[-50:].mean(), 4))
    assert s["indicators"]["sma200"] == pytest.approx(round(c.iloc[-200:].mean(), 4))
    assert s["returns_pct"]["1m"] == pytest.approx(round((c.iloc[-1] / c.iloc[-22] - 1) * 100, 2))
    assert s["range_52w"]["high"] == pytest.approx(round(df["high"].iloc[-252:].max(), 4))
    assert s["bars"] == 300
    json.dumps(s, allow_nan=False)          # no NaN leaks into JSON


def test_snapshot_with_short_history_leaves_long_averages_null_not_nan():
    s = snapshot.build_snapshot(make_bars(n=80), "TEST", "2026-10-28")
    assert s["indicators"]["sma200"] is None
    assert s["returns_pct"]["12m"] is None
    assert "close_above_sma200" not in s["flags"]
    json.dumps(s, allow_nan=False)


def test_snapshot_refuses_too_little_history():
    with pytest.raises(ValueError, match="need at least"):
        snapshot.build_snapshot(make_bars(n=30), "TEST", "2026-10-28")


def test_clean_bars_sorts_dedupes_and_rejects_bad_input():
    df = make_bars(n=70)
    messy = pd.concat([df.iloc[::-1], df.iloc[:3]])
    out = snapshot.clean_bars(messy)
    assert out.index.is_monotonic_increasing and out.index.is_unique and len(out) == 70
    with pytest.raises(ValueError):
        snapshot.clean_bars(pd.DataFrame())
    with pytest.raises(ValueError, match="missing columns"):
        snapshot.clean_bars(df.drop(columns=["volume"]))


def test_partial_bar_dropped_only_while_the_session_is_open():
    idx = pd.bdate_range("2026-10-20", "2026-10-28")           # 28 Oct 2026 is a Wednesday
    df = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}, index=idx)
    during = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)   # 11:00 New York (EDT, UTC-4)
    after = datetime(2026, 10, 28, 22, 0, tzinfo=timezone.utc)    # 18:00 New York
    out, dropped = snapshot.drop_partial_bar(df, during)
    assert dropped and out.index[-1] == pd.Timestamp("2026-10-27")
    out, dropped = snapshot.drop_partial_bar(df, after)
    assert not dropped and out.index[-1] == pd.Timestamp("2026-10-28")


def test_market_markdown_contains_the_key_numbers():
    s = snapshot.build_snapshot(make_bars(), "TEST", "2026-10-28")
    md = snapshot.render_market_markdown(s)
    assert "TEST verified market snapshot" in md and "ATR(14)" in md and "RSI(14)" in md
    assert f"{s['price']['close']:,.2f}" in md
    assert "nan" not in md.lower().replace("financial", "")


# -------------------------------------------------------------- fetch_bars

class FakeIB:
    def __init__(self, fail_connect=False, qualify_ok_on="NYSE", bars=None):
        self.fail_connect, self.qualify_ok_on = fail_connect, qualify_ok_on
        self.bars = bars if bars is not None else [
            SimpleNamespace(date=date(2026, 10, 27), open=1, high=2, low=0.5, close=1.5, volume=100)]
        self.connected = False
        self.connect_kwargs = None
        self.hist_kwargs = None

    def connect(self, host, port, **kw):
        if self.fail_connect:
            raise ConnectionRefusedError("refused")
        self.connected, self.connect_kwargs = True, kw

    def disconnect(self):
        self.connected = False

    def qualifyContracts(self, c):
        ok = (getattr(c, "primaryExchange", None) == self.qualify_ok_on)
        c.conId = 123 if ok else 0
        return [c]

    def reqHistoricalData(self, contract, **kw):
        self.hist_kwargs = kw
        return self.bars


def fake_stock(symbol, exch, cur, primaryExchange=None):
    return SimpleNamespace(symbol=symbol, exchange=exch, currency=cur, primaryExchange=primaryExchange, conId=0)


def test_fetch_uses_readonly_connection_and_daily_rth_bars_and_tries_primaries():
    ib = FakeIB()
    df = fetch_bars.fetch_daily_bars("B", _ib=ib, _stock=fake_stock)
    assert ib.connect_kwargs["readonly"] is True and ib.connect_kwargs["clientId"] == 91
    assert ib.hist_kwargs["barSizeSetting"] == "1 day" and ib.hist_kwargs["useRTH"] is True
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert ib.connected is False                      # always disconnects


def test_fetch_refuses_live_and_unknown_ports():
    for port in (4001, 7496, 9999):
        with pytest.raises(fetch_bars.BarFetchError):
            fetch_bars.fetch_daily_bars("MPC", port=port, _ib=FakeIB(), _stock=fake_stock)


def test_fetch_connection_failure_is_explained():
    with pytest.raises(fetch_bars.BarFetchError, match="Gateway/TWS running"):
        fetch_bars.fetch_daily_bars("MPC", _ib=FakeIB(fail_connect=True), _stock=fake_stock)


def test_fetch_unqualifiable_and_empty_cases_raise():
    with pytest.raises(fetch_bars.BarFetchError, match="could not qualify"):
        fetch_bars.fetch_daily_bars("ZZZZ", _ib=FakeIB(qualify_ok_on="NONE"), _stock=fake_stock)
    with pytest.raises(fetch_bars.BarFetchError, match="no bars"):
        fetch_bars.fetch_daily_bars("MPC", _ib=FakeIB(bars=[]), _stock=fake_stock)


# ------------------------------------------------------------ fundamentals

def _q(end, val, filed, days=91):
    st = (date.fromisoformat(end) - pd.Timedelta(days=days)).isoformat()
    return {"start": st, "end": end, "val": val, "filed": filed, "form": "10-Q"}


def fake_facts():
    ends = ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]
    rev = [_q(e, 1000 + 100 * i, "2026-04-30") for i, e in enumerate(ends)]
    rev.append({"start": "2025-01-01", "end": "2025-12-31", "val": 4600, "filed": "2026-02-20", "form": "10-K"})
    ni = [_q(e, 100 + 10 * i, "2026-04-30") for i, e in enumerate(ends)]
    # a restatement of the oldest quarter filed later must win
    rev.append(_q("2025-03-31", 1010, "2026-05-15"))
    cash = [{"end": "2026-03-31", "val": 500, "filed": "2026-04-30"}, {"end": "2025-12-31", "val": 400, "filed": "2026-02-20"}]
    debt = [{"end": "2026-03-31", "val": 900, "filed": "2026-04-30"}]
    eq = [{"end": "2026-03-31", "val": 1800, "filed": "2026-04-30"}]
    return {"entityName": "Fake Corp", "facts": {
        "us-gaap": {
            "Revenues": {"units": {"USD": rev}},
            "NetIncomeLoss": {"units": {"USD": ni}},
            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": cash}},
            "LongTermDebt": {"units": {"USD": debt}},
            "StockholdersEquity": {"units": {"USD": eq}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [_q("2026-03-31", 1.23, "2026-04-30")]}},
        },
        "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2026-04-25", "val": 123456789, "filed": "2026-04-30"}]}}},
    }}


def test_summarize_picks_latest_filing_and_computes_ttm_and_yoy():
    s = fundamentals.summarize(fake_facts(), date(2026, 10, 28))
    q = dict(s["metrics"]["Revenue"]["quarterly"])
    assert q[date(2026, 3, 31)] == 1400
    assert q[date(2025, 3, 31)] == 1010                  # restated value, not the original 1000
    assert s["derived"]["Revenue TTM"] == 1400 + 1300 + 1200 + 1100
    assert s["derived"]["Revenue growth, latest quarter vs year ago %"] == pytest.approx((1400 / 1010 - 1) * 100)
    assert s["derived"]["Net debt (long-term debt - cash)"] == 400
    assert s["derived"]["Long-term debt / equity"] == pytest.approx(0.5)
    assert s["shares_outstanding"][1] == 123456789


def test_summarize_is_point_in_time():
    s = fundamentals.summarize(fake_facts(), date(2026, 3, 1))     # before the 10-Q filings
    q = s["metrics"]["Revenue"]["quarterly"]
    assert all(e <= date(2025, 12, 31) for e, _ in q)
    assert "Cash" in s["metrics"] and s["metrics"]["Cash"]["instant"][0][0] == date(2025, 12, 31)


def test_summarize_handles_ifrs_filer_with_annual_only_and_empty_input():
    f = {"entityName": "Foreign SA", "facts": {"ifrs-full": {
        "Revenue": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 2.5e9, "filed": "2026-03-01"}]}}}}}
    s = fundamentals.summarize(f, date(2026, 10, 28))
    assert s["metrics"]["Revenue"]["annual"][0][1] == 2.5e9 and s["metrics"]["Revenue"]["quarterly"] == []
    md = fundamentals.render_markdown("NEXA", "Foreign SA", s, date(2026, 10, 28))
    assert "annual only" in md and "2.50B" in md
    empty = fundamentals.render_markdown("X", "X", fundamentals.summarize({}, date(2026, 10, 28)), date(2026, 10, 28))
    assert "NO USABLE XBRL FACTS" in empty


def test_render_uses_brackets_for_negatives():
    f = fake_facts()
    f["facts"]["us-gaap"]["NetIncomeLoss"]["units"]["USD"][-1]["val"] = -50
    md = fundamentals.render_markdown("T", "Fake", fundamentals.summarize(f, date(2026, 10, 28)), date(2026, 10, 28))
    assert "(50)" in md and "-50" not in md


def test_fetch_facts_requires_contact_and_uses_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("SEC_CONTACT", raising=False)
    with pytest.raises(fundamentals.FundamentalsError, match="SEC_CONTACT"):
        fundamentals.fetch_facts("MPC", tmp_path)
    monkeypatch.setenv("SEC_CONTACT", "ben@example.com")
    monkeypatch.setattr(fundamentals, "MIN_GAP_S", 0)
    calls = []

    def fake_get(url, ua, _opener=None):
        calls.append((url, ua))
        if url == fundamentals.TICKER_MAP_URL:
            return {"0": {"cik_str": 1510295, "ticker": "MPC", "title": "Marathon Petroleum"}}
        return fake_facts()

    monkeypatch.setattr(fundamentals, "_get_json", fake_get)
    facts, title = fundamentals.fetch_facts("mpc", tmp_path)
    assert title == "Marathon Petroleum" and facts["entityName"] == "Fake Corp"
    assert all("ben@example.com" in ua for _, ua in calls)
    n = len(calls)
    fundamentals.fetch_facts("MPC", tmp_path)
    assert len(calls) == n                                    # second call served from cache
    with pytest.raises(fundamentals.FundamentalsError, match="not in SEC"):
        fundamentals.fetch_facts("NOPE", tmp_path)


# ----------------------------------------------------------------- prepare

def test_prepare_writes_all_files_from_csv_and_fake_facts(tmp_path):
    cfg = cfgmod.load_config()
    cfg["runs_dir"] = str(tmp_path / "runs")
    csvp = tmp_path / "bars.csv"
    make_bars().to_csv(csvp, index=False)
    res = prep.prepare("MPC", "2026-10-28", cfg, bars_csv=str(csvp),
                       _facts=lambda t: (fake_facts(), "Marathon Petroleum"))
    rd = tmp_path / "runs" / "2026-10-28" / "MPC"
    for name in ("bars.csv", "snapshot.json", "market_data.md", "fundamentals_data.md", "status.json"):
        assert (rd / name).exists(), name
    st = json.loads((rd / "status.json").read_text(encoding="utf-8"))
    assert st["bars"].startswith("ok") and st["fundamentals"].startswith("ok")
    assert res["close"] == json.loads((rd / "snapshot.json").read_text(encoding="utf-8"))["price"]["close"]


def test_prepare_survives_missing_fundamentals_but_not_missing_bars(tmp_path):
    cfg = cfgmod.load_config()
    cfg["runs_dir"] = str(tmp_path / "runs")
    csvp = tmp_path / "bars.csv"
    make_bars().to_csv(csvp, index=False)

    def boom(t):
        raise fundamentals.FundamentalsError("SEC down")

    prep.prepare("MPC", "2026-10-28", cfg, bars_csv=str(csvp), _facts=boom)
    rd = tmp_path / "runs" / "2026-10-28" / "MPC"
    assert "UNAVAILABLE" in (rd / "fundamentals_data.md").read_text(encoding="utf-8")
    assert json.loads((rd / "status.json").read_text(encoding="utf-8"))["fundamentals"].startswith("unavailable")

    def no_gateway(*a, **k):
        raise fetch_bars.BarFetchError("cannot connect")

    with pytest.raises(fetch_bars.BarFetchError):
        prep.prepare("AMZN", "2026-10-28", cfg, skip_fundamentals=True, _fetch=no_gateway)
    st = json.loads((tmp_path / "runs" / "2026-10-28" / "AMZN" / "status.json").read_text(encoding="utf-8"))
    assert st["bars"].startswith("FAILED")


def test_prepare_cli_returns_2_on_failure_and_0_on_success(tmp_path, capsys, monkeypatch):
    cfgp = tmp_path / "config.json"
    cfg = cfgmod.load_config()
    cfg["runs_dir"] = str(tmp_path / "runs")
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    csvp = tmp_path / "bars.csv"
    make_bars().to_csv(csvp, index=False)
    ok = prep.main(["MPC", "--date", "2026-10-28", "--bars-csv", str(csvp), "--skip-fundamentals", "--config", str(cfgp)])
    assert ok == 0 and "PREPARED {" in capsys.readouterr().out
    bad = prep.main(["MPC", "--date", "2026-10-28", "--bars-csv", str(tmp_path / "missing.csv"),
                     "--skip-fundamentals", "--config", str(cfgp)])
    assert bad == 2 and "PREPARE FAILED" in capsys.readouterr().out
