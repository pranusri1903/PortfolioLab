import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Fixed-precision decimals only: no floats for financial values.
MONEY = Numeric(20, 4)
PRICE = Numeric(20, 6)
QTY = Numeric(24, 8)


def _now() -> datetime:
    return datetime.now(UTC)


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (Index("ix_portfolios_owner_id", "owner_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    is_demo: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)  # STOCK | ETF
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    exchange: Mapped[str | None] = mapped_column(String(16))  # MIC code; NULL for sample assets


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_portfolio_date", "portfolio_id", "trade_date"),
        Index("ix_transactions_asset_id", "asset_id"),
        Index("ix_transactions_fingerprint", "portfolio_id", "fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Stored as UTC. Date-only inputs (CSV, forms) are interpreted as 00:00 UTC.
    trade_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(QTY, nullable=True)
    price: Mapped[Decimal | None] = mapped_column(PRICE, nullable=True)
    fee: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=Decimal("0"))
    cash_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    sip_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sip_plans.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    asset: Mapped[Asset | None] = relationship(lazy="joined")


class SipPlan(Base):
    """Recurring monthly investment. Each installment becomes a DEPOSIT + BUY pair."""

    __tablename__ = "sip_plans"
    __table_args__ = (Index("ix_sip_plans_portfolio", "portfolio_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"))
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"))
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    day_of_month: Mapped[int] = mapped_column(nullable=False)  # 1-28
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    asset: Mapped[Asset] = relationship(lazy="joined")


class DailyPrice(Base):
    __tablename__ = "daily_prices"
    __table_args__ = (
        UniqueConstraint("asset_id", "date", name="uq_daily_prices_asset_date"),
        Index("ix_daily_prices_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[Decimal] = mapped_column(PRICE, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="demo")


class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    __table_args__ = (UniqueConstraint("portfolio_id", "date", name="uq_daily_snapshots_portfolio_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    market_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    total_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    external_cash_flow: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
