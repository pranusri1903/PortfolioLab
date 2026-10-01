import io
from decimal import Decimal as D

from sqlalchemy import delete

from app.models import DailyPrice
from app.repositories import data as repo
from tests.conftest import auth

BASE = "/api/v1/portfolios"


def tx(client, pid, body, user="alice"):
    return client.post(f"{BASE}/{pid}/transactions", json=body, headers=auth(user))


def deposit(client, pid, amount=10000, date="2025-01-10"):
    return tx(client, pid, {"trade_date": date, "type": "DEPOSIT", "cash_amount": str(amount)})


def test_unauthenticated_requests_fail(client):
    assert client.get(BASE).status_code == 401
    assert client.get(BASE, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_cross_user_access_is_denied(client, portfolio):
    tid = deposit(client, portfolio).json()["id"]
    bob = auth("bob")
    for method, path in [
        ("get", ""),
        ("get", "/summary"),
        ("get", "/holdings"),
        ("get", "/performance"),
        ("get", "/allocation"),
        ("get", "/transactions"),
        ("get", "/transactions-export"),
        ("delete", f"/transactions/{tid}"),
    ]:
        assert getattr(client, method)(f"{BASE}/{portfolio}{path}", headers=bob).status_code == 404, path
    assert (
        client.patch(f"{BASE}/{portfolio}/transactions/{tid}", json={"notes": "x"}, headers=bob).status_code
        == 404
    )
    assert (
        tx(
            client, portfolio, {"trade_date": "2025-01-10", "type": "DEPOSIT", "cash_amount": "1"}, "bob"
        ).status_code
        == 404
    )
    assert client.get(BASE, headers=bob).json() == []
    assert client.get(f"{BASE}/{portfolio}/transactions", headers=auth()).json()["total"] == 1


def test_one_portfolio_per_user(client, portfolio):
    assert client.post(BASE, json={"name": "Two"}, headers=auth()).status_code == 409


def test_buy_sell_flow_updates_holdings(client, portfolio):
    deposit(client, portfolio, 10000)
    r = tx(
        client,
        portfolio,
        {
            "trade_date": "2025-01-13",
            "type": "BUY",
            "symbol": "ACME",
            "quantity": "10",
            "price": "50",
            "fee": "1",
        },
    )
    assert r.status_code == 201, r.text
    h = client.get(f"{BASE}/{portfolio}/holdings", headers=auth()).json()
    pos = h["holdings"][0]
    assert (
        D(pos["quantity"]) == 10 and D(pos["cost_basis"]) == D("501") and D(pos["average_cost"]) == D("50.1")
    )
    assert pos["price_status"] == "ok" and h["is_sample_data"]
    s = client.get(f"{BASE}/{portfolio}/summary", headers=auth()).json()
    assert D(s["cash_balance"]) == D("9499")
    assert D(s["market_value"]) + D(s["cash_balance"]) == D(s["total_value"])


def test_rejects_oversell_overdraw_and_bad_fields(client, portfolio):
    deposit(client, portfolio, 100)
    base = {"trade_date": "2025-01-13", "symbol": "ACME", "quantity": "10", "price": "50"}
    r = tx(client, portfolio, {**base, "type": "BUY"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "insufficient_cash"
    r = tx(client, portfolio, {**base, "type": "SELL"})
    assert r.json()["error"]["code"] == "insufficient_shares"
    assert (
        tx(client, portfolio, {**base, "type": "BUY", "symbol": "NOPE"}).json()["error"]["code"]
        == "unknown_symbol"
    )
    assert tx(client, portfolio, {**base, "type": "BUY", "quantity": "-1"}).status_code == 422
    assert tx(client, portfolio, {"trade_date": "2025-01-13", "type": "DEPOSIT"}).status_code == 422


def test_delete_that_strands_a_trade_is_rejected_and_edit_works(client, portfolio):
    dep = deposit(client, portfolio, 1000).json()["id"]
    tx(
        client,
        portfolio,
        {"trade_date": "2025-01-13", "type": "BUY", "symbol": "ACME", "quantity": "10", "price": "50"},
    )
    assert client.delete(f"{BASE}/{portfolio}/transactions/{dep}", headers=auth()).status_code == 422
    r = client.patch(f"{BASE}/{portfolio}/transactions/{dep}", json={"cash_amount": "100"}, headers=auth())
    assert r.status_code == 422  # would overdraw the later buy
    r = client.patch(f"{BASE}/{portfolio}/transactions/{dep}", json={"cash_amount": "2000"}, headers=auth())
    assert r.status_code == 200 and D(r.json()["cash_amount"]) == 2000


def test_transaction_list_filters_and_pagination(client, portfolio):
    deposit(client, portfolio, 5000)
    for d in ("2025-01-13", "2025-02-13", "2025-03-13"):
        tx(
            client,
            portfolio,
            {"trade_date": d, "type": "BUY", "symbol": "ACME", "quantity": "1", "price": "10"},
        )
    get = lambda q: client.get(f"{BASE}/{portfolio}/transactions?{q}", headers=auth()).json()  # noqa: E731
    assert get("type=BUY")["total"] == 3
    assert get("symbol=acme&date_from=2025-02-01&date_to=2025-02-28")["total"] == 1
    page = get("page=2&page_size=3")
    assert page["total"] == 4 and len(page["items"]) == 1


HEADER = "trade_date,type,symbol,quantity,price,fee,cash_amount,notes\n"


def imp(client, pid, csv_text, commit=False):
    return client.post(
        f"{BASE}/{pid}/transactions/import?commit={str(commit).lower()}",
        files={"file": ("t.csv", io.BytesIO(csv_text.encode()))},
        headers=auth(),
    )


def test_csv_preview_flags_every_problem_and_writes_nothing(client, portfolio):
    csv = HEADER + "\n".join(
        [
            "2025-01-10,DEPOSIT,,,,,5000,ok",
            "2025-13-40,DEPOSIT,,,,,5,bad date",
            "2025-01-11,BUY,ZZZZ,1,10,,,unknown symbol",
            "2025-01-11,BUY,ACME,abc,10,,,bad amount",
            "2025-01-10,DEPOSIT,,,,,5000,duplicate of row 1",
            "2025-01-12,BUY,ACME,1000,50,,,overdraw",
            "2025-01-12,BUY,ACME,10,50,1,,good",
        ]
    )
    r = imp(client, portfolio, csv).json()
    status = {x["row_number"]: x["status"] for x in r["rows"]}
    assert status == {
        1: "valid",
        2: "invalid",
        3: "invalid",
        4: "invalid",
        5: "duplicate",
        6: "invalid",
        7: "valid",
    }
    assert not r["committed"] and (r["valid"], r["invalid"], r["duplicate"]) == (2, 4, 1)
    assert client.get(f"{BASE}/{portfolio}/transactions", headers=auth()).json()["total"] == 0


def test_csv_commit_reports_counts_and_is_idempotent(client, portfolio):
    csv = (
        HEADER
        + "2025-01-10,DEPOSIT,,,,,600.00,Monthly\n2025-01-12,BUY,ACME,10,50.00,1.00,,Initial\nbad,row\n"
    )
    r = imp(client, portfolio, csv, commit=True).json()
    assert r["result"] == {"imported": 2, "skipped": 0, "rejected": 1}
    assert D(client.get(f"{BASE}/{portfolio}/summary", headers=auth()).json()["cash_balance"]) == D("99")
    again = imp(client, portfolio, csv, commit=True).json()
    assert again["result"] == {"imported": 0, "skipped": 2, "rejected": 1}


def test_csv_bad_header_rejected(client, portfolio):
    r = imp(client, portfolio, "date,type\n2025-01-01,BUY\n")
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_csv_header"


def test_export_round_trips_through_import(client, portfolio):
    deposit(client, portfolio, 500)
    csv = client.get(f"{BASE}/{portfolio}/transactions-export", headers=auth()).text
    assert csv.startswith(HEADER)
    assert imp(client, portfolio, csv).json()["duplicate"] == 1


def test_demo_portfolio_has_full_dashboard(client):
    pid = client.post(BASE, json={"name": "Demo", "load_demo_data": True}, headers=auth("demo")).json()["id"]
    h = auth("demo")
    s = client.get(f"{BASE}/{pid}/summary?range=1Y", headers=h).json()
    assert s["is_sample_data"] and s["value_complete"] and s["as_of"] == "2026-09-30"
    assert s["metrics"]["annualized_volatility"]["value"] > 0
    p = client.get(f"{BASE}/{pid}/performance?range=All", headers=h).json()
    assert p["series"][0]["portfolio_index"] == 100 and not p["partial"]
    assert p["series"][-1]["benchmark_index"] is not None
    one_m = client.get(f"{BASE}/{pid}/performance?range=1M", headers=h).json()
    assert 15 < len(one_m["series"]) < 30
    a = client.get(f"{BASE}/{pid}/allocation", headers=h).json()
    assert abs(sum(x["weight"] for x in a["by_holding"]) - 1) < 1e-9
    d = client.get(f"{BASE}/{pid}/holdings/ACME", headers=h).json()
    assert d["is_sample_data"] and d["price_history"] and d["position_history"]


def test_new_account_has_honest_empty_state(client, portfolio):
    p = client.get(f"{BASE}/{portfolio}/performance?range=1Y", headers=auth()).json()
    assert p["series"] == [] and p["metrics"]["cumulative_return"]["value"] is None
    assert p["metrics"]["cumulative_return"]["reason"]


def test_missing_price_is_flagged_not_zero(client, db):
    pid = client.post(BASE, json={"name": "P"}, headers=auth()).json()["id"]
    deposit(client, pid, 5000)
    tx(
        client,
        pid,
        {"trade_date": "2025-01-13", "type": "BUY", "symbol": "ACME", "quantity": "10", "price": "50"},
    )
    db.execute(delete(DailyPrice).where(DailyPrice.asset_id == repo.get_asset(db, "ACME").id))
    db.commit()
    h = client.get(f"{BASE}/{pid}/holdings", headers=auth()).json()
    assert h["holdings"][0]["price_status"] == "unavailable" and h["holdings"][0]["market_value"] is None
    assert h["unavailable_symbols"] == ["ACME"] and not h["value_complete"]
    s = client.get(f"{BASE}/{pid}/summary", headers=auth()).json()
    assert not s["value_complete"] and s["unavailable_symbols"] == ["ACME"]


def test_summary_income_and_monthly_returns(client):
    pid = client.post(BASE, json={"name": "Demo", "load_demo_data": True}, headers=auth("m")).json()["id"]
    s = client.get(f"{BASE}/{pid}/summary", headers=auth("m")).json()
    assert D(s["dividend_income"]) > 0 and D(s["fees_paid"]) >= 7 and D(s["realized_gain_loss"]) != 0
    mr = client.get(f"{BASE}/{pid}/performance/monthly", headers=auth("m")).json()
    assert len(mr["months"]) > 40 and mr["months"][0]["benchmark"] is not None
