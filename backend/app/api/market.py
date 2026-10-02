import hmac
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.config import get_settings
from app.db import get_engine, get_session
from app.errors import ApiError
from app.models import Asset
from app.repositories import data as repo
from app.schemas.portfolio import AssetOut
from app.services import prices
from app.services.live_data import (
    CompositeProvider,
    MfApiProvider,
    ProviderError,
    SymbolHit,
    TwelveDataProvider,
)

router = APIRouter(prefix="/api/v1", tags=["market"])
Db = Annotated[Session, Depends(get_session)]
User = Annotated[str, Depends(current_user_id)]


@lru_cache
def get_provider() -> CompositeProvider:
    key = get_settings().twelve_data_api_key
    return CompositeProvider(TwelveDataProvider(key) if key else None, MfApiProvider())


Provider = Annotated[CompositeProvider, Depends(get_provider)]


class SearchResult(BaseModel):
    symbol: str
    name: str
    asset_type: str
    currency: str
    exchange: str | None
    in_db: bool
    sample: bool


class SearchResponse(BaseModel):
    results: list[SearchResult]
    warning: str | None = None


@router.get("/market/status")
def status(_: User, provider: Provider):
    return {"stocks": provider.stocks is not None, "mutual_funds": provider.funds is not None}


@router.get("/assets", response_model=list[AssetOut])
def list_assets(db: Db, _: User):
    return db.query(Asset).order_by(Asset.symbol).all()


@router.get("/assets/search", response_model=SearchResponse)
def search_assets(
    db: Db,
    _: User,
    provider: Provider,
    q: str = Query(min_length=1, max_length=40),
    currency: str | None = None,
):
    like = f"%{q}%"
    local = db.query(Asset).filter((Asset.symbol.ilike(like)) | (Asset.name.ilike(like)))
    if currency:
        local = local.filter(Asset.currency == currency)
    results = [
        SearchResult(
            symbol=a.symbol,
            name=a.name,
            asset_type=a.asset_type,
            currency=a.currency,
            exchange=a.exchange,
            in_db=True,
            sample=a.exchange is None,
        )
        for a in local.limit(10)
    ]
    known, warning = {r.symbol for r in results}, None
    try:
        results += [
            SearchResult(**h.__dict__, in_db=False, sample=False)
            for h in provider.search(q, currency)
            if h.symbol not in known
        ]
    except ProviderError as exc:
        warning = f"Live search unavailable: {exc}"
    return SearchResponse(results=results[:25], warning=warning)


class AssetAdd(BaseModel):
    symbol: str


@router.post("/assets", response_model=AssetOut, status_code=201)
def add_asset(body: AssetAdd, db: Db, _: User, provider: Provider):
    """Add a live-priced asset. The provider is asked again so name/currency can't be forged."""
    if a := repo.get_asset(db, body.symbol.upper()):
        return a
    try:
        hit = next(
            (h for h in provider.search(body.symbol.split(".")[0]) if h.symbol == body.symbol.upper()), None
        )
    except ProviderError as exc:
        raise ApiError(502, "provider_error", f"Market data provider error: {exc}") from exc
    if hit is None:
        raise ApiError(404, "unknown_symbol", f"'{body.symbol}' was not found at the market data provider.")
    return prices.add_live_asset(db, provider, hit)


def _update_job(provider: CompositeProvider) -> None:
    from sqlalchemy.orm import Session as S

    with S(get_engine()) as s:
        prices.update_all(s, provider)


@router.post("/admin/update-prices", status_code=202)
def update_prices(background: BackgroundTasks, provider: Provider, x_cron_secret: str = Header("")):
    """Called daily by a scheduler (see .github/workflows/update-prices.yml)."""
    secret = get_settings().cron_secret
    if not secret or not hmac.compare_digest(x_cron_secret, secret):
        raise ApiError(403, "forbidden", "Invalid cron secret.")
    background.add_task(_update_job, provider)
    return {"status": "started"}


__all__ = ["router", "get_provider", "SymbolHit"]
