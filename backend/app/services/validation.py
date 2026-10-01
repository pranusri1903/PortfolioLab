"""Field-level transaction validation shared by the JSON API and CSV import."""

import hashlib
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.calculations.ledger import ALL_TYPES, BUY, CASH_TYPES, DIVIDEND, SELL, TRADE_TYPES

MAX_ABS = Decimal("1e12")


def to_utc_datetime(d: date | datetime) -> datetime:
    """Date-only values mean 00:00 UTC; aware datetimes are converted to UTC;
    naive datetimes are assumed to already be UTC."""
    if isinstance(d, datetime):
        return d.astimezone(UTC) if d.tzinfo else d.replace(tzinfo=UTC)
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def check_decimal(name: str, v: Decimal | None, *, places: int, allow_zero: bool, errors: list[str]) -> None:
    if v is None:
        return
    if not v.is_finite():
        errors.append(f"{name} must be a finite number")
        return
    if abs(v) >= MAX_ABS:
        errors.append(f"{name} is too large")
    if v.as_tuple().exponent < -places:  # type: ignore[operator]
        errors.append(f"{name} has more than {places} decimal places")
    if v < 0 or (v == 0 and not allow_zero):
        errors.append(f"{name} must be {'non-negative' if allow_zero else 'greater than zero'}")


def validate_fields(
    *,
    type: str,
    symbol: str | None,
    quantity: Decimal | None,
    price: Decimal | None,
    fee: Decimal,
    cash_amount: Decimal | None,
) -> list[str]:
    errors: list[str] = []
    if type not in ALL_TYPES:
        return [f"Unknown type '{type}'"]
    check_decimal("quantity", quantity, places=8, allow_zero=False, errors=errors)
    check_decimal("price", price, places=6, allow_zero=False, errors=errors)
    check_decimal("fee", fee, places=4, allow_zero=True, errors=errors)
    check_decimal("cash_amount", cash_amount, places=4, allow_zero=False, errors=errors)

    if type in TRADE_TYPES:
        if not symbol:
            errors.append(f"{type} requires a symbol")
        if quantity is None:
            errors.append(f"{type} requires quantity")
        if price is None:
            errors.append(f"{type} requires price")
        if cash_amount is not None:
            errors.append(f"{type} must not have cash_amount")
    else:
        if cash_amount is None:
            errors.append(f"{type} requires cash_amount")
        if quantity is not None or price is not None:
            errors.append(f"{type} must not have quantity or price")
        if fee != 0:
            errors.append(f"{type} must not have a fee")
        if type == DIVIDEND and not symbol:
            errors.append("DIVIDEND requires a symbol")
        if type in CASH_TYPES - {DIVIDEND} and symbol:
            errors.append(f"{type} must not have a symbol")
    return errors


def _norm(d: Decimal | None) -> str:
    return "" if d is None else format(d.normalize(), "f")


def fingerprint(
    portfolio_id: uuid.UUID,
    *,
    trade_date: date | datetime,
    type: str,
    symbol: str | None,
    quantity: Decimal | None,
    price: Decimal | None,
    fee: Decimal,
    cash_amount: Decimal | None,
) -> str:
    """Deterministic duplicate key. Notes are deliberately excluded."""
    parts = [
        str(portfolio_id),
        to_utc_datetime(trade_date).date().isoformat(),
        type,
        symbol or "",
        _norm(quantity),
        _norm(price),
        _norm(fee),
        _norm(cash_amount),
    ]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


__all__ = [
    "BUY",
    "SELL",
    "check_decimal",
    "fingerprint",
    "to_utc_datetime",
    "validate_fields",
]
