import csv
import io
import json
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth import current_user_id
from app.db import get_session
from app.errors import ApiError
from app.models import Portfolio, SipPlan
from app.repositories import data as repo
from app.schemas import analytics as an
from app.schemas.portfolio import (
    ImportResponse,
    PortfolioCreate,
    PortfolioOut,
    QuickStart,
    RangeKey,
    SipCreate,
    SipPatch,
    TransactionIn,
    TransactionOut,
    TransactionPage,
    TransactionPatch,
    TxType,
)
from app.services import analytics as analytics_service
from app.services import csv_import, holdings, performance, sip, transactions
from app.services.demo import load_demo_transactions, seed_market_data

router = APIRouter(prefix="/api/v1")
Db = Annotated[Session, Depends(get_session)]
User = Annotated[str, Depends(current_user_id)]


def owned(portfolio_id: uuid.UUID, db: Db, user: User) -> Portfolio:
    p = repo.get_owned_portfolio(db, user, portfolio_id)
    if p is None:  # 404, not 403: don't reveal that other users' portfolios exist
        raise ApiError(404, "not_found", "Portfolio not found.")
    return p


Owned = Annotated[Portfolio, Depends(owned)]


@router.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok"}


@router.post("/portfolios", response_model=PortfolioOut, status_code=201)
def create_portfolio(body: PortfolioCreate, db: Db, user: User):
    kind = "demo" if body.load_demo_data else "real"
    if any(
        x.base_currency == body.currency and x.is_demo == body.load_demo_data
        for x in repo.list_portfolios(db, user)
    ):
        raise ApiError(
            409,
            "portfolio_exists",
            f"You already have a {kind} {body.currency} portfolio (one {kind} portfolio per currency).",
        )
    p = Portfolio(owner_id=user, name=body.name, base_currency=body.currency, is_demo=body.load_demo_data)
    db.add(p)
    db.commit()
    if body.load_demo_data:
        seed_market_data(db)
        load_demo_transactions(db, p)
    return p


@router.get("/portfolios", response_model=list[PortfolioOut])
def list_portfolios(db: Db, user: User):
    return repo.list_portfolios(db, user)


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioOut)
def get_portfolio(p: Owned):
    return p


@router.delete("/portfolios/{portfolio_id}", status_code=204)
def delete_portfolio(p: Owned, db: Db):
    """Permanently removes the portfolio with its transactions, SIPs and history."""
    db.delete(p)
    db.commit()
    return Response(status_code=204)


@router.get("/portfolios/{portfolio_id}/summary", response_model=an.SummaryResponse)
def summary(p: Owned, db: Db, range: RangeKey = "1Y"):
    return performance.summary(db, p, range)


@router.get("/portfolios/{portfolio_id}/performance", response_model=an.PerformanceResponse)
def get_performance(p: Owned, db: Db, range: RangeKey = "1Y"):
    return performance.performance(db, p, range)


@router.get("/portfolios/{portfolio_id}/performance/monthly", response_model=an.MonthlyReturnsResponse)
def get_monthly_returns(p: Owned, db: Db):
    return performance.monthly_returns(db, p)


@router.get("/portfolios/{portfolio_id}/holdings", response_model=an.HoldingsResponse)
def get_holdings(p: Owned, db: Db, asset_type: str | None = None):
    return holdings.holdings_response(db, p, asset_type)


@router.get("/portfolios/{portfolio_id}/analytics", response_model=an.AnalyticsResponse)
def get_analytics(p: Owned, db: Db, asset_type: str | None = None):
    return analytics_service.analytics(db, p, asset_type)


@router.get("/portfolios/{portfolio_id}/holdings/{symbol}", response_model=an.HoldingDetail)
def get_holding(symbol: str, p: Owned, db: Db):
    return holdings.holding_detail(db, p, symbol)


@router.get("/portfolios/{portfolio_id}/allocation", response_model=an.AllocationResponse)
def get_allocation(p: Owned, db: Db):
    return holdings.allocation_response(db, p)


@router.get("/portfolios/{portfolio_id}/transactions", response_model=TransactionPage)
def list_transactions(
    p: Owned,
    db: Db,
    symbol: str | None = None,
    type: TxType | None = None,
    asset_type: str | None = None,
    source: str | None = Query(None, pattern="^(sip|manual)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    rows, total = repo.query_transactions(
        db,
        p.id,
        symbol=symbol,
        tx_type=type,
        asset_type=asset_type,
        source=source,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return TransactionPage(
        items=[transactions.to_out(t) for t in rows], total=total, page=page, page_size=page_size
    )


@router.post("/portfolios/{portfolio_id}/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(body: TransactionIn, p: Owned, db: Db):
    return transactions.to_out(transactions.create_transaction(db, p, body))


@router.post("/portfolios/{portfolio_id}/transactions/import", response_model=ImportResponse)
async def import_transactions(
    p: Owned,
    db: Db,
    file: UploadFile = File(...),
    commit: bool = False,
    mapping: str | None = Form(None),
    date_format: str = Form("%Y-%m-%d"),
):
    try:
        cols = json.loads(mapping) if mapping else None
    except ValueError:
        raise ApiError(422, "invalid_mapping", "mapping must be a JSON object.") from None
    content = await file.read()
    return (csv_import.commit if commit else csv_import.preview)(db, p, content, cols, date_format)


@router.post("/portfolios/{portfolio_id}/quick-start", status_code=201)
def quick_start(body: QuickStart, p: Owned, db: Db):
    return {"created": transactions.quick_start(db, p, body)}


@router.get("/portfolios/{portfolio_id}/sips", response_model=list[an.SipOut])
def list_sips(p: Owned, db: Db):
    return sip.plan_stats(db, p)


@router.post("/portfolios/{portfolio_id}/sips", response_model=an.SipOut, status_code=201)
def create_sip(body: SipCreate, p: Owned, db: Db):
    plan = sip.create_plan(
        db,
        p,
        symbol=body.symbol,
        amount=body.amount,
        day_of_month=body.day_of_month,
        start_date=body.start_date,
        end_date=body.end_date,
    )
    return next(x for x in sip.plan_stats(db, p) if x.id == str(plan.id))


def _plan(p: Portfolio, plan_id: uuid.UUID, db: Session):
    plan = db.get(SipPlan, plan_id)
    if plan is None or plan.portfolio_id != p.id:
        raise ApiError(404, "not_found", "SIP not found.")
    return plan


@router.patch("/portfolios/{portfolio_id}/sips/{plan_id}", response_model=an.SipOut)
def update_sip(plan_id: uuid.UUID, body: SipPatch, p: Owned, db: Db):
    plan = _plan(p, plan_id, db)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(plan, k, v)
    db.commit()
    sip.run_all_sips(db, p.id)
    return next(x for x in sip.plan_stats(db, p) if x.id == str(plan.id))


@router.delete("/portfolios/{portfolio_id}/sips/{plan_id}", status_code=204)
def delete_sip(plan_id: uuid.UUID, p: Owned, db: Db):
    """Stops the plan; past installments stay in the transaction history."""
    db.delete(_plan(p, plan_id, db))
    db.commit()
    return Response(status_code=204)


def _tx(portfolio: Portfolio, transaction_id: uuid.UUID, db: Session):
    t = repo.get_transaction(db, portfolio.id, transaction_id)
    if t is None:
        raise ApiError(404, "not_found", "Transaction not found.")
    return t


@router.patch("/portfolios/{portfolio_id}/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(transaction_id: uuid.UUID, body: TransactionPatch, p: Owned, db: Db):
    return transactions.to_out(transactions.update_transaction(db, p, _tx(p, transaction_id, db), body))


@router.delete("/portfolios/{portfolio_id}/transactions/{transaction_id}", status_code=204)
def delete_transaction(transaction_id: uuid.UUID, p: Owned, db: Db):
    transactions.delete_transaction(db, p, _tx(p, transaction_id, db))
    return Response(status_code=204)


@router.get("/portfolios/{portfolio_id}/transactions-export")
def export_transactions(p: Owned, db: Db):
    """CSV in the same format the importer accepts."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(csv_import.EXPECTED_HEADER)
    for t in repo.all_transactions(db, p.id):
        o = transactions.to_out(t)
        w.writerow(
            [
                o.trade_date.date(),
                o.type,
                o.symbol or "",
                o.quantity or "",
                o.price or "",
                o.fee or "",
                o.cash_amount or "",
                o.notes or "",
            ]
        )
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="transactions.csv"'},
    )
