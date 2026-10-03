from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.calculations import metrics as m
from app.config import get_settings
from app.models import Portfolio
from app.repositories import data as repo
from app.schemas.analytics import (
    MetricOut,
    Metrics,
    MonthlyReturn,
    MonthlyReturnsResponse,
    PerformanceResponse,
    SeriesPoint,
    SummaryResponse,
)
from app.schemas.portfolio import PortfolioOut
from app.services.holdings import value_portfolio
from app.services.pricing import PriceBook

BENCH_MISSING = (
    "No real benchmark is loaded yet. It is added automatically once live market data is on "
    "(see Settings); we don't compare real portfolios against fictional sample data."
)
RANGE_DAYS = {"1M": 30, "3M": 91, "6M": 182, "1Y": 365, "3Y": 1095, "5Y": 1826}

ASSUMPTIONS = [
    "Returns are time-weighted from daily snapshots; external deposits and withdrawals are "
    "treated as occurring at the end of the day, so they do not count as investment return.",
    "daily return = (ending value - external cash flow) / previous ending value - 1; the first "
    "day in the window is the base and has no return.",
    "Volatility = stdev(daily returns) x sqrt(252). Sharpe = mean(excess daily return) / "
    "stdev(excess daily return) x sqrt(252), using the stated annual risk-free rate.",
    "Not tax-adjusted and not equivalent to brokerage-reported performance.",
    "Windows are measured back from the latest available data date, not today's date.",
    "Benchmark: a real index proxy (UTI Nifty 50 Index Fund for INR, SPY for USD) or, in demo portfolios, "
    "a fictional sample ETF. Both lines start at 100 on the first day shown, so the gap between them is the "
    "difference in return over the period. The benchmark ignores dividends unless its price series includes "
    "them, and index funds carry small fees; it is a yardstick, not an investable alternative.",
]


def _mv(v: m.MetricValue) -> MetricOut:
    return MetricOut(value=v.value, reason=v.reason)


def _empty_metrics(reason: str) -> Metrics:
    e = MetricOut(value=None, reason=reason)
    return Metrics(
        cumulative_return=e,
        annualized_volatility=e,
        sharpe_ratio=e,
        max_drawdown=e,
        benchmark_cumulative_return=e,
    )


def performance(s: Session, p: Portfolio, range_key: str) -> PerformanceResponse:
    cfg = get_settings()
    snaps = repo.snapshots(s, p.id)
    base = dict(
        range=range_key,
        benchmark_symbol=cfg.benchmark_for(p.base_currency, p.is_demo),
        risk_free_rate=float(cfg.risk_free_rate),
        assumptions=ASSUMPTIONS,
    )
    benchmark = repo.get_asset(s, cfg.benchmark_for(p.base_currency, p.is_demo))
    sources = repo.price_sources(s, [benchmark.id]) if benchmark else set()
    bench_sample = "demo" in sources
    is_sample = bench_sample if benchmark else p.is_demo
    base.update(
        benchmark_name=benchmark.name if benchmark else None,
        benchmark_is_sample=bench_sample,
        benchmark_available=benchmark is not None,
    )

    if len(snaps) < 2:
        return PerformanceResponse(
            **base,
            start_date=None,
            end_date=None,
            partial=False,
            is_sample_data=is_sample,
            series=[],
            metrics=_empty_metrics("Not enough history (need at least 2 days of data)."),
            zero_value_days=0,
        )

    end = snaps[-1].date
    partial = False
    window = snaps
    if range_key != "All":
        start_target = (
            date(end.year - 1, 12, 31) if range_key == "YTD" else end - timedelta(days=RANGE_DAYS[range_key])
        )
        idx = next((i for i, x in enumerate(snaps) if x.date > start_target), None)
        base_i = max((idx or 0) - 1, 0)  # last snapshot on/before the target start
        partial = snaps[0].date > start_target
        window = snaps[base_i:]
    points = [m.SnapshotPoint(x.date, x.total_value, x.external_cash_flow) for x in window]
    returns, zero_days = m.daily_returns(points)
    rf = cfg.risk_free_rate

    # Benchmark closes aligned to the window
    bench_prices: dict[date, Decimal] = {}
    if benchmark:
        book = PriceBook.load(s, [benchmark.id])
        for x in window:
            lk = book.at(benchmark.id, x.date)
            if lk is not None:
                bench_prices[x.date] = lk.close
    bench_series = [(d, bench_prices[d]) for d in (x.date for x in window) if d in bench_prices]
    bench_ret = m.price_returns(bench_series)
    if benchmark is None:
        bench_cum = m.MetricValue(None, BENCH_MISSING)
    elif len(bench_series) < len(window):
        bench_cum = m.MetricValue(None, "Benchmark prices are missing for part of this window.")
    else:
        bench_cum = m.cumulative_return(bench_ret)

    # Series: portfolio index chained from returns; benchmark rebased to 100
    ret_by_date = {r.date: r.value for r in returns}
    level = Decimal(100)
    series: list[SeriesPoint] = []
    b0 = bench_series[0][1] if bench_series and bench_series[0][0] == window[0].date else None
    for i, x in enumerate(window):
        if i > 0 and x.date in ret_by_date:
            level *= 1 + ret_by_date[x.date]
        b = bench_prices.get(x.date)
        series.append(
            SeriesPoint(
                date=x.date,
                total_value=x.total_value,
                portfolio_index=float(level),
                benchmark_index=float(Decimal(100) * b / b0) if b is not None and b0 else None,
            )
        )
    return PerformanceResponse(
        **base,
        start_date=window[0].date,
        end_date=window[-1].date,
        partial=partial,
        is_sample_data=is_sample,
        series=series,
        metrics=Metrics(
            cumulative_return=_mv(m.cumulative_return(returns)),
            annualized_volatility=_mv(m.annualized_volatility(returns)),
            sharpe_ratio=_mv(m.sharpe_ratio(returns, rf)),
            max_drawdown=_mv(m.max_drawdown(returns)),
            benchmark_cumulative_return=_mv(bench_cum),
        ),
        zero_value_days=zero_days,
    )


def summary(s: Session, p: Portfolio, range_key: str) -> SummaryResponse:
    v = value_portfolio(s, p)
    perf = performance(s, p, range_key)
    net = v.state.external_cash_flow
    gl = v.total_value - net
    tx_count = len(repo.all_transactions(s, p.id))
    q = lambda d: d.quantize(Decimal("0.0001"))  # noqa: E731
    return SummaryResponse(
        portfolio=PortfolioOut.model_validate(p),
        as_of=v.as_of,
        data_updated_at=None,
        is_sample_data=v.is_sample,
        value_complete=v.value_complete,
        unavailable_symbols=v.unavailable,
        total_value=v.total_value,
        market_value=v.market_value,
        cash_balance=v.cash,
        net_contributions=net.quantize(Decimal("0.0001")),
        total_gain_loss=gl.quantize(Decimal("0.0001")),
        total_gain_loss_pct=float(gl / net) if net > 0 else None,
        range=range_key,
        period_return=perf.metrics.cumulative_return,
        metrics=perf.metrics,
        transaction_count=tx_count,
        realized_gain_loss=q(v.state.realized),
        dividend_income=q(v.state.dividends),
        fees_paid=q(v.state.fees),
    )


def monthly_returns(s: Session, p: Portfolio) -> MonthlyReturnsResponse:
    """Compounded daily returns per calendar month, portfolio vs benchmark."""
    snaps = repo.snapshots(s, p.id)
    points = [m.SnapshotPoint(x.date, x.total_value, x.external_cash_flow) for x in snaps]
    port, _ = m.daily_returns(points)
    bench = repo.get_asset(s, get_settings().benchmark_for(p.base_currency, p.is_demo))
    book = PriceBook.load(s, [bench.id]) if bench else PriceBook()
    bench_ret = (
        m.price_returns([(x.date, lk.close) for x in snaps if (lk := book.at(bench.id, x.date))])
        if bench
        else []
    )

    def by_month(rs: list[m.DailyReturn]) -> dict[str, float]:
        groups: dict[str, list[m.DailyReturn]] = {}
        for r in rs:
            groups.setdefault(r.date.strftime("%Y-%m"), []).append(r)
        return {k: m.cumulative_return(v).value for k, v in groups.items()}  # type: ignore[misc]

    pm, bm = by_month(port), by_month(bench_ret)
    sources = repo.price_sources(s, [bench.id]) if bench else set()
    return MonthlyReturnsResponse(
        is_sample_data="demo" in sources or not sources,
        months=[MonthlyReturn(month=k, portfolio=pm.get(k), benchmark=bm.get(k)) for k in sorted(pm)],
    )
