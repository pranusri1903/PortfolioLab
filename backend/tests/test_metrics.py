import math
from datetime import date, timedelta
from decimal import Decimal as D

from app.calculations import metrics as m


def pts(values, flows=None):
    flows = flows or [0] * len(values)
    return [
        m.SnapshotPoint(date(2025, 1, 1) + timedelta(days=i), D(v), D(f))
        for i, (v, f) in enumerate(zip(values, flows, strict=True))
    ]


def test_deposit_is_not_return():
    r, _ = m.daily_returns(pts([100, 200], [0, 100]))  # value doubled only because of a deposit
    assert r[0].value == 0


def test_return_excludes_first_day_and_compounds():
    r, _ = m.daily_returns(pts([100, 110, 99]))
    assert len(r) == 2
    assert math.isclose(m.cumulative_return(r).value, -0.01)


def test_zero_previous_value_is_skipped_and_counted():
    r, skipped = m.daily_returns(pts([0, 100, 110]))
    assert skipped == 1 and len(r) == 1


def test_insufficient_history_hides_metrics():
    r, _ = m.daily_returns(pts([100]))
    assert m.cumulative_return(r).value is None
    r, _ = m.daily_returns(pts([100, 101, 102]))
    assert m.annualized_volatility(r).value is None and m.max_drawdown(r).value is None


def test_volatility_sharpe_drawdown():
    vals = [100 + (i % 2) * 2 - (i // 7) for i in range(40)]
    r, _ = m.daily_returns(pts(vals))
    assert m.annualized_volatility(r).value > 0
    assert m.max_drawdown(r).value < 0
    assert m.sharpe_ratio(r, D("0.02")).value is not None


def test_zero_volatility_sharpe_undefined():
    r, _ = m.daily_returns(pts([100] * 30))
    assert m.sharpe_ratio(r, D(0)).value is None
