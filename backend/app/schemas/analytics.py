from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.portfolio import PortfolioOut, TransactionOut

PriceStatus = Literal["ok", "stale", "unavailable"]


class HoldingOut(BaseModel):
    symbol: str
    name: str
    asset_type: str
    quantity: Decimal
    average_cost: Decimal
    cost_basis: Decimal
    latest_price: Decimal | None
    price_date: date | None
    price_status: PriceStatus
    market_value: Decimal | None
    unrealized_gain_loss: Decimal | None
    unrealized_gain_loss_pct: float | None
    weight: float | None


class HoldingsResponse(BaseModel):
    as_of: date | None
    is_sample_data: bool
    value_complete: bool
    unavailable_symbols: list[str]
    holdings: list[HoldingOut]


class PositionPoint(BaseModel):
    date: date
    quantity: Decimal
    cost_basis: Decimal


class PricePoint(BaseModel):
    date: date
    close: Decimal


class HoldingDetail(BaseModel):
    holding: HoldingOut | None  # None when the position is fully closed
    symbol: str
    name: str
    asset_type: str
    is_sample_data: bool
    price_source: str | None
    position_history: list[PositionPoint]
    price_history: list[PricePoint]
    transactions: list[TransactionOut]


class AllocationSlice(BaseModel):
    key: str
    label: str
    value: Decimal
    weight: float


class AllocationResponse(BaseModel):
    as_of: date | None
    is_sample_data: bool
    value_complete: bool
    by_holding: list[AllocationSlice]
    by_asset_type: list[AllocationSlice]


class MetricOut(BaseModel):
    value: float | None
    reason: str | None = None


class Metrics(BaseModel):
    cumulative_return: MetricOut
    annualized_volatility: MetricOut
    sharpe_ratio: MetricOut
    max_drawdown: MetricOut
    benchmark_cumulative_return: MetricOut


class SeriesPoint(BaseModel):
    date: date
    total_value: Decimal
    portfolio_index: float
    benchmark_index: float | None


class PerformanceResponse(BaseModel):
    range: str
    start_date: date | None
    end_date: date | None
    partial: bool  # requested range starts before available history
    is_sample_data: bool
    benchmark_symbol: str
    series: list[SeriesPoint]
    metrics: Metrics
    zero_value_days: int
    risk_free_rate: float
    assumptions: list[str]


class SummaryResponse(BaseModel):
    portfolio: PortfolioOut
    as_of: date | None
    data_updated_at: datetime | None
    is_sample_data: bool
    value_complete: bool
    unavailable_symbols: list[str]
    total_value: Decimal
    market_value: Decimal
    cash_balance: Decimal
    net_contributions: Decimal
    total_gain_loss: Decimal
    total_gain_loss_pct: float | None
    range: str
    period_return: MetricOut
    metrics: Metrics
    transaction_count: int
    realized_gain_loss: Decimal
    dividend_income: Decimal
    fees_paid: Decimal


class MonthlyReturn(BaseModel):
    month: str  # YYYY-MM
    portfolio: float | None
    benchmark: float | None


class MonthlyReturnsResponse(BaseModel):
    is_sample_data: bool
    months: list[MonthlyReturn]
