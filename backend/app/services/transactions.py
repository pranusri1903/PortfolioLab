import uuid
from datetime import date
from decimal import ROUND_CEILING, Decimal

from sqlalchemy.orm import Session

from app.calculations.ledger import ZERO, Txn, replay
from app.errors import ApiError
from app.models import Portfolio, Transaction
from app.repositories import data as repo
from app.schemas.portfolio import QuickStart, TransactionIn, TransactionOut, TransactionPatch
from app.services.ledger_io import aware, to_txn, to_txns
from app.services.snapshots import rebuild_snapshots
from app.services.validation import fingerprint, to_utc_datetime, validate_fields


def to_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        **{c: getattr(t, c) for c in ("id", "type", "quantity", "price", "fee", "cash_amount", "notes")},
        trade_date=aware(t.trade_date),
        symbol=t.asset and t.asset.symbol,
        asset_name=t.asset and t.asset.name,
        created_at=aware(t.created_at),
    )


def _columns(s: Session, pid: uuid.UUID, v: dict) -> dict:
    """Validate raw fields and return Transaction column values."""
    v = {**v, "symbol": v["symbol"].strip().upper() if v.get("symbol") else None}
    v["fee"] = v["fee"] if v["fee"] is not None else ZERO
    if errors := validate_fields(
        **{k: v[k] for k in ("type", "symbol", "quantity", "price", "fee", "cash_amount")}
    ):
        raise ApiError(422, "invalid_transaction", "; ".join(errors), [{"reason": e} for e in errors])
    asset = repo.get_asset(s, v["symbol"]) if v["symbol"] else None
    if v["symbol"] and not asset:
        raise ApiError(422, "unknown_symbol", f"Unknown symbol '{v['symbol']}'.")
    return dict(
        type=v["type"],
        asset=asset,
        quantity=v["quantity"],
        price=v["price"],
        fee=v["fee"],
        cash_amount=v["cash_amount"],
        notes=v["notes"],
        trade_date=to_utc_datetime(v["trade_date"]),
        fingerprint=fingerprint(
            pid,
            **{k: v[k] for k in ("trade_date", "type", "symbol", "quantity", "price", "fee", "cash_amount")},
        ),
    )


def _save(s: Session, p: Portfolio, t: Transaction, cols: dict, exclude: uuid.UUID | None) -> Transaction:
    asset = cols["asset"]
    if asset and asset.currency != p.base_currency:
        raise ApiError(
            422,
            "currency_mismatch",
            f"{asset.symbol} trades in {asset.currency}; this portfolio is in {p.base_currency}.",
        )
    others = [r for r in repo.all_transactions(s, p.id) if r.id != exclude]
    probe = Transaction(portfolio_id=p.id, **cols)  # transient; validates the new ledger
    replay(
        [
            *to_txns(others),
            Txn(
                type=probe.type,
                trade_date=probe.trade_date,
                symbol=cols["asset"] and cols["asset"].symbol,
                quantity=probe.quantity,
                price=probe.price,
                fee=probe.fee,
                cash_amount=probe.cash_amount,
                seq=len(others) + 1,
            ),
        ]
    )
    for k, val in cols.items():
        setattr(t, k, val)
    s.add(t)
    s.flush()
    rebuild_snapshots(s, p.id)
    s.commit()
    return t


def quick_start(s: Session, p: Portfolio, body: QuickStart) -> int:
    """Turn "what I own" into a ledger: one DEPOSIT covering cost + cash, then one BUY per holding."""
    if repo.all_transactions(s, p.id):
        raise ApiError(409, "not_empty", "Quick start only works on a portfolio with no transactions.")
    if not body.holdings and body.cash <= 0:
        raise ApiError(422, "invalid_transaction", "Enter at least one holding or a cash balance.")
    buys = [
        _columns(
            s,
            p.id,
            dict(
                type="BUY",
                trade_date=h.date,
                symbol=h.symbol,
                quantity=h.quantity,
                price=h.average_price,
                fee=ZERO,
                cash_amount=None,
                notes="Quick start",
            ),
        )
        for h in body.holdings
    ]
    total = sum((h.quantity * h.average_price for h in body.holdings), ZERO) + body.cash
    start = min((h.date for h in body.holdings), default=date.today())
    deposit = _columns(
        s,
        p.id,
        dict(
            type="DEPOSIT",
            trade_date=start,
            symbol=None,
            quantity=None,
            price=None,
            fee=ZERO,
            cash_amount=total.quantize(Decimal("0.0001"), ROUND_CEILING),
            notes="Quick start: opening balance",
        ),
    )
    for c in (deposit, *buys):
        if c["asset"] and c["asset"].currency != p.base_currency:
            raise ApiError(422, "currency_mismatch", f"{c['asset'].symbol} trades in {c['asset'].currency}.")
    txns = [Transaction(portfolio_id=p.id, **c) for c in (deposit, *buys)]
    replay([to_txn(t, i) for i, t in enumerate(txns)])
    s.add_all(txns)
    s.flush()
    rebuild_snapshots(s, p.id)
    s.commit()
    return len(txns)


def create_transaction(s: Session, p: Portfolio, body: TransactionIn) -> Transaction:
    return _save(s, p, Transaction(portfolio_id=p.id), _columns(s, p.id, body.model_dump()), None)


def update_transaction(s: Session, p: Portfolio, t: Transaction, body: TransactionPatch) -> Transaction:
    cur = {
        "trade_date": t.trade_date,
        "type": t.type,
        "symbol": t.asset and t.asset.symbol,
        "quantity": t.quantity,
        "price": t.price,
        "fee": t.fee,
        "cash_amount": t.cash_amount,
        "notes": t.notes,
    }
    return _save(s, p, t, _columns(s, p.id, {**cur, **body.model_dump(exclude_unset=True)}), t.id)


def delete_transaction(s: Session, p: Portfolio, t: Transaction) -> None:
    replay(to_txns([r for r in repo.all_transactions(s, p.id) if r.id != t.id]))
    s.delete(t)
    s.flush()
    rebuild_snapshots(s, p.id)
    s.commit()
