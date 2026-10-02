import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculations.ledger import replay
from app.models import Asset, DailyPrice, Portfolio, SipPlan, Transaction
from app.repositories import data as repo
from app.services.ledger_io import to_txns
from app.services.market_data import DEMO_ASSETS, DEMO_END, DEMO_START, DemoProvider
from app.services.sip import materialize
from app.services.snapshots import rebuild_snapshots
from app.services.validation import fingerprint, to_utc_datetime


def seed_market_data(s: Session, provider=None) -> None:
    """Idempotent: loads sample assets (USD and INR) and deterministic daily prices if missing."""
    provider = provider or DemoProvider()
    for sym, (name, kind, *_, cur) in DEMO_ASSETS.items():
        asset = repo.get_asset(s, sym) or Asset(symbol=sym, name=name, asset_type=kind, currency=cur)
        s.add(asset)
        s.flush()
        have = set(s.scalars(select(DailyPrice.date).where(DailyPrice.asset_id == asset.id)))
        s.add_all(
            DailyPrice(asset_id=asset.id, date=d, close=c, source=provider.source)
            for d, c in provider.daily_closes(asset, DEMO_START, DEMO_END)
            if d not in have
        )
    s.commit()


# Sample history per currency: (symbol, units, first buy on/after), dividend, one sale, SIP fund.
PLANS: dict[str, dict[str, Any]] = {
    "USD": dict(
        deposit=40000,
        monthly=1000,
        fee=Decimal("1.00"),
        dividend=("ACME", Decimal(20)),
        sell=("DYNA", 50),
        sip=("GRWF", Decimal(500)),
        buys=[
            ("BNCH", 100, date(2023, 1, 4)),
            ("ACME", 80, date(2023, 1, 4)),
            ("CRST", 40, date(2023, 2, 1)),
            ("DYNA", 150, date(2023, 6, 1)),
            ("BOND", 60, date(2023, 6, 1)),
            ("BOLT", 50, date(2024, 3, 1)),
        ],
    ),
    "INR": dict(
        deposit=3000000,
        monthly=50000,
        fee=Decimal("20"),
        dividend=("BHRT", Decimal(1200)),
        sell=("SWDS", 100),
        sip=("FLXF", Decimal(10000)),
        buys=[
            ("NIFB", 3000, date(2023, 1, 4)),
            ("BHRT", 100, date(2023, 1, 4)),
            ("INFX", 150, date(2023, 2, 1)),
            ("SWDS", 300, date(2023, 6, 1)),
            ("GSEC", 1500, date(2023, 6, 1)),
        ],
    ),
}


def load_demo_transactions(s: Session, p: Portfolio) -> None:
    """Deterministic sample history: deposit, buys at that day's close, monthly contributions,
    quarterly dividends, one partial sale, and a monthly SIP into a sample mutual fund."""
    plan = PLANS[p.base_currency]
    assets = repo.assets_by_symbol(s)
    syms = [b[0] for b in plan["buys"]] + [plan["sell"][0]]
    close = {
        (sym, r.date): r.close
        for sym in syms
        for r in s.scalars(select(DailyPrice).where(DailyPrice.asset_id == assets[sym].id))
    }

    def on_or_after(sym, d):
        return next((dd, close[sym, dd]) for dd in sorted(x for (sy, x) in close if sy == sym and x >= d))

    rows: list[dict] = [
        dict(type="DEPOSIT", trade_date=date(2023, 1, 3), cash_amount=Decimal(plan["deposit"]))
    ]
    for sym, qty, d in plan["buys"]:
        day, px = on_or_after(sym, d)
        rows.append(
            dict(type="BUY", symbol=sym, trade_date=day, quantity=Decimal(qty), price=px, fee=plan["fee"])
        )
    for year in (2023, 2024, 2025, 2026):
        for month in range(1, 13):
            if date(year, month, 1) <= DEMO_END and (year, month) > (2023, 1):
                rows.append(
                    dict(
                        type="DEPOSIT", trade_date=date(year, month, 1), cash_amount=Decimal(plan["monthly"])
                    )
                )
            if month in (3, 6, 9, 12) and date(year, month, 15) <= DEMO_END:
                rows.append(
                    dict(
                        type="DIVIDEND",
                        symbol=plan["dividend"][0],
                        trade_date=date(year, month, 15),
                        cash_amount=plan["dividend"][1],
                    )
                )
    sym, qty = plan["sell"]
    day, px = on_or_after(sym, date(2025, 6, 2))
    rows.append(
        dict(type="SELL", symbol=sym, trade_date=day, quantity=Decimal(qty), price=px, fee=plan["fee"])
    )
    full = [
        {
            "quantity": None,
            "price": None,
            "fee": Decimal(0),
            "cash_amount": None,
            "symbol": None,
            "notes": "Sample data",
            **r,
        }
        for r in rows
    ]
    s.add_all(
        Transaction(
            id=uuid.uuid4(),
            portfolio_id=p.id,
            asset=assets.get(r["symbol"]),
            trade_date=to_utc_datetime(r["trade_date"]),
            fingerprint=fingerprint(
                p.id,
                **{
                    k: r[k]
                    for k in ("trade_date", "type", "symbol", "quantity", "price", "fee", "cash_amount")
                },
            ),
            **{k: r[k] for k in ("type", "quantity", "price", "fee", "cash_amount", "notes")},
        )
        for r in full
    )
    s.flush()
    replay(to_txns(repo.all_transactions(s, p.id)))  # fail loudly if the demo ledger is invalid
    sym, amount = plan["sip"]
    sip = SipPlan(
        portfolio_id=p.id, asset_id=assets[sym].id, amount=amount, day_of_month=5, start_date=date(2023, 3, 1)
    )
    sip.asset = assets[sym]
    s.add(sip)
    s.flush()
    materialize(s, sip, DEMO_END)
    rebuild_snapshots(s, p.id)
    s.commit()
