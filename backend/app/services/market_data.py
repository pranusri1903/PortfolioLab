"""Market-data provider interface. Portfolio calculations only read the daily_prices
table, so a real (licensed) provider can be added by implementing this protocol and
writing its rows to daily_prices with a different ``source``."""

import random
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol

from app.models import Asset

# symbol: (name, type, start price, annual drift, annual volatility, currency)
DEMO_ASSETS = {
    "ACME": ("Acme Industrial Corp (sample)", "STOCK", 50, 0.10, 0.25, "USD"),
    "BOLT": ("Bolt Energy Inc (sample)", "STOCK", 80, 0.08, 0.32, "USD"),
    "CRST": ("Crest Health Group (sample)", "STOCK", 120, 0.12, 0.22, "USD"),
    "DYNA": ("Dyna Software Ltd (sample)", "STOCK", 30, 0.15, 0.40, "USD"),
    "BNCH": ("Benchmark Market ETF (sample)", "ETF", 100, 0.09, 0.16, "USD"),
    "BOND": ("Sample Aggregate Bond ETF", "ETF", 90, 0.03, 0.05, "USD"),
    "GRWF": ("Sample Growth Mutual Fund", "MUTUAL_FUND", 40, 0.11, 0.18, "USD"),
    "INFX": ("Infinity Systems Ltd (sample)", "STOCK", 1500, 0.13, 0.28, "INR"),
    "BHRT": ("Bharat Industrials Ltd (sample)", "STOCK", 2400, 0.10, 0.24, "INR"),
    "SWDS": ("Swadesh Foods Ltd (sample)", "STOCK", 600, 0.09, 0.30, "INR"),
    "NIFB": ("Nifty-style Benchmark ETF (sample)", "ETF", 200, 0.11, 0.15, "INR"),
    "GSEC": ("Sample Gilt ETF", "ETF", 100, 0.05, 0.04, "INR"),
    "FLXF": ("Sample Flexi Cap Mutual Fund", "MUTUAL_FUND", 60, 0.13, 0.17, "INR"),
}
DEMO_START, DEMO_END = date(2022, 1, 3), date(2026, 9, 30)


class MarketDataProvider(Protocol):
    source: str

    def daily_closes(self, asset: Asset, start: date, end: date) -> Iterator[tuple[date, Decimal]]: ...


class DemoProvider:
    """Deterministic geometric random walk, seeded by symbol. Weekdays only."""

    source = "demo"

    def daily_closes(self, asset: Asset, start: date, end: date) -> Iterator[tuple[date, Decimal]]:
        _, _, price, mu, sigma, _ = DEMO_ASSETS[asset.symbol]
        rng = random.Random(asset.symbol)
        for i in range((end - start).days + 1):
            d = start + timedelta(days=i)
            if d.weekday() < 5:
                price *= 1 + mu / 252 + sigma / 252**0.5 * rng.gauss(0, 1)
                yield d, Decimal(price).quantize(Decimal("0.01"))
