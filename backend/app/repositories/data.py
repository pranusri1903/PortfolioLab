"""Database access. Every portfolio-scoped query filters by portfolio_id, and
portfolio lookup is always scoped to the authenticated owner."""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Asset, DailyPrice, DailySnapshot, Portfolio, Transaction


def get_owned_portfolio(s: Session, owner_id: str, portfolio_id: uuid.UUID) -> Portfolio | None:
    return s.scalar(select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.owner_id == owner_id))


def list_portfolios(s: Session, owner_id: str) -> list[Portfolio]:
    return list(
        s.scalars(select(Portfolio).where(Portfolio.owner_id == owner_id).order_by(Portfolio.created_at))
    )


def assets_by_symbol(s: Session) -> dict[str, Asset]:
    return {a.symbol: a for a in s.scalars(select(Asset))}


def get_asset(s: Session, symbol: str) -> Asset | None:
    return s.scalar(select(Asset).where(Asset.symbol == symbol))


def all_transactions(s: Session, portfolio_id: uuid.UUID) -> list[Transaction]:
    return list(
        s.scalars(
            select(Transaction)
            .where(Transaction.portfolio_id == portfolio_id)
            .order_by(Transaction.trade_date, Transaction.created_at)
        )
    )


def get_transaction(s: Session, portfolio_id: uuid.UUID, tx_id: uuid.UUID) -> Transaction | None:
    return s.scalar(
        select(Transaction).where(Transaction.portfolio_id == portfolio_id, Transaction.id == tx_id)
    )


def fingerprints(s: Session, portfolio_id: uuid.UUID) -> set[str]:
    return set(s.scalars(select(Transaction.fingerprint).where(Transaction.portfolio_id == portfolio_id)))


def query_transactions(
    s: Session,
    portfolio_id: uuid.UUID,
    *,
    symbol: str | None,
    tx_type: str | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> tuple[list[Transaction], int]:
    conds = [Transaction.portfolio_id == portfolio_id]
    if symbol:
        conds.append(Asset.symbol == symbol.upper())
    if tx_type:
        conds.append(Transaction.type == tx_type)
    if date_from:
        conds.append(Transaction.trade_date >= datetime.combine(date_from, time.min, tzinfo=UTC))
    if date_to:
        conds.append(
            Transaction.trade_date < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
        )
    base = select(Transaction).outerjoin(Asset, Transaction.asset_id == Asset.id).where(*conds)
    total = s.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = s.scalars(
        base.order_by(Transaction.trade_date.desc(), Transaction.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique()
    return list(rows), total


def prices_for_assets(s: Session, asset_ids: list[uuid.UUID]) -> list[DailyPrice]:
    if not asset_ids:
        return []
    return list(
        s.scalars(
            select(DailyPrice)
            .where(DailyPrice.asset_id.in_(asset_ids))
            .order_by(DailyPrice.asset_id, DailyPrice.date)
        )
    )


def latest_price_date(s: Session) -> date | None:
    return s.scalar(select(func.max(DailyPrice.date)))


def price_dates(s: Session, start: date) -> list[date]:
    return list(
        s.scalars(
            select(DailyPrice.date).where(DailyPrice.date >= start).distinct().order_by(DailyPrice.date)
        )
    )


def price_sources(s: Session, asset_ids: list[uuid.UUID]) -> set[str]:
    if not asset_ids:
        return set()
    return set(s.scalars(select(DailyPrice.source).where(DailyPrice.asset_id.in_(asset_ids)).distinct()))


def replace_snapshots(s: Session, portfolio_id: uuid.UUID, rows: list[DailySnapshot]) -> None:
    s.execute(delete(DailySnapshot).where(DailySnapshot.portfolio_id == portfolio_id))
    s.add_all(rows)


def snapshots(s: Session, portfolio_id: uuid.UUID) -> list[DailySnapshot]:
    return list(
        s.scalars(
            select(DailySnapshot)
            .where(DailySnapshot.portfolio_id == portfolio_id)
            .order_by(DailySnapshot.date)
        )
    )
