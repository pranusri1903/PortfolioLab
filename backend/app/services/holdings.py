from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.calculations.ledger import ZERO, LedgerState, apply, replay, sort_txns
from app.config import get_settings
from app.errors import ApiError
from app.models import Portfolio
from app.repositories import data as repo
from app.schemas.analytics import (
    AllocationResponse,
    AllocationSlice,
    HoldingDetail,
    HoldingOut,
    HoldingsResponse,
    PositionPoint,
    PricePoint,
)
from app.services.ledger_io import to_txns
from app.services.pricing import PriceBook
from app.services.transactions import to_out


@dataclass
class Valuation:
    as_of: date | None
    state: LedgerState
    holdings: list[HoldingOut]
    market_value: Decimal
    cash: Decimal
    total_value: Decimal
    value_complete: bool
    unavailable: list[str]
    is_sample: bool


def _q(d: Decimal, places: str = "0.0001") -> Decimal:
    return d.quantize(Decimal(places))


def value_portfolio(s: Session, p: Portfolio) -> Valuation:
    rows = repo.all_transactions(s, p.id)
    state = replay(to_txns(rows)) if rows else LedgerState()
    assets = repo.assets_by_symbol(s)
    as_of = repo.latest_price_date(s, p.base_currency)
    held = {sym: pos for sym, pos in state.positions.items() if pos.quantity > ZERO}
    book = PriceBook.load(s, [assets[sym].id for sym in held])
    max_age = timedelta(days=get_settings().stale_price_days)

    market = ZERO
    unavailable: list[str] = []
    out: list[HoldingOut] = []
    for sym, pos in sorted(held.items()):
        a = assets[sym]
        lk = book.at(a.id, as_of) if as_of else None
        if lk is None:
            status, price, pdate, mv = "unavailable", None, None, None
            unavailable.append(sym)
        else:
            status = "stale" if as_of and as_of - lk.price_date > max_age else "ok"
            price, pdate, mv = lk.close, lk.price_date, pos.quantity * lk.close
            market += mv
        gl = (mv - pos.cost_basis) if mv is not None else None
        out.append(
            HoldingOut(
                symbol=sym,
                name=a.name,
                asset_type=a.asset_type,
                quantity=pos.quantity,
                average_cost=_q(pos.average_cost, "0.000001"),
                cost_basis=_q(pos.cost_basis),
                latest_price=price,
                price_date=pdate,
                price_status=status,  # type: ignore[arg-type]
                market_value=_q(mv) if mv is not None else None,
                unrealized_gain_loss=_q(gl) if gl is not None else None,
                unrealized_gain_loss_pct=(
                    float(gl / pos.cost_basis) if gl is not None and pos.cost_basis else None
                ),
                weight=None,
            )
        )
    total = market + state.cash
    for h in out:
        if h.market_value is not None and total > ZERO:
            h.weight = float(h.market_value / total)
    sources = repo.price_sources(s, [assets[sym].id for sym in held]) if held else set()
    return Valuation(
        as_of=as_of,
        state=state,
        holdings=out,
        market_value=_q(market),
        cash=_q(state.cash),
        total_value=_q(total),
        value_complete=not unavailable,
        unavailable=unavailable,
        is_sample=("demo" in sources) or not sources,
    )


def holdings_response(s: Session, p: Portfolio, asset_type: str | None = None) -> HoldingsResponse:
    v = value_portfolio(s, p)
    return HoldingsResponse(
        as_of=v.as_of,
        is_sample_data=v.is_sample,
        value_complete=v.value_complete,
        unavailable_symbols=v.unavailable,
        holdings=[h for h in v.holdings if not asset_type or h.asset_type == asset_type],
    )


def allocation_response(s: Session, p: Portfolio) -> AllocationResponse:
    v = value_portfolio(s, p)
    total = v.total_value
    by_holding: list[AllocationSlice] = []
    by_type: dict[str, Decimal] = {}

    def w(x: Decimal) -> float:
        return float(x / total) if total > ZERO else 0.0

    for h in v.holdings:
        if h.market_value is None:
            continue
        by_holding.append(
            AllocationSlice(key=h.symbol, label=h.name, value=h.market_value, weight=w(h.market_value))
        )
        by_type[h.asset_type] = by_type.get(h.asset_type, ZERO) + h.market_value
    if v.cash > ZERO:
        by_holding.append(AllocationSlice(key="CASH", label="Cash", value=v.cash, weight=w(v.cash)))
        by_type["CASH"] = v.cash
    by_holding.sort(key=lambda x: x.value, reverse=True)
    types = [
        AllocationSlice(key=k, label=k.title() if k == "CASH" else k, value=val, weight=w(val))
        for k, val in sorted(by_type.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return AllocationResponse(
        as_of=v.as_of,
        is_sample_data=v.is_sample,
        value_complete=v.value_complete,
        by_holding=by_holding,
        by_asset_type=types,
    )


def holding_detail(s: Session, p: Portfolio, symbol: str) -> HoldingDetail:
    symbol = symbol.upper()
    asset = repo.get_asset(s, symbol)
    if asset is None:
        raise ApiError(404, "not_found", f"Unknown symbol '{symbol}'.")
    rows = [t for t in repo.all_transactions(s, p.id) if t.asset_id == asset.id]
    # position history needs the full ledger context only for this symbol's own trades
    state = LedgerState()
    history: list[PositionPoint] = []
    for t in sort_txns(to_txns(rows)):
        if t.type in ("BUY", "SELL"):
            apply_symbol_only(state, t)
            pos = state.positions.get(symbol)
            history.append(
                PositionPoint(
                    date=t.trade_date.date(),
                    quantity=pos.quantity if pos else ZERO,
                    cost_basis=_q(pos.cost_basis) if pos else ZERO,
                )
            )
    book = PriceBook.load(s, [asset.id])
    prices = [PricePoint(date=d, close=c) for d, c in book.series(asset.id)]
    sources = repo.price_sources(s, [asset.id])
    val = value_portfolio(s, p)
    holding = next((h for h in val.holdings if h.symbol == symbol), None)
    return HoldingDetail(
        holding=holding,
        symbol=symbol,
        name=asset.name,
        asset_type=asset.asset_type,
        is_sample_data=("demo" in sources) or not sources,
        price_source=", ".join(sorted(sources)) or None,
        position_history=history,
        price_history=prices,
        transactions=[to_out(t) for t in reversed(rows)],
    )


def apply_symbol_only(state: LedgerState, t) -> None:
    """Track quantity/cost for one symbol, ignoring cash (cash is validated elsewhere)."""
    state.cash = Decimal("1e18")  # never the binding constraint for a per-symbol view
    apply(state, t)
