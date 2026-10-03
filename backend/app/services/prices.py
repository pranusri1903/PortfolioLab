"""Fetching and storing live prices, plus the daily update job."""

import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import ApiError
from app.models import Asset, DailyPrice, Transaction
from app.repositories import data as repo
from app.services.live_data import CompositeProvider, ProviderError, SymbolHit
from app.services.snapshots import rebuild_snapshots

log = logging.getLogger("portfoliolab.prices")
HISTORY_YEARS = 5


def save_prices(s: Session, asset: Asset, rows, source: str) -> int:
    have = set(s.scalars(select(DailyPrice.date).where(DailyPrice.asset_id == asset.id)))
    new = [DailyPrice(asset_id=asset.id, date=d, close=c, source=source) for d, c in rows if d not in have]
    s.add_all(new)
    return len(new)


def add_live_asset(s: Session, provider: CompositeProvider, hit: SymbolHit) -> Asset:
    """Create the asset and backfill history; rejects symbols the provider has no prices for."""
    existing = repo.get_asset(s, hit.symbol)
    if existing and existing.exchange is None:
        raise ApiError(409, "symbol_reserved", f"{hit.symbol} is a sample-data symbol.")
    asset = existing or Asset(
        symbol=hit.symbol,
        name=hit.name,
        asset_type=hit.asset_type,
        currency=hit.currency,
        exchange=hit.exchange,
    )
    s.add(asset)
    s.flush()
    try:
        today = date.today()
        n = save_prices(
            s,
            asset,
            provider.daily_closes(asset, today - timedelta(days=365 * HISTORY_YEARS), today),
            provider.source_for(asset),
        )
    except ProviderError as exc:
        s.rollback()
        raise ApiError(502, "provider_error", f"Market data provider error: {exc}") from exc
    if n == 0 and repo.latest_price_date_for(s, asset.id) is None:
        s.rollback()
        raise ApiError(422, "no_price_data", f"No price history is available for {hit.symbol}.")
    s.commit()
    return asset


def ensure_benchmark(s: Session, provider: CompositeProvider, currency: str) -> Asset | None:
    """Make sure the real benchmark for this currency exists, with price history. Best effort."""
    sym = get_settings().benchmark_for(currency)
    if (asset := repo.get_asset(s, sym)) is not None:
        return asset
    try:
        if sym.startswith("MF-"):  # an Indian mutual fund, identified by its AMFI code
            hit = provider.funds.lookup(sym[3:]) if provider.funds else None
        else:
            hit = next((h for h in provider.search(sym.split(".")[0], currency) if h.symbol == sym), None)
        return add_live_asset(s, provider, hit) if hit else None
    except (ProviderError, ApiError) as exc:
        log.warning("could not load benchmark %s: %s", sym, exc)
        return None


def update_all(s: Session, provider: CompositeProvider) -> dict:
    """Fetch new closes for every live asset, then refresh SIPs and snapshots."""
    from app.services.sip import run_all_sips

    failed: list[str] = []
    for currency in ("USD", "INR"):
        if ensure_benchmark(s, provider, currency) is None:
            failed.append(f"benchmark for {currency} portfolios not available")
    today, added = date.today(), 0
    for asset in s.scalars(select(Asset).where(Asset.exchange.is_not(None))).all():
        last = s.scalar(select(func.max(DailyPrice.date)).where(DailyPrice.asset_id == asset.id))
        start = last + timedelta(days=1) if last else today - timedelta(days=365 * HISTORY_YEARS)
        if start > today:
            continue
        try:
            added += save_prices(
                s, asset, provider.daily_closes(asset, start, today), provider.source_for(asset)
            )
            s.commit()
        except ProviderError as exc:
            s.rollback()
            failed.append(f"{asset.symbol}: {exc}")
    sips = run_all_sips(s)
    for pid in s.scalars(select(Transaction.portfolio_id).distinct()).all():
        rebuild_snapshots(s, pid)
    s.commit()
    log.info("price update: %d new prices, %d sip installments, %d failures", added, sips, len(failed))
    return {"prices_added": added, "sip_installments": sips, "failed": failed}
