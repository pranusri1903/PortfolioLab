"""Bridge between ORM rows and the pure ledger module."""

from datetime import UTC

from app.calculations.ledger import ZERO, Txn
from app.models import Transaction


def aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def to_txn(t: Transaction, seq: int = 0) -> Txn:
    return Txn(
        type=t.type,
        trade_date=aware(t.trade_date),
        symbol=t.asset.symbol if t.asset else None,
        quantity=t.quantity,
        price=t.price,
        fee=t.fee if t.fee is not None else ZERO,
        cash_amount=t.cash_amount,
        seq=seq,
    )


def to_txns(rows: list[Transaction]) -> list[Txn]:
    # rows arrive ordered by (trade_date, created_at); seq preserves creation order
    return [to_txn(t, i) for i, t in enumerate(rows)]
