import statistics
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.calculations import metrics as m
from app.calculations.ledger import ZERO, LedgerState, apply, sort_txns
from app.calculations.xirr import xirr
from app.models import Portfolio
from app.repositories import data as repo
from app.schemas.analytics import (
    AnalyticsResponse,
    ClassBreakdown,
    Concentration,
    Correlation,
    DrawdownPoint,
    HoldingAnalytics,
    MetricOut,
)
from app.services.holdings import value_portfolio
from app.services.ledger_io import to_txns
from app.services.pricing import PriceBook

CORR_MAX, CORR_MIN_DAYS = 12, 30


def _price_stats(series: list[tuple[date, Decimal]], as_of: date | None):
    year = [(d, c) for d, c in series if as_of and as_of - timedelta(days=365) <= d <= as_of]
    rets = m.price_returns(year)
    if len(year) < 2:
        return dict(vol=None, dd=None, ret=None, hi=None, lo=None, off=None)
    level = peak = Decimal(1)
    worst = ZERO
    for r in rets:
        level *= 1 + r.value
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
    closes = [c for _, c in year]
    return dict(
        vol=m.annualized_volatility(rets).value if len(rets) >= m.MIN_RETURNS_RISK else None,
        dd=float(worst) if len(rets) >= m.MIN_RETURNS_RISK else None,
        ret=float(year[-1][1] / year[0][1] - 1),
        hi=max(closes),
        lo=min(closes),
        off=float(year[-1][1] / max(closes) - 1),
    )


def analytics(s: Session, p: Portfolio, asset_type: str | None = None) -> AnalyticsResponse:
    v = value_portfolio(s, p)
    rows = repo.all_transactions(s, p.id)
    txns = sort_txns(to_txns(rows))
    assets = repo.assets_by_symbol(s)
    book = PriceBook.load(s, [a.id for a in assets.values() if a.currency == p.base_currency])

    # replay once, collecting per-symbol cash flows for XIRR
    state = LedgerState()
    flows: dict[str, list[tuple[date, float]]] = {}
    bought: dict[str, Decimal] = {}
    first: dict[str, date] = {}
    port_flows: list[tuple[date, float]] = []
    for t in txns:
        apply(state, t)
        day = t.trade_date.date()
        if t.type in ("DEPOSIT", "WITHDRAWAL"):
            amount = float(t.cash_amount or 0)
            port_flows.append((day, -amount if t.type == "DEPOSIT" else amount))
        if not t.symbol:
            continue
        f = flows.setdefault(t.symbol, [])
        if t.type == "BUY":
            cost = t.quantity * t.price + t.fee  # type: ignore[operator]
            f.append((day, float(-cost)))
            bought[t.symbol] = bought.get(t.symbol, ZERO) + cost
            first.setdefault(t.symbol, day)
        elif t.type == "SELL":
            f.append((day, float(t.quantity * t.price - t.fee)))  # type: ignore[operator]
        elif t.type == "DIVIDEND":
            f.append((day, float(t.cash_amount)))  # type: ignore[arg-type]

    held = {hd.symbol: hd for hd in v.holdings}
    out: list[HoldingAnalytics] = []
    for sym, pos in state.positions.items():
        a = assets[sym]
        if asset_type and a.asset_type != asset_type:
            continue
        if sym not in bought:
            continue
        pos_view = held.get(sym)
        value = pos_view.market_value if pos_view else ZERO
        unreal = (value - pos.cost_basis) if value is not None else None
        total = (unreal + pos.realized + pos.dividends) if unreal is not None else None
        fl = list(flows[sym])
        if value and v.as_of:
            fl.append((v.as_of, float(value)))
        ps = _price_stats(book.series(a.id), v.as_of)
        out.append(
            HoldingAnalytics(
                symbol=sym,
                name=a.name,
                asset_type=a.asset_type,
                open=pos.quantity > ZERO,
                quantity=pos.quantity,
                total_invested=bought[sym].quantize(Decimal("0.0001")),
                current_value=value,
                unrealized_gain_loss=unreal and unreal.quantize(Decimal("0.0001")),
                realized_gain_loss=pos.realized.quantize(Decimal("0.0001")),
                dividends=pos.dividends.quantize(Decimal("0.0001")),
                total_return=total and total.quantize(Decimal("0.0001")),
                total_return_pct=float(total / bought[sym]) if total is not None and bought[sym] else None,
                xirr=xirr(fl),
                first_buy=first.get(sym),
                holding_days=(v.as_of - first[sym]).days if v.as_of and sym in first else None,
                weight=pos_view.weight if pos_view else None,
                share_of_profit=None,
                volatility_1y=ps["vol"],
                max_drawdown_1y=ps["dd"],
                return_1y=ps["ret"],
                high_52w=ps["hi"],
                low_52w=ps["lo"],
                pct_from_high=ps["off"],
            )
        )
    profit = sum((h.total_return or ZERO for h in out), ZERO)
    for h in out:
        if h.total_return is not None and profit != ZERO:
            h.share_of_profit = float(h.total_return / profit)
    out.sort(key=lambda h: (not h.open, -(float(h.current_value or 0))))

    open_w = [h.weight for h in out if h.open and h.weight]
    tot_w = sum(open_w) or 1
    ws = sorted((w / tot_w for w in open_w), reverse=True)
    hhi = sum(w * w for w in ws) if ws else None
    classes: dict[str, list[HoldingAnalytics]] = {}
    for h in out:
        if h.open:
            classes.setdefault(h.asset_type, []).append(h)
    by_class = [
        ClassBreakdown(
            asset_type=k,
            value=sum((x.current_value or ZERO for x in g), ZERO),
            count=len(g),
            weight=sum(x.weight or 0 for x in g),
            total_return=sum((x.total_return or ZERO for x in g), ZERO),
        )
        for k, g in sorted(classes.items())
    ]

    # correlation of daily price returns over the last year, open holdings only
    syms = [h.symbol for h in out if h.open][:CORR_MAX]
    rets = {}
    for sym in syms:
        yr = [
            (d, c)
            for d, c in book.series(assets[sym].id)
            if v.as_of and v.as_of - timedelta(days=365) <= d <= v.as_of
        ]
        rets[sym] = {r.date: float(r.value) for r in m.price_returns(yr)}
    matrix: list[list[float | None]] = []
    for x in syms:
        row: list[float | None] = []
        for y in syms:
            common = sorted(set(rets[x]) & set(rets[y]))
            try:
                row.append(
                    1.0
                    if x == y
                    else round(
                        statistics.correlation([rets[x][d] for d in common], [rets[y][d] for d in common]), 4
                    )
                    if len(common) >= CORR_MIN_DAYS
                    else None
                )
            except statistics.StatisticsError:
                row.append(None)
        matrix.append(row)

    snaps = repo.snapshots(s, p.id)
    returns, _ = m.daily_returns(
        [m.SnapshotPoint(x.date, x.total_value, x.external_cash_flow) for x in snaps]
    )
    level = peak = Decimal(1)
    dd: list[DrawdownPoint] = []
    for r in returns:
        level *= 1 + r.value
        peak = max(peak, level)
        dd.append(DrawdownPoint(date=r.date, drawdown=float(level / peak - 1)))

    if v.as_of and v.total_value:
        port_flows.append((v.as_of, float(v.total_value)))
    px = xirr(port_flows)
    return AnalyticsResponse(
        currency=p.base_currency,
        as_of=v.as_of,
        is_sample_data=v.is_sample,
        portfolio_xirr=MetricOut(
            value=px, reason=None if px is not None else "Needs at least 30 days of history with deposits."
        ),
        realized_total=state.realized.quantize(Decimal("0.0001")),
        dividends_total=state.dividends.quantize(Decimal("0.0001")),
        holdings=out,
        concentration=Concentration(
            top1=ws[0] if ws else None,
            top3=sum(ws[:3]) if ws else None,
            hhi=hhi,
            effective_holdings=1 / hhi if hhi else None,
        ),
        by_class=by_class,
        correlation=Correlation(symbols=syms, matrix=matrix, window_days=365),
        drawdown=dd[:: max(1, len(dd) // 400)],
    )
