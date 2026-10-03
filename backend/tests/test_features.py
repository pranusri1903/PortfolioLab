import io
import json
from datetime import date, timedelta
from decimal import Decimal as D

import httpx
import pytest

from app.api.market import get_provider
from app.calculations.xirr import xirr
from app.main import app
from app.repositories import data as repo
from app.services import prices
from app.services.live_data import CompositeProvider, MfApiProvider, SymbolHit, TwelveDataProvider
from tests.conftest import auth

BASE = "/api/v1/portfolios"
H = auth("feat")


def new_portfolio(client, currency="USD", demo=False):
    r = client.post(BASE, json={"name": "P", "currency": currency, "load_demo_data": demo}, headers=H)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_xirr_matches_simple_annual_return():
    r = xirr([(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), 1100.0)])
    assert abs(r - 0.0997) < 0.002  # 366-day year
    assert xirr([(date(2024, 1, 1), -1000.0), (date(2024, 1, 5), 1100.0)]) is None  # too short
    assert xirr([(date(2024, 1, 1), -1000.0), (date(2025, 1, 1), -5.0)]) is None  # no inflow


def test_one_portfolio_per_currency_and_inr_demo(client):
    usd, inr = new_portfolio(client), new_portfolio(client, "INR", demo=True)
    dup_demo = {"name": "x", "currency": "INR", "load_demo_data": True}
    assert client.post(BASE, json=dup_demo, headers=H).status_code == 409  # one demo per currency
    assert (
        client.post(BASE, json={"name": "x", "currency": "USD"}, headers=H).status_code == 409
    )  # one real per currency
    s = client.get(f"{BASE}/{inr}/summary", headers=H).json()
    assert (
        s["portfolio"]["base_currency"] == "INR" and s["is_sample_data"] and D(s["total_value"]) > 1_000_000
    )
    assert client.get(f"{BASE}/{inr}/performance?range=All", headers=H).json()["benchmark_symbol"] == "NIFB"
    assert D(client.get(f"{BASE}/{usd}/summary", headers=H).json()["total_value"]) == 0


def test_currency_mismatch_rejected(client):
    pid = new_portfolio(client)
    body = {"trade_date": "2025-01-10", "type": "DEPOSIT", "cash_amount": "100000"}
    client.post(f"{BASE}/{pid}/transactions", json=body, headers=H)
    r = client.post(
        f"{BASE}/{pid}/transactions",
        headers=H,
        json={"trade_date": "2025-01-13", "type": "BUY", "symbol": "INFX", "quantity": "1", "price": "10"},
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "currency_mismatch"


def test_quick_start_builds_ledger_once(client):
    pid = new_portfolio(client)
    body = {
        "cash": "100",
        "holdings": [{"symbol": "ACME", "quantity": "10", "average_price": "50", "date": "2025-01-10"}],
    }
    assert client.post(f"{BASE}/{pid}/quick-start", json=body, headers=H).json() == {"created": 2}
    s = client.get(f"{BASE}/{pid}/summary", headers=H).json()
    assert D(s["cash_balance"]) == 100 and D(s["net_contributions"]) == 600
    h = client.get(f"{BASE}/{pid}/holdings", headers=H).json()["holdings"][0]
    assert D(h["cost_basis"]) == 500
    assert client.post(f"{BASE}/{pid}/quick-start", json=body, headers=H).status_code == 409
    bad = {"holdings": [{"symbol": "INFX", "quantity": "1", "average_price": "1", "date": "2025-01-10"}]}
    other = new_portfolio(client, "INR")
    assert client.post(f"{BASE}/{other}/quick-start", json=bad, headers=H).status_code == 201


def test_sip_creates_installments_once_and_survives_delete(client):
    pid = new_portfolio(client)
    r = client.post(
        f"{BASE}/{pid}/sips",
        headers=H,
        json={"symbol": "GRWF", "amount": "500", "day_of_month": 5, "start_date": "2024-01-01"},
    )
    assert r.status_code == 201, r.text
    sip = r.json()
    assert sip["installments"] == 33 and sip["xirr"] is not None and D(sip["current_value"]) > 0
    patched = client.patch(f"{BASE}/{pid}/sips/{sip['id']}", json={"end_date": None}, headers=H).json()
    assert patched["installments"] == 33  # idempotent
    s = client.get(f"{BASE}/{pid}/summary", headers=H).json()
    assert D(s["cash_balance"]) >= 0 and D(s["net_contributions"]) == 500 * 33
    assert client.get(f"{BASE}/{pid}/transactions?source=sip", headers=H).json()["total"] == 66
    assert client.delete(f"{BASE}/{pid}/sips/{sip['id']}", headers=H).status_code == 204
    assert (
        client.get(f"{BASE}/{pid}/transactions?source=sip", headers=H).json()["total"] == 0
    )  # unlinked, not deleted
    assert client.get(f"{BASE}/{pid}/transactions", headers=H).json()["total"] == 66


def test_sip_validation_and_ownership(client):
    pid = new_portfolio(client)
    bad = {"symbol": "GRWF", "amount": "500", "day_of_month": 31, "start_date": "2024-01-01"}
    assert client.post(f"{BASE}/{pid}/sips", json=bad, headers=H).status_code == 422
    inr = {"symbol": "FLXF", "amount": "500", "day_of_month": 5, "start_date": "2024-01-01"}
    assert (
        client.post(f"{BASE}/{pid}/sips", json=inr, headers=H).json()["error"]["code"] == "currency_mismatch"
    )
    assert client.get(f"{BASE}/{pid}/sips", headers=auth("intruder")).status_code == 404


def test_broker_csv_mapping_with_indian_formats(client):
    pid = new_portfolio(client, "INR")
    csv = (
        "Date,Action,Ticker,Units,Rate,Brokerage,Amount\n"
        '10/01/2025,Credit,,,,,"Rs 1,00,000.00"\n'
        "13/01/2025,Bought,infx,10,1500.50,20,\n"
        "99/99/2025,Bought,infx,1,1,0,\n"
    )
    mapping = {
        "trade_date": "Date",
        "type": "Action",
        "symbol": "Ticker",
        "quantity": "Units",
        "price": "Rate",
        "fee": "Brokerage",
        "cash_amount": "Amount",
    }
    files = {"file": ("b.csv", io.BytesIO(csv.encode()))}
    data = {"mapping": json.dumps(mapping), "date_format": "%d/%m/%Y"}
    r = client.post(f"{BASE}/{pid}/transactions/import?commit=true", files=files, data=data, headers=H).json()
    assert r["result"] == {"imported": 2, "skipped": 0, "rejected": 1}
    h = client.get(f"{BASE}/{pid}/holdings", headers=H).json()["holdings"][0]
    assert h["symbol"] == "INFX" and D(h["cost_basis"]) == D("15025.00")


def test_analytics_for_demo_portfolio(client):
    pid = new_portfolio(client, demo=True)
    a = client.get(f"{BASE}/{pid}/analytics", headers=H).json()
    by = {h["symbol"]: h for h in a["holdings"]}
    assert {"ACME", "GRWF", "DYNA"} <= set(by)
    assert by["GRWF"]["asset_type"] == "MUTUAL_FUND" and by["GRWF"]["xirr"] is not None
    assert D(by["DYNA"]["realized_gain_loss"]) != 0 and D(by["ACME"]["dividends"]) == 300
    for h in a["holdings"]:
        parts = D(h["unrealized_gain_loss"]) + D(h["realized_gain_loss"]) + D(h["dividends"])
        assert abs(parts - D(h["total_return"])) < D("0.01")
    assert a["portfolio_xirr"]["value"] is not None
    c = a["correlation"]
    assert c["symbols"] and all(c["matrix"][i][i] == 1.0 for i in range(len(c["symbols"])))
    assert (
        0 < a["concentration"]["hhi"] <= 1
        and a["drawdown"]
        and min(p["drawdown"] for p in a["drawdown"]) <= 0
    )
    only = client.get(f"{BASE}/{pid}/analytics?asset_type=MUTUAL_FUND", headers=H).json()
    assert {h["asset_type"] for h in only["holdings"]} == {"MUTUAL_FUND"}
    funds = client.get(f"{BASE}/{pid}/holdings?asset_type=ETF", headers=H).json()["holdings"]
    assert funds and {h["asset_type"] for h in funds} == {"ETF"}


def test_new_date_ranges(client):
    pid = new_portfolio(client, demo=True)
    for r in ("6M", "YTD", "3Y", "5Y"):
        p = client.get(f"{BASE}/{pid}/performance?range={r}", headers=H).json()
        assert p["series"] and p["metrics"]["cumulative_return"]["value"] is not None, r


# ---- live data -------------------------------------------------------------------------------


class FakeLive(CompositeProvider):
    source = "fake"

    def __init__(self):
        super().__init__(stocks=object(), funds=None)  # type: ignore[arg-type]
        self.last_end = None

    def search(self, q, currency=None):
        hits = [
            SymbolHit("SPY", "SPDR S&P 500 ETF", "ETF", "USD", "ARCX"),
            SymbolHit("AAPL", "Apple Inc", "STOCK", "USD", "XNAS"),
            SymbolHit("RELIANCE.NS", "Reliance Industries", "STOCK", "INR", "XNSE"),
        ]
        return [h for h in hits if q.upper() in h.symbol and currency in (None, h.currency)]

    def source_for(self, a):
        return "fake"

    def daily_closes(self, asset, start, end):
        self.last_end = end
        d = start
        while d <= end:
            if d.weekday() < 5:
                yield d, D("100") + D(d.toordinal() % 7)
            d += timedelta(days=1)


@pytest.fixture
def live(client):
    fake = FakeLive()
    app.dependency_overrides[get_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_provider, None)


def test_search_add_and_trade_a_live_symbol(client, live):
    r = client.get("/api/v1/assets/search?q=aap&currency=USD", headers=H).json()
    assert [x["symbol"] for x in r["results"]] == ["AAPL"] and not r["results"][0]["in_db"]
    local = client.get("/api/v1/assets/search?q=acme", headers=H).json()["results"][0]
    assert local["in_db"] and local["sample"]
    assert client.post("/api/v1/assets", json={"symbol": "NOPE"}, headers=H).status_code == 404
    assert client.post("/api/v1/assets", json={"symbol": "AAPL"}, headers=H).status_code == 201
    pid = new_portfolio(client)
    client.post(
        f"{BASE}/{pid}/transactions",
        headers=H,
        json={"trade_date": date.today().isoformat(), "type": "DEPOSIT", "cash_amount": "5000"},
    )
    r = client.post(
        f"{BASE}/{pid}/transactions",
        headers=H,
        json={
            "trade_date": date.today().isoformat(),
            "type": "BUY",
            "symbol": "AAPL",
            "quantity": "2",
            "price": "100",
        },
    )
    assert r.status_code == 201
    h = client.get(f"{BASE}/{pid}/holdings", headers=H).json()
    assert not h["is_sample_data"] and h["holdings"][0]["price_status"] == "ok"


def test_inr_symbols_keep_suffix_and_currency(client, live):
    assert (
        client.post("/api/v1/assets", json={"symbol": "reliance.ns"}, headers=H).json()["currency"] == "INR"
    )


def test_update_all_appends_new_closes(db, live):
    hit = live.search("AAPL")[0]
    asset = prices.add_live_asset(db, live, hit)
    last = repo.latest_price_date_for(db, asset.id)
    assert last >= date.today() - timedelta(days=3)
    asset_old = asset
    from sqlalchemy import delete

    from app.models import DailyPrice

    db.execute(
        delete(DailyPrice).where(
            DailyPrice.asset_id == asset_old.id, DailyPrice.date > date.today() - timedelta(days=20)
        )
    )
    db.commit()
    out = prices.update_all(db, live)
    assert out["prices_added"] > 0 and not [f for f in out["failed"] if "AAPL" in f]
    assert repo.latest_price_date_for(db, asset.id) == last
    assert prices.update_all(db, live)["prices_added"] == 0  # idempotent


def test_admin_update_requires_secret(client, live, monkeypatch):
    import app.api.market as market
    from app.config import get_settings

    called = []
    monkeypatch.setattr(market, "_update_job", lambda provider: called.append(1))
    monkeypatch.setattr(get_settings(), "cron_secret", "")
    assert client.post("/api/v1/admin/update-prices", headers={"X-Cron-Secret": ""}).status_code == 403
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret")
    assert client.post("/api/v1/admin/update-prices", headers={"X-Cron-Secret": "wrong"}).status_code == 403
    assert client.post("/api/v1/admin/update-prices", headers={"X-Cron-Secret": "s3cret"}).status_code == 202
    assert called == [1]


def test_twelve_data_parsing():
    def handler(req: httpx.Request):
        if req.url.path.endswith("symbol_search"):
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "data": [
                        {
                            "symbol": "RELIANCE",
                            "instrument_name": "Reliance",
                            "mic_code": "XNSE",
                            "currency": "INR",
                            "instrument_type": "Common Stock",
                        },
                        {
                            "symbol": "SPY",
                            "instrument_name": "SPDR S&P 500",
                            "mic_code": "ARCX",
                            "currency": "USD",
                            "instrument_type": "ETF",
                        },
                        {
                            "symbol": "BTC",
                            "instrument_name": "Bitcoin",
                            "mic_code": "",
                            "currency": "USD",
                            "instrument_type": "Digital Currency",
                        },
                        {
                            "symbol": "X",
                            "instrument_name": "Euro stock",
                            "mic_code": "XPAR",
                            "currency": "EUR",
                            "instrument_type": "Common Stock",
                        },
                    ],
                },
            )
        assert req.url.params["mic_code"] == "XNSE" and req.url.params["symbol"] == "RELIANCE"
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "values": [
                    {"datetime": "2025-01-02", "close": "1234.5"},
                    {"datetime": "2025-01-03", "close": "1240.25"},
                ],
            },
        )

    p = TwelveDataProvider("k", httpx.Client(transport=httpx.MockTransport(handler)))
    hits = {h.symbol: h for h in p.search("x")}
    assert set(hits) == {"RELIANCE.NS", "SPY"} and hits["SPY"].asset_type == "ETF"
    from app.models import Asset

    a = Asset(symbol="RELIANCE.NS", name="r", asset_type="STOCK", currency="INR", exchange="XNSE")
    assert list(p.daily_closes(a, date(2025, 1, 1), date(2025, 1, 5))) == [
        (date(2025, 1, 2), D("1234.5")),
        (date(2025, 1, 3), D("1240.25")),
    ]


def test_twelve_data_error_and_rate_limit_retry():
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, json={"code": 429, "status": "error", "message": "limit"})
        return httpx.Response(200, json={"status": "error", "code": 400, "message": "bad symbol"})

    p = TwelveDataProvider("k", httpx.Client(transport=httpx.MockTransport(handler)))
    p.sleep = lambda s: None
    from app.services.live_data import ProviderError

    with pytest.raises(ProviderError, match="bad symbol"):
        p.search("x")
    assert len(calls) == 2


def test_mfapi_parsing_filters_idcw_and_orders_oldest_first():
    def handler(req):
        if "search" in req.url.path:
            return httpx.Response(
                200,
                json=[
                    {"schemeCode": 1, "schemeName": "Fund - Direct Plan - Growth"},
                    {"schemeCode": 2, "schemeName": "Fund - Monthly IDCW Payout"},
                ],
            )
        return httpx.Response(
            200,
            json={
                "data": [
                    {"date": "03-01-2025", "nav": "12.5"},
                    {"date": "02-01-2025", "nav": "12.0"},
                    {"date": "01-01-2025", "nav": "0"},
                ]
            },
        )

    p = MfApiProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    hits = p.search("fund")
    assert (
        [h.symbol for h in hits] == ["MF-1"]
        and hits[0].currency == "INR"
        and hits[0].asset_type == "MUTUAL_FUND"
    )
    from app.models import Asset

    a = Asset(symbol="MF-1", name="f", asset_type="MUTUAL_FUND", currency="INR", exchange="AMFI")
    assert list(p.daily_closes(a, date(2025, 1, 1), date(2025, 1, 31))) == [
        (date(2025, 1, 2), D("12.0")),
        (date(2025, 1, 3), D("12.5")),
    ]


def test_demo_does_not_block_a_real_portfolio_and_can_be_abandoned(client):
    demo = new_portfolio(client, demo=True)
    real = new_portfolio(client)  # a real USD portfolio alongside the USD demo
    assert {p["is_demo"] for p in client.get(BASE, headers=H).json()} == {True, False}
    assert client.delete(f"{BASE}/{demo}", headers=auth("intruder")).status_code == 404
    assert client.delete(f"{BASE}/{demo}", headers=H).status_code == 204
    assert client.get(f"{BASE}/{demo}", headers=H).status_code == 404
    assert [p["id"] for p in client.get(BASE, headers=H).json()] == [real]
    again = new_portfolio(client, demo=True)  # the demo slot is free again
    assert client.get(f"{BASE}/{again}/summary", headers=H).status_code == 200


def test_deleting_a_portfolio_removes_its_data(client, db):
    from sqlalchemy import func, select

    from app.models import SipPlan, Transaction

    pid = new_portfolio(client, demo=True)
    assert db.scalar(select(func.count()).select_from(SipPlan)) == 1
    assert client.delete(f"{BASE}/{pid}", headers=H).status_code == 204
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Transaction)) == 0
    assert db.scalar(select(func.count()).select_from(SipPlan)) == 0


# ---- the "vs benchmark" line must be real, or honestly absent ------------------------------------


def _trade_history(client, pid, symbol="ACME", price="50"):
    client.post(
        f"{BASE}/{pid}/transactions",
        headers=H,
        json={"trade_date": "2025-06-02", "type": "DEPOSIT", "cash_amount": "50000"},
    )
    for d in ("2025-06-03", "2025-07-01"):
        client.post(
            f"{BASE}/{pid}/transactions",
            headers=H,
            json={"trade_date": d, "type": "BUY", "symbol": symbol, "quantity": "10", "price": price},
        )


def test_demo_portfolio_uses_a_labelled_fictional_benchmark(client):
    pid = new_portfolio(client, demo=True)
    p = client.get(f"{BASE}/{pid}/performance?range=All", headers=H).json()
    assert p["benchmark_is_sample"] and p["benchmark_available"] and p["benchmark_symbol"] == "BNCH"
    assert p["series"][-1]["benchmark_index"] is not None


def test_real_portfolio_never_gets_the_fictional_benchmark(client):
    pid = new_portfolio(client)  # real USD portfolio, live data not configured
    _trade_history(client, pid)
    p = client.get(f"{BASE}/{pid}/performance?range=All", headers=H).json()
    assert p["benchmark_symbol"] == "SPY" and not p["benchmark_available"] and not p["benchmark_is_sample"]
    assert all(pt["benchmark_index"] is None for pt in p["series"]) and p["series"]
    m = p["metrics"]["benchmark_cumulative_return"]
    assert m["value"] is None and "fictional" in m["reason"]
    assert (
        p["metrics"]["cumulative_return"]["value"] is not None
    )  # the portfolio's own numbers are unaffected


def test_real_benchmark_is_loaded_when_a_real_portfolio_is_created(client, live):
    pid = new_portfolio(client)
    assert client.get("/api/v1/assets/search?q=SPY", headers=H).json()["results"][0]["in_db"]
    _trade_history(client, pid, symbol="AAPL", price="100")
    client.post("/api/v1/assets", json={"symbol": "AAPL"}, headers=H)
    p = client.get(f"{BASE}/{pid}/performance?range=All", headers=H).json()
    assert p["benchmark_available"] and not p["benchmark_is_sample"] and "SPDR" in p["benchmark_name"]
    assert p["series"][-1]["benchmark_index"] is not None
    assert p["metrics"]["benchmark_cumulative_return"]["value"] is not None


def test_indian_mutual_fund_can_be_the_inr_benchmark(client, monkeypatch):
    from app.config import get_settings
    from tests.test_imports import FundProvider

    monkeypatch.setattr(get_settings(), "benchmark_inr", "MF-1")
    app.dependency_overrides[get_provider] = lambda: FundProvider()
    new_portfolio(client, "INR")
    hit = client.get("/api/v1/assets/search?q=MF-1", headers=H).json()["results"]
    assert hit and hit[0]["symbol"] == "MF-1" and hit[0]["in_db"] and hit[0]["asset_type"] == "MUTUAL_FUND"
