"""Daily snapshot rebuild.

Trading days are the dates that have price data. A snapshot is written for each
trading day on/after the first transaction. External cash flow for a snapshot
is everything deposited/withdrawn since the previous snapshot (end-of-day
assumption). Days where a held asset has no usable price are skipped and
reported, never valued at zero.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.calculations.ledger import ZERO, LedgerState, apply, external_flow, sort_txns
from app.config import get_settings
from app.models import DailySnapshot
from app.repositories import data as repo
from app.services.ledger_io import to_txns
from app.services.pricing import PriceBook


@dataclass
class RebuildResult:
    written: int
    skipped_days: int


def rebuild_snapshots(s: Session, portfolio_id: uuid.UUID) -> RebuildResult:
    rows = repo.all_transactions(s, portfolio_id)
    if not rows:
        repo.replace_snapshots(s, portfolio_id, [])
        return RebuildResult(0, 0)

    txns = sort_txns(to_txns(rows))
    assets = repo.assets_by_symbol(s)
    book = PriceBook.load(s, [a.id for a in assets.values()])
    max_age = timedelta(days=get_settings().stale_price_days)

    first = txns[0].trade_date.date()
    days = repo.price_dates(s, first)

    state = LedgerState()
    i = 0
    snaps: list[DailySnapshot] = []
    skipped = 0
    for day in days:
        flow = ZERO
        while i < len(txns) and txns[i].trade_date.date() <= day:
            apply(state, txns[i])
            flow += external_flow(txns[i])
            i += 1
        market = ZERO
        usable = True
        for sym, pos in state.positions.items():
            if pos.quantity == ZERO:
                continue
            lk = book.at(assets[sym].id, day)
            if lk is None or day - lk.price_date > max_age:
                usable = False
                break
            market += pos.quantity * lk.close
        if not usable:
            skipped += 1
            continue
        snaps.append(
            DailySnapshot(
                portfolio_id=portfolio_id,
                date=day,
                market_value=_q(market),
                cash_balance=_q(state.cash),
                total_value=_q(market + state.cash),
                external_cash_flow=_q(flow),
            )
        )
    repo.replace_snapshots(s, portfolio_id, snaps)
    return RebuildResult(len(snaps), skipped)


def _q(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.0001"))
