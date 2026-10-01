"""Return and risk metrics from daily snapshots.

Cash-flow assumption (MVP): external deposits/withdrawals occur at the END of
the day, so the day's investment return excludes them:

    daily_return = (ending_value - external_cash_flow) / previous_ending_value - 1

The first day in a window is the base point and has no return. Days whose
previous value is <= 0 have an undefined return and are excluded (counted in
``zero_value_days``). This is a simple time-weighted return, not tax-adjusted
and not equivalent to brokerage-reported performance.
"""

import math
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")
TRADING_DAYS = 252
MIN_RETURNS_CUMULATIVE = 1
MIN_RETURNS_RISK = 20  # volatility, Sharpe, drawdown need a meaningful sample


@dataclass(frozen=True)
class SnapshotPoint:
    date: date
    total_value: Decimal
    external_cash_flow: Decimal


@dataclass(frozen=True)
class DailyReturn:
    date: date
    value: Decimal


@dataclass
class MetricValue:
    value: float | None
    reason: str | None = None  # why value is None


def daily_returns(points: list[SnapshotPoint]) -> tuple[list[DailyReturn], int]:
    """Returns (series, zero_value_days). ``points`` must be sorted by date."""
    out: list[DailyReturn] = []
    skipped = 0
    for prev, cur in zip(points, points[1:], strict=False):
        if prev.total_value <= ZERO:
            skipped += 1
            continue
        out.append(DailyReturn(cur.date, (cur.total_value - cur.external_cash_flow) / prev.total_value - 1))
    return out, skipped


def price_returns(prices: list[tuple[date, Decimal]]) -> list[DailyReturn]:
    out = []
    for (_, p0), (d1, p1) in zip(prices, prices[1:], strict=False):
        if p0 > ZERO:
            out.append(DailyReturn(d1, p1 / p0 - 1))
    return out


def cumulative_return(returns: list[DailyReturn]) -> MetricValue:
    if len(returns) < MIN_RETURNS_CUMULATIVE:
        return MetricValue(None, "Not enough history (need at least 2 days of data).")
    growth = Decimal(1)
    for r in returns:
        growth *= 1 + r.value
    return MetricValue(float(growth - 1))


def index_series(returns: list[DailyReturn], base: Decimal = Decimal(100)) -> list[Decimal]:
    """Growth of ``base`` through the return series (length = len(returns))."""
    out, level = [], base
    for r in returns:
        level *= 1 + r.value
        out.append(level)
    return out


def annualized_volatility(returns: list[DailyReturn]) -> MetricValue:
    if len(returns) < MIN_RETURNS_RISK:
        return MetricValue(None, f"Needs at least {MIN_RETURNS_RISK} daily returns.")
    vals = [float(r.value) for r in returns]
    return MetricValue(statistics.stdev(vals) * math.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: list[DailyReturn], risk_free_annual: Decimal) -> MetricValue:
    if len(returns) < MIN_RETURNS_RISK:
        return MetricValue(None, f"Needs at least {MIN_RETURNS_RISK} daily returns.")
    rf_daily = float(risk_free_annual) / TRADING_DAYS
    excess = [float(r.value) - rf_daily for r in returns]
    sd = statistics.stdev(excess)
    if sd == 0:
        return MetricValue(None, "Return volatility is zero; Sharpe ratio is undefined.")
    return MetricValue(statistics.fmean(excess) / sd * math.sqrt(TRADING_DAYS))


def max_drawdown(returns: list[DailyReturn]) -> MetricValue:
    """Largest peak-to-trough decline of the return index, as a negative fraction."""
    if len(returns) < MIN_RETURNS_RISK:
        return MetricValue(None, f"Needs at least {MIN_RETURNS_RISK} daily returns.")
    level = peak = Decimal(1)
    worst = ZERO
    for r in returns:
        level *= 1 + r.value
        peak = max(peak, level)
        worst = min(worst, level / peak - 1)
    return MetricValue(float(worst))
