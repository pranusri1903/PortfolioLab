"""Pure ledger math: cash balance, positions, weighted-average cost basis.

No database or HTTP code lives here. All amounts are ``Decimal``.

Conventions (see README "Calculation definitions"):
- BUY   : cash -= qty * price + fee ; cost basis += qty * price + fee
- SELL  : cash += qty * price - fee ; cost basis -= cost_basis * (qty / held)
- DIVIDEND / DEPOSIT : cash += cash_amount
- WITHDRAWAL / FEE   : cash -= cash_amount
- Dividends never change share cost basis. Cost basis is an analytics
  convention (weighted average), not tax accounting.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

ZERO = Decimal("0")

BUY, SELL, DIVIDEND, DEPOSIT, WITHDRAWAL, FEE = (
    "BUY",
    "SELL",
    "DIVIDEND",
    "DEPOSIT",
    "WITHDRAWAL",
    "FEE",
)
TRADE_TYPES = {BUY, SELL}
CASH_TYPES = {DIVIDEND, DEPOSIT, WITHDRAWAL, FEE}
ALL_TYPES = TRADE_TYPES | CASH_TYPES

# Deterministic ordering for transactions that share a trade date:
# money in first, then trades, then money out.
_TYPE_RANK = {DEPOSIT: 0, DIVIDEND: 1, BUY: 2, SELL: 3, WITHDRAWAL: 4, FEE: 5}


class LedgerError(ValueError):
    """A transaction would violate a ledger rule (negative cash, oversell...)."""

    def __init__(self, message: str, code: str = "ledger_violation"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Txn:
    type: str
    trade_date: datetime
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal = ZERO
    cash_amount: Decimal | None = None
    seq: int = 0  # tie-breaker (creation order)


@dataclass
class Position:
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    realized: Decimal = ZERO
    dividends: Decimal = ZERO

    @property
    def average_cost(self) -> Decimal:
        return self.cost_basis / self.quantity if self.quantity else ZERO


@dataclass
class LedgerState:
    cash: Decimal = ZERO
    positions: dict[str, Position] = field(default_factory=dict)
    external_cash_flow: Decimal = ZERO  # cumulative deposits - withdrawals
    realized: Decimal = ZERO  # realized gain/loss on sells (net of fees)
    dividends: Decimal = ZERO
    fees: Decimal = ZERO  # trade fees + FEE transactions

    def held(self, symbol: str) -> Decimal:
        pos = self.positions.get(symbol)
        return pos.quantity if pos else ZERO


def sort_key(t: Txn) -> tuple:
    return (t.trade_date, _TYPE_RANK.get(t.type, 9), t.seq)


def sort_txns(txns: list[Txn]) -> list[Txn]:
    return sorted(txns, key=sort_key)


def cash_effect(t: Txn) -> Decimal:
    if t.type == BUY:
        return -(_req(t.quantity) * _req(t.price) + t.fee)
    if t.type == SELL:
        return _req(t.quantity) * _req(t.price) - t.fee
    if t.type in (DIVIDEND, DEPOSIT):
        return _req(t.cash_amount)
    if t.type in (WITHDRAWAL, FEE):
        return -_req(t.cash_amount)
    raise LedgerError(f"Unknown transaction type {t.type}", "invalid_type")


def external_flow(t: Txn) -> Decimal:
    """Deposits/withdrawals are external cash flows; everything else is internal."""
    if t.type == DEPOSIT:
        return _req(t.cash_amount)
    if t.type == WITHDRAWAL:
        return -_req(t.cash_amount)
    return ZERO


def _req(v: Decimal | None) -> Decimal:
    if v is None:
        raise LedgerError("Missing required numeric field", "invalid_transaction")
    return v


def apply(state: LedgerState, t: Txn) -> None:
    """Apply one transaction in place, raising LedgerError if it is not allowed."""
    new_cash = state.cash + cash_effect(t)
    if new_cash < ZERO:
        raise LedgerError(
            f"{t.type} on {t.trade_date.date()} would make the cash balance negative "
            f"({new_cash:.2f}). Margin is not supported.",
            "insufficient_cash",
        )
    if t.type == BUY:
        assert t.symbol
        pos = state.positions.setdefault(t.symbol, Position())
        pos.quantity += _req(t.quantity)
        pos.cost_basis += _req(t.quantity) * _req(t.price) + t.fee
    elif t.type == SELL:
        assert t.symbol
        held = state.held(t.symbol)
        qty = _req(t.quantity)
        if qty > held:
            raise LedgerError(
                f"Cannot sell {qty} {t.symbol} on {t.trade_date.date()}: only {held} held. "
                "Short selling is not supported.",
                "insufficient_shares",
            )
        pos = state.positions[t.symbol]
        removed = pos.cost_basis * (qty / pos.quantity)
        gain = qty * _req(t.price) - t.fee - removed
        state.realized += gain
        pos.realized += gain
        pos.cost_basis -= removed
        pos.quantity -= qty
        if pos.quantity == ZERO:
            pos.cost_basis = ZERO
    state.cash = new_cash
    state.fees += t.fee + (_req(t.cash_amount) if t.type == FEE else ZERO)
    if t.type == DIVIDEND:
        state.dividends += _req(t.cash_amount)
        if t.symbol:
            state.positions.setdefault(t.symbol, Position()).dividends += _req(t.cash_amount)
    state.external_cash_flow += external_flow(t)


def replay(txns: list[Txn]) -> LedgerState:
    """Replay a full ledger in canonical order; raises on the first violation."""
    state = LedgerState()
    for t in sort_txns(txns):
        apply(state, t)
    return state


def state_as_of(txns_sorted: list[Txn], as_of: datetime) -> LedgerState:
    """State after all transactions with trade_date <= as_of (no validation)."""
    state = LedgerState()
    for t in txns_sorted:
        if t.trade_date > as_of:
            break
        apply(state, t)
    return state
