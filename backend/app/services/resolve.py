"""Turn whatever a statement calls an asset (ticker, scheme name, AMFI code) into one of our symbols."""

import re
from dataclasses import dataclass

from app.models import Asset
from app.services.live_data import ProviderError, SymbolHit

MAX_LOOKUPS = 25  # provider calls per file
FILLER = {"fund", "plan", "scheme", "option", "mutual", "the", "of", "and"}  # words fund houses add or drop


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


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
        self.other: dict[str, Resolved | None] = {}
        self.lookups = 0
        self.error: str | None = None  # last problem talking to the market-data service

    @staticmethod
    def _asset(a: Asset) -> Resolved:
        return Resolved(a.symbol, a.name, a.currency, a.asset_type)

    def resolve(self, raw: str) -> Resolved | None:
        raw = raw.strip()
        if raw not in self.cache:
            self.cache[raw] = self._resolve(raw)
        return self.cache[raw]

    def elsewhere(self, raw: str) -> Resolved | None:
        """Does this name exist in another currency? Used to explain why a row can't go in this portfolio."""
        raw = raw.strip()
        if raw not in self.other:
            self.other[raw] = self._remote(raw, None)
        return self.other[raw]

    def _resolve(self, raw: str) -> Resolved | None:
        key = raw.upper()
        a = self.assets.get(key) or next(
            (self.assets[key + x] for x in (".NS", ".BO") if key + x in self.assets), None
        )
        a = a or (self.assets.get("MF-" + raw) if raw.isdigit() else None) or self.by_name.get(norm(raw))
        return self._asset(a) if a else self._remote(raw, self.currency)

    def _search(self, raw: str, currency: str | None) -> list[SymbolHit]:
        """Search the provider with the full text, then again without filler words."""
        short = " ".join(w for w in raw.split() if w.lower() not in FILLER)
        hits: dict[str, SymbolHit] = {}
        for q in dict.fromkeys([raw, short]):
            if q and not hits:
                hits = {h.symbol: h for h in self.provider.search(q, currency)}
        return list(hits.values())

    @staticmethod
    def _pick(raw: str, hits: list[SymbolHit]) -> SymbolHit | None:
        """Accept a match only when it is unambiguous; never guess between several funds."""
        exact = [h for h in hits if norm(h.name) == norm(raw) or h.symbol == raw.upper()]
        if exact:
            return exact[0]
        want = tokens(raw) - FILLER
        close = [h for h in hits if want <= tokens(h.name)]  # every meaningful word of the statement appears
        for word in ("direct", "regular"):  # the statement says which plan; names may differ in wording
            if word in want:
                close = [h for h in close if word in tokens(h.name)] or close
        return close[0] if len(close) == 1 else (hits[0] if len(hits) == 1 else None)

    def _remote(self, raw: str, currency: str | None) -> Resolved | None:
        if self.provider is None or self.lookups >= MAX_LOOKUPS or len(raw) > 80:
            return None
        self.lookups += 1
        try:
            if raw.isdigit():
                funds = getattr(self.provider, "funds", None)
                pick = funds.lookup(raw) if funds else None
            else:
                pick = self._pick(raw, self._search(raw, currency))
        except ProviderError as exc:
            self.error = str(exc)
            return None
        if pick is None:
            return None
        known = self.assets.get(pick.symbol)
        return (
            self._asset(known)
            if known
            else Resolved(pick.symbol, pick.name, pick.currency, pick.asset_type, pick)
        )
