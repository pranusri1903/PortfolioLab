import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TxType = Literal["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAWAL", "FEE"]
RangeKey = Literal["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "All"]


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    currency: Literal["USD", "INR"] = "USD"
    load_demo_data: bool = False


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    base_currency: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    name: str
    asset_type: str
    currency: str
    exchange: str | None


class TransactionIn(BaseModel):
    trade_date: date | datetime
    type: TxType
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal = Decimal("0")
    cash_amount: Decimal | None = None
    notes: str | None = Field(default=None, max_length=500)


class QuickStartHolding(BaseModel):
    symbol: str
    quantity: Decimal
    average_price: Decimal
    date: date


class QuickStart(BaseModel):
    cash: Decimal = Decimal("0")
    holdings: list[QuickStartHolding] = Field(default_factory=list, max_length=100)


class SipCreate(BaseModel):
    symbol: str
    amount: Decimal
    day_of_month: int = 5
    start_date: date
    end_date: date | None = None


class SipPatch(BaseModel):
    active: bool | None = None
    amount: Decimal | None = None
    end_date: date | None = None


class TransactionPatch(BaseModel):
    trade_date: date | datetime | None = None
    type: TxType | None = None
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal | None = None
    cash_amount: Decimal | None = None
    notes: str | None = Field(default=None, max_length=500)


class TransactionOut(BaseModel):
    id: uuid.UUID
    trade_date: datetime
    type: TxType
    symbol: str | None
    asset_name: str | None
    quantity: Decimal | None
    price: Decimal | None
    fee: Decimal
    cash_amount: Decimal | None
    notes: str | None
    created_at: datetime


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    page_size: int


class ImportRow(BaseModel):
    row_number: int  # 1-based data row; the header is row 0 (file line = row_number + 1)
    status: Literal["valid", "invalid", "duplicate"]
    reasons: list[str] = []
    data: dict[str, str | None]
    resolved_symbol: str | None = None
    resolved_name: str | None = None
    will_add_asset: bool = False  # live-priced asset not in our database yet; added when you confirm


class ImportCounts(BaseModel):
    imported: int
    skipped: int  # duplicates
    rejected: int  # invalid rows


class ImportResponse(BaseModel):
    committed: bool
    total_rows: int
    valid: int
    invalid: int
    duplicate: int
    rows: list[ImportRow]
    result: ImportCounts | None = None
