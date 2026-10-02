"""SIP (systematic investment plan): a recurring monthly investment into one asset.

Each installment on a scheduled day executes at the first NAV/close on or after that day and
is recorded as a DEPOSIT (the money paid in) plus a BUY of fractional units. Units are rounded
down, so a tiny remainder stays as cash. Running the SIP again never duplicates installments.
"""

import uuid
from datetime import date
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Portfolio, SipPlan, Transaction
from app.repositories import data as repo
from app.services.pricing import PriceBook
from app.services.snapshots import rebuild_snapshots
from app.services.validation import fingerprint, to_utc_datetime


def schedule(plan: SipPlan, until: date):
    y, m = plan.start_date.year, plan.start_date.month
    end = min(until, plan.end_date or until)
    while (d := date(y, m, plan.day_of_month)) <= end:
        if d >= plan.start_date:
            yield d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def materialize(s: Session, plan: SipPlan, today: date | None = None) -> int:
    """Create any missing installments up to today. Returns how many were added."""
    if not plan.active:
        return 0
    book = PriceBook.load(s, [plan.asset_id])
    done = {
        t.trade_date.date()
        for t in repo.all_transactions(s, plan.portfolio_id)
        if t.sip_plan_id == plan.id and t.type == "BUY"
    }
    added = 0
    for due in schedule(plan, today or date.today()):
        nav = book.on_or_after(plan.asset_id, due)
        if nav is None or nav.price_date in done:
            continue
        units = (plan.amount / nav.close).quantize(Decimal("1e-8"), rounding=ROUND_DOWN)
        if units <= 0:
            continue
        for kind, qty, price, cash in (("DEPOSIT", None, None, plan.amount), ("BUY", units, nav.close, None)):
            s.add(
                Transaction(
                    portfolio_id=plan.portfolio_id,
                    asset_id=plan.asset_id if kind == "BUY" else None,
                    type=kind,
                    trade_date=to_utc_datetime(nav.price_date),
                    quantity=qty,
                    price=price,
                    fee=Decimal(0),
                    cash_amount=cash,
                    sip_plan_id=plan.id,
                    notes=f"SIP {due:%Y-%m}",
                    fingerprint=fingerprint(
                        plan.portfolio_id,
                        trade_date=nav.price_date,
                        type=kind,
                        symbol=plan.asset.symbol if kind == "BUY" else None,
                        quantity=qty,
                        price=price,
                        fee=Decimal(0),
                        cash_amount=cash,
                    ),
                )
            )
        done.add(nav.price_date)
        added += 1
    s.flush()
    return added


def create_plan(
    s: Session,
    p: Portfolio,
    *,
    symbol: str,
    amount: Decimal,
    day_of_month: int,
    start_date: date,
    end_date: date | None,
) -> SipPlan:
    asset = repo.get_asset(s, symbol.upper())
    if asset is None:
        raise ApiError(422, "unknown_symbol", f"Unknown symbol '{symbol}'.")
    if asset.currency != p.base_currency:
        raise ApiError(422, "currency_mismatch", f"{asset.symbol} trades in {asset.currency}.")
    if amount <= 0 or not 1 <= day_of_month <= 28:
        raise ApiError(422, "invalid_sip", "Amount must be positive and the day between 1 and 28.")
    if end_date and end_date < start_date:
        raise ApiError(422, "invalid_sip", "End date is before the start date.")
    plan = SipPlan(
        portfolio_id=p.id,
        asset_id=asset.id,
        amount=amount,
        day_of_month=day_of_month,
        start_date=start_date,
        end_date=end_date,
    )
    plan.asset = asset
    s.add(plan)
    s.flush()
    materialize(s, plan)
    rebuild_snapshots(s, p.id)
    s.commit()
    return plan


def run_all_sips(s: Session, portfolio_id: uuid.UUID | None = None) -> int:
    q = select(SipPlan).where(SipPlan.active.is_(True))
    if portfolio_id:
        q = q.where(SipPlan.portfolio_id == portfolio_id)
    total = 0
    for plan in s.scalars(q).unique().all():
        n = materialize(s, plan)
        if n:
            rebuild_snapshots(s, plan.portfolio_id)
        total += n
    s.commit()
    return total


def plan_stats(s: Session, p: Portfolio) -> list:
    from app.calculations.xirr import xirr
    from app.schemas.analytics import SipOut

    as_of = repo.latest_price_date(s, p.base_currency)
    rows = repo.all_transactions(s, p.id)
    out = []
    for plan in s.scalars(
        select(SipPlan).where(SipPlan.portfolio_id == p.id).order_by(SipPlan.created_at)
    ).unique():
        buys = [t for t in rows if t.sip_plan_id == plan.id and t.type == "BUY"]
        cost = {t.id: (t.quantity or Decimal(0)) * (t.price or Decimal(0)) for t in buys}
        units = sum((t.quantity or Decimal(0) for t in buys), Decimal(0))
        invested = sum(cost.values(), Decimal(0))
        lk = PriceBook.load(s, [plan.asset_id]).at(plan.asset_id, as_of) if as_of else None
        value = units * lk.close if lk else None
        flows = [(t.trade_date.date(), float(-cost[t.id])) for t in buys]
        if value and as_of:
            flows.append((as_of, float(value)))
        nxt = (
            next((d for d in schedule(plan, date(2100, 1, 1)) if as_of and d > as_of), None)
            if plan.active
            else None
        )
        out.append(
            SipOut(
                id=str(plan.id),
                symbol=plan.asset.symbol,
                name=plan.asset.name,
                asset_type=plan.asset.asset_type,
                amount=plan.amount,
                day_of_month=plan.day_of_month,
                start_date=plan.start_date,
                end_date=plan.end_date,
                active=plan.active,
                installments=len(buys),
                invested=invested.quantize(Decimal("0.0001")),
                units=units,
                current_value=value and value.quantize(Decimal("0.0001")),
                gain_loss=(value - invested).quantize(Decimal("0.0001")) if value is not None else None,
                xirr=xirr(flows),
                next_date=nxt,
            )
        )
    return out
