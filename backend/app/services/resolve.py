"""Turn whatever a statement calls an asset (ticker, scheme name, AMFI code) into one of our symbols."""

import re
from dataclasses import dataclass

from app.models import Asset
from app.services.live_data import ProviderError, SymbolHit

MAX_LOOKUPS = 25  # provider calls per file


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


@dataclass(frozen=True)
class Resolved:
    symbol: str
    name: str
    currency: str
    asset_type: str
    hit: SymbolHit | None = None  # set when the asset isn't in our database yet (added on commit)


class Resolver:
    def __init__(self, assets: dict[str, Asset], provider, currency: str):
        self.assets, self.provider, self.currency = assets, provider, currency
        self.by_name = {norm(a.name): a for a in assets.values()}
        self.cache: dict[str, Resolved | None] = {}
        self.lookups = 0

    @staticmethod
    def _asset(a: Asset) -> Resolved:
        return Resolved(a.symbol, a.name, a.currency, a.asset_type)

    def resolve(self, raw: str) -> Resolved | None:
        raw = raw.strip()
        if raw not in self.cache:
            self.cache[raw] = self._resolve(raw)
        return self.cache[raw]

    def _resolve(self, raw: str) -> Resolved | None:
        key = raw.upper()
        a = self.assets.get(key) or next(
            (self.assets[key + x] for x in (".NS", ".BO") if key + x in self.assets), None
        )
        a = a or (self.assets.get("MF-" + raw) if raw.isdigit() else None) or self.by_name.get(norm(raw))
        return self._asset(a) if a else self._remote(raw)

    def _remote(self, raw: str) -> Resolved | None:
        if self.provider is None or self.lookups >= MAX_LOOKUPS or len(raw) > 80:
            return None
        self.lookups += 1
        try:
            if raw.isdigit():
                funds = getattr(self.provider, "funds", None)
                pick = funds.lookup(raw) if funds else None
            else:
                hits = self.provider.search(raw, self.currency)
                exact = [h for h in hits if norm(h.name) == norm(raw) or h.symbol == raw.upper()]
                pick = (
                    exact[0] if exact else (hits[0] if len(hits) == 1 else None)
                )  # never guess between several
        except ProviderError:
            return None
        if pick is None:
            return None
        known = self.assets.get(pick.symbol)
        return (
            self._asset(known)
            if known
            else Resolved(pick.symbol, pick.name, pick.currency, pick.asset_type, pick)
        )
