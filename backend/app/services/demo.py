import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calculations.ledger import replay
from app.models import Asset, DailyPrice, Portfolio, Transaction
from app.repositories import data as repo
from app.services.ledger_io import to_txns
from app.services.market_data import DEMO_ASSETS, DEMO_END, DEMO_START, DemoProvider
from app.services.snapshots import rebuild_snapshots
from app.services.validation import fingerprint, to_utc_datetime


def seed_market_data(s: Session, provider=DemoProvider()) -> None:
    """Idempotent: loads assets and sample daily prices if missing."""
    for sym, (name, kind, *_) in DEMO_ASSETS.items():
        asset = repo.get_asset(s, sym) or Asset(symbol=sym, name=name, asset_type=kind)
        s.add(asset)
        s.flush()
        have = set(s.scalars(select(DailyPrice.date).where(DailyPrice.asset_id == asset.id)))
        s.add_all(
            DailyPrice(asset_id=asset.id, date=d, close=c, source=provider.source)
            for d, c in provider.daily_closes(sym, DEMO_START, DEMO_END)
            if d not in have
        )
    s.commit()


def load_demo_transactions(s: Session, p: Portfolio) -> None:
    """Deterministic sample history: a deposit, a few buys at that day's close, monthly
    contributions, quarterly dividends, and one partial sale."""
    assets = repo.assets_by_symbol(s)
    close = {
        (a.symbol, r.date): r.close
        for a in assets.values()
        for r in s.scalars(select(DailyPrice).where(DailyPrice.asset_id == a.id))
    }
    on_or_after = lambda sym, d: next(  # noqa: E731
        (dd, close[sym, dd]) for dd in sorted(x for (sy, x) in close if sy == sym and x >= d)
    )
    rows: list[dict] = [dict(type="DEPOSIT", trade_date=date(2023, 1, 3), cash_amount=Decimal(40000))]
    for sym, qty, d in [
        ("BNCH", 100, date(2023, 1, 4)),
        ("ACME", 80, date(2023, 1, 4)),
        ("CRST", 40, date(2023, 2, 1)),
        ("DYNA", 150, date(2023, 6, 1)),
        ("BOND", 60, date(2023, 6, 1)),
        ("BOLT", 50, date(2024, 3, 1)),
    ]:
        day, px = on_or_after(sym, d)
        rows.append(
            dict(type="BUY", symbol=sym, trade_date=day, quantity=Decimal(qty), price=px, fee=Decimal("1.00"))
        )
    for year in (2023, 2024, 2025, 2026):
        for month in range(1, 13):
            if date(year, month, 1) <= DEMO_END and (year, month) > (2023, 1):
                rows.append(dict(type="DEPOSIT", trade_date=date(year, month, 1), cash_amount=Decimal(1000)))
            if month in (3, 6, 9, 12) and date(year, month, 15) <= DEMO_END and year >= 2023:
                rows.append(
                    dict(
                        type="DIVIDEND",
                        symbol="ACME",
                        trade_date=date(year, month, 15),
                        cash_amount=Decimal("0.25") * 80,
                    )
                )
    day, px = on_or_after("DYNA", date(2025, 6, 2))
    rows.append(
        dict(type="SELL", symbol="DYNA", trade_date=day, quantity=Decimal(50), price=px, fee=Decimal("1.00"))
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
    txns = [
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
    ]
    s.add_all(txns)
    s.flush()
    replay(to_txns(repo.all_transactions(s, p.id)))  # fail loudly if the demo ledger is invalid
    rebuild_snapshots(s, p.id)
    s.commit()
