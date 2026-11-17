"""W18-0006: the macro closes file. Nothing here touches IBKR; a fake connection stands in."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from desk import config as cfgmod
from desk import macro

NOW = datetime(2026, 11, 10, 21, 20, tzinfo=timezone.utc)


def bars(closes, start=date(2026, 10, 20)):
    return [SimpleNamespace(date=start + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1)
            for i, c in enumerate(closes)]


class FakeIB:
    """series: {symbol: bars list}. A symbol that is absent returns no bars (no subscription)."""

    def __init__(self, series, fail_connect=False, unknown=()):
        self.series, self.fail_connect, self.unknown = series, fail_connect, set(unknown)
        self.connect_kwargs = None
        self.hist_calls = []
        self.disconnected = False

    def connect(self, host, port, **kw):
        if self.fail_connect:
            raise ConnectionRefusedError("refused")
        self.connect_kwargs = kw

    def disconnect(self):
        self.disconnected = True

    def qualifyContracts(self, c):
        c.conId = 0 if c.symbol in self.unknown else 7
        return [c]

    def reqHistoricalData(self, contract, **kw):
        self.hist_calls.append((contract.symbol, kw))
        return self.series.get(contract.symbol, [])


def _c(kind):
    def make(symbol, *a, primaryExchange=None, **k):
        exch = a[0] if a else None
        return SimpleNamespace(symbol=symbol, kind=kind, exchange=exch, conId=0, primaryExchange=primaryExchange)
    return make


MOD = SimpleNamespace(Stock=_c("stock"), Index=_c("index"), ContFuture=_c("future"))

GOOD = {
    "SPY": bars([100, 101, 102, 103, 104, 105, 110]),
    "QQQ": bars([200, 200, 200, 200, 200, 210, 200]),
    "IWM": bars([50] * 7),
    "VIX": bars([20, 20, 20, 20, 20, 20, 18]),
    "CL": bars([60, 61, 62, 63, 64, 65, 66]),
    "TNX": bars([4.0, 4.1, 4.2, 4.3, 4.4, 4.5, 4.35]),
}


def cfg_for(tmp_path):
    cfg = cfgmod.load_config()
    cfg["runs_dir"] = str(tmp_path / "runs")
    return cfg


def run(tmp_path, ib):
    res = macro.build(cfg_for(tmp_path), "2026-11-10", _ib=ib, _mod=MOD, now=NOW)
    text = (tmp_path / "runs" / "2026-11-10" / "_macro_data.md").read_text(encoding="utf-8")
    return res, text


def row(text, start):
    return next(l for l in text.splitlines() if l.startswith(f"| {start}"))


def test_shipped_config_has_an_unused_client_id_and_the_file_name_matches_the_pipeline():
    m = cfgmod.load_config()["macro"]
    cfg = cfgmod.load_config()
    assert m["client_id"] not in (17, 55, 77, 88, cfg["ibkr"]["client_id"], cfg["bridge"]["client_id"])
    assert macro.MACRO_DATA_FILE == "_macro_data.md"


def test_all_real_series_numbers_and_readonly_connection(tmp_path):
    ib = FakeIB(GOOD)
    res, text = run(tmp_path, ib)
    assert res["real"] == 6 and res["standin"] == 0 and res["unavailable"] == []
    assert ib.connect_kwargs["readonly"] is True and ib.connect_kwargs["clientId"] == 93
    assert ib.disconnected
    spy = row(text, "S&P 500")
    assert "110.00" in spy and "5.00" in spy and "4.76%" in spy and "8.91%" in spy
    assert "2026-10-26" in spy                       # last bar date
    tnx = row(text, "US 10-year")
    assert "4.350%" in tnx and "(15.0) bp" in tnx and "25.0 bp" in tnx
    assert row(text, "WTI crude").count("66.00") == 1
    assert all(kw["whatToShow"] == "TRADES" and kw["barSizeSetting"] == "1 day" for _, kw in ib.hist_calls)


def test_negatives_are_in_brackets(tmp_path):
    _, text = run(tmp_path, FakeIB(GOOD))
    qqq = row(text, "Nasdaq-100")
    assert "(10.00)" in qqq and "(4.76)%" in qqq
    assert "-4.76" not in text and "-10.00" not in text


def test_yield_index_quoted_times_ten_is_divided_and_labelled(tmp_path):
    series = dict(GOOD, TNX=bars([40, 41, 42, 43, 44, 45, 43.5]))
    _, text = run(tmp_path, FakeIB(series))
    tnx = row(text, "US 10-year")
    assert "4.350%" in tnx and "(15.0) bp" in tnx and "divided by 10" in tnx


def test_vix_without_subscription_uses_a_labelled_standin(tmp_path):
    series = {k: v for k, v in GOOD.items() if k != "VIX"}
    series["VIXY"] = bars([30, 30, 30, 30, 30, 30, 33])
    res, text = run(tmp_path, FakeIB(series))
    assert res["real"] == 5 and res["standin"] == 1 and res["unavailable"] == []
    vix = row(text, "VIX")
    assert "STAND-IN" in vix and "NOT the VIX itself" in vix and "33.00" in vix and "VIX:" in vix
    assert "A STAND-IN row is a fund" in text


def test_standin_yield_fund_is_shown_as_a_price_not_a_yield(tmp_path):
    series = {k: v for k, v in GOOD.items() if k != "TNX"}
    series["IEF"] = bars([95, 95, 95, 95, 95, 95, 96])
    _, text = run(tmp_path, FakeIB(series))
    ief = row(text, "IEF")
    assert "96.00" in ief and "bp" not in ief and "STAND-IN" in ief and "FALLS when yields RISE" in ief


def test_instrument_that_fails_everywhere_is_marked_unavailable_and_others_survive(tmp_path):
    series = {k: v for k, v in GOOD.items() if k != "CL"}
    res, text = run(tmp_path, FakeIB(series, unknown=("CL", "USO")))
    assert res["unavailable"] == ["CL"] and res["real"] == 5
    crude = row(text, "WTI crude")
    assert "UNAVAILABLE" in crude and "could not identify CL" in crude
    assert "WebSearch" in text


def test_stale_series_triggers_a_warning(tmp_path):
    series = dict(GOOD, IWM=bars([50] * 7, start=date(2026, 10, 10)))
    _, text = run(tmp_path, FakeIB(series))
    assert "WARNING: the latest bar dates differ" in text and "2026-10-16" in text


def test_short_history_leaves_five_day_change_blank_not_wrong(tmp_path):
    series = dict(GOOD, SPY=bars([100, 102, 101]))
    _, text = run(tmp_path, FakeIB(series))
    assert "n/a" in row(text, "S&P 500") and "1.00" in row(text, "S&P 500")


def test_nothing_at_all_raises_and_writes_no_file(tmp_path):
    with pytest.raises(macro.MacroError, match="no instrument returned data"):
        macro.build(cfg_for(tmp_path), "2026-11-10", _ib=FakeIB({}), _mod=MOD, now=NOW)
    assert not (tmp_path / "runs" / "2026-11-10" / "_macro_data.md").exists()


def test_connection_failure_live_and_unknown_ports_are_refused(tmp_path):
    with pytest.raises(macro.MacroError, match="cannot connect"):
        macro.build(cfg_for(tmp_path), "2026-11-10", _ib=FakeIB(GOOD, fail_connect=True), _mod=MOD)
    for port in (4001, 7496, 1234):
        cfg = cfg_for(tmp_path)
        cfg["ibkr"]["port"] = port
        ib = FakeIB(GOOD)
        with pytest.raises(macro.MacroError):
            macro.build(cfg, "2026-11-10", _ib=ib, _mod=MOD)
        assert ib.connect_kwargs is None             # refused before connecting


def test_cli_exit_codes(monkeypatch, capsys):
    monkeypatch.setattr(macro, "build", lambda cfg, date: {"file": "x", "real": 6, "standin": 0, "unavailable": []})
    assert macro.main(["--date", "2026-11-10"]) == 0
    assert capsys.readouterr().out.startswith("MACRO {")

    def boom(cfg, date):
        raise macro.MacroError("gateway down")
    monkeypatch.setattr(macro, "build", boom)
    assert macro.main(["--date", "2026-11-10"]) == 2
    assert "MACRO FAILED: gateway down" in capsys.readouterr().out
