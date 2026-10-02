import uuid
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories import data as repo


@dataclass(frozen=True)
class PriceLookup:
    close: Decimal
    price_date: date


class PriceBook:
    """Closing prices by asset. Lookups return the most recent close ON OR BEFORE
    the requested date, never a future price, and report the price's own date so
    callers can flag stale data. Missing data returns None (never zero)."""

    def __init__(self) -> None:
        self._dates: dict[uuid.UUID, list[date]] = {}
        self._closes: dict[uuid.UUID, list[Decimal]] = {}

    @classmethod
    def load(cls, s: Session, asset_ids: list[uuid.UUID]) -> "PriceBook":
        book = cls()
        for p in repo.prices_for_assets(s, asset_ids):
            book._dates.setdefault(p.asset_id, []).append(p.date)
            book._closes.setdefault(p.asset_id, []).append(p.close)
        return book

    def at(self, asset_id: uuid.UUID, on: date) -> PriceLookup | None:
        dates = self._dates.get(asset_id)
        if not dates:
            return None
        i = bisect_right(dates, on)
        if i == 0:
            return None
        return PriceLookup(self._closes[asset_id][i - 1], dates[i - 1])

    def on_or_after(self, asset_id: uuid.UUID, on: date) -> PriceLookup | None:
        dates = self._dates.get(asset_id, [])
        i = bisect_left(dates, on)
        return PriceLookup(self._closes[asset_id][i], dates[i]) if i < len(dates) else None

    def series(self, asset_id: uuid.UUID) -> list[tuple[date, Decimal]]:
        return list(zip(self._dates.get(asset_id, []), self._closes.get(asset_id, []), strict=True))
