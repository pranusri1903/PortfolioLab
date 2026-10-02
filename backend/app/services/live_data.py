"""Live market-data providers. Both implement ``MarketDataProvider`` plus ``search``.

- TwelveDataProvider: stocks/ETFs (US, and NSE/BSE if your plan includes them). Needs an API key.
  Check your plan's licence: the free Basic plan is for internal, non-display use.
- MfApiProvider: Indian mutual funds via the free mfapi.in service (AMFI NAV data), no key.
"""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import httpx

from app.models import Asset


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class SymbolHit:
    symbol: str
    name: str
    asset_type: str  # STOCK | ETF | MUTUAL_FUND
    currency: str
    exchange: str  # MIC code, or "AMFI" for Indian mutual funds


class TwelveDataProvider:
    source = "twelvedata"
    URL = "https://api.twelvedata.com"
    SUFFIX = {"XNSE": ".NS", "XBOM": ".BO"}  # our symbol = ticker + suffix for Indian listings

    def __init__(self, api_key: str, client: httpx.Client | None = None):
        self.key, self.http, self.sleep = api_key, client or httpx.Client(timeout=30), time.sleep

    def _get(self, path: str, **params) -> dict:
        for attempt in range(2):
            try:
                r = self.http.get(f"{self.URL}/{path}", params={**params, "apikey": self.key})
                data = r.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise ProviderError(f"could not reach the stock data service ({type(exc).__name__})") from exc
            if data.get("code") == 429 and attempt == 0:  # free plan: 8 requests/minute
                self.sleep(61)
                continue
            if r.status_code != 200 or data.get("status") == "error":
                raise ProviderError(data.get("message", r.text[:200]))
            return data
        raise ProviderError("rate limited")

    def search(self, q: str) -> list[SymbolHit]:
        hits: dict[str, SymbolHit] = {}
        for d in self._get("symbol_search", symbol=q, outputsize=30).get("data", []):
            kind, mic, cur = d.get("instrument_type", "").lower(), d.get("mic_code", ""), d.get("currency")
            if not ("stock" in kind or "etf" in kind or "reit" in kind) or cur not in ("USD", "INR"):
                continue
            if (cur == "INR") != (mic in self.SUFFIX):  # INR only on NSE/BSE
                continue
            sym = d["symbol"] + self.SUFFIX.get(mic, "")
            hits.setdefault(
                sym, SymbolHit(sym, d["instrument_name"], "ETF" if "etf" in kind else "STOCK", cur, mic)
            )
        return list(hits.values())

    def daily_closes(self, asset: Asset, start: date, end: date) -> Iterator[tuple[date, Decimal]]:
        ticker = asset.symbol.removesuffix(self.SUFFIX.get(asset.exchange or "", "\0"))
        data = self._get(
            "time_series",
            symbol=ticker,
            mic_code=asset.exchange,
            interval="1day",
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            outputsize=5000,
            order="ASC",
        )
        for v in data.get("values", []):
            yield date.fromisoformat(v["datetime"][:10]), Decimal(v["close"]).quantize(Decimal("0.000001"))


class MfApiProvider:
    source = "mfapi"
    URL = "https://api.mfapi.in/mf"

    def __init__(self, client: httpx.Client | None = None):
        self.http = client or httpx.Client(timeout=30)

    def _get(self, path: str, **params):
        try:
            r = self.http.get(f"{self.URL}{path}", params=params)
            if r.status_code != 200:
                raise ProviderError(f"mfapi.in returned {r.status_code}")
            return r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError(
                f"could not reach the mutual fund data service ({type(exc).__name__})"
            ) from exc

    def search(self, q: str) -> list[SymbolHit]:
        # Growth plans only: dividend payouts would need distribution handling.
        rows = self._get("/search", q=q)
        return [
            SymbolHit(f"MF-{r['schemeCode']}", r["schemeName"], "MUTUAL_FUND", "INR", "AMFI")
            for r in rows
            if "IDCW" not in r["schemeName"] and "dividend" not in r["schemeName"].lower()
        ][:15]

    def lookup(self, code: str) -> SymbolHit | None:
        """Resolve an AMFI scheme code to a fund (statements often list codes, not names)."""
        try:
            name = (self._get(f"/{code}").get("meta") or {}).get("scheme_name")
        except ProviderError:
            return None
        if not name or "IDCW" in name or "dividend" in name.lower():
            return None
        return SymbolHit(f"MF-{code}", name, "MUTUAL_FUND", "INR", "AMFI")

    def daily_closes(self, asset: Asset, start: date, end: date) -> Iterator[tuple[date, Decimal]]:
        for row in reversed(self._get(f"/{asset.symbol.removeprefix('MF-')}").get("data", [])):
            d = datetime.strptime(row["date"], "%d-%m-%Y").date()
            if start <= d <= end and Decimal(row["nav"]) > 0:
                yield d, Decimal(row["nav"]).quantize(Decimal("0.000001"))


class CompositeProvider:
    """Routes each asset/search to the provider that covers it."""

    source = "live"

    def __init__(self, stocks: TwelveDataProvider | None, funds: MfApiProvider | None):
        self.stocks, self.funds = stocks, funds

    def for_asset(self, a: Asset):
        p = self.funds if a.exchange == "AMFI" else self.stocks
        if p is None:
            raise ProviderError(f"No live provider configured for {a.symbol}")
        return p

    def search(self, q: str, currency: str | None = None) -> list[SymbolHit]:
        hits: list[SymbolHit] = []
        for p in (self.stocks, self.funds if currency in (None, "INR") else None):
            if p:
                try:
                    hits += p.search(q)
                except ProviderError:
                    continue
        return [h for h in hits if currency in (None, h.currency)]

    def daily_closes(self, asset: Asset, start: date, end: date):
        return self.for_asset(asset).daily_closes(asset, start, end)

    def source_for(self, a: Asset) -> str:
        return self.for_asset(a).source
