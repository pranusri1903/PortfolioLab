from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from app.calculations.ledger import LedgerError, Txn, replay


def t(type, day, **kw):
    return Txn(type=type, trade_date=datetime(2025, 1, day, tzinfo=UTC), seq=day, **kw)


def test_buy_updates_cash_quantity_and_cost_basis_with_fee_once():
    s = replay(
        [t("DEPOSIT", 1, cash_amount=D(1000)), t("BUY", 2, symbol="A", quantity=D(10), price=D(50), fee=D(1))]
    )
    assert s.cash == D(499)  # 1000 - (500 + 1)
    assert s.positions["A"].quantity == 10
    assert s.positions["A"].cost_basis == D(501)


def test_sell_reduces_cost_proportionally_and_nets_fee():
    s = replay(
        [
            t("DEPOSIT", 1, cash_amount=D(1000)),
            t("BUY", 2, symbol="A", quantity=D(10), price=D(50), fee=D(1)),
            t("SELL", 3, symbol="A", quantity=D(4), price=D(60), fee=D(2)),
        ]
    )
    assert s.cash == D(499) + D(240) - D(2)
    assert s.positions["A"].quantity == 6
    assert s.positions["A"].cost_basis == D("300.6")  # 501 * 6/10


def test_weighted_average_cost_across_buys():
    s = replay(
        [
            t("DEPOSIT", 1, cash_amount=D(5000)),
            t("BUY", 2, symbol="A", quantity=D(10), price=D(10)),
            t("BUY", 3, symbol="A", quantity=D(10), price=D(20)),
        ]
    )
    assert s.positions["A"].average_cost == D(15)


def test_dividend_and_cash_flows_do_not_touch_cost_basis():
    s = replay(
        [
            t("DEPOSIT", 1, cash_amount=D(1000)),
            t("BUY", 2, symbol="A", quantity=D(1), price=D(100)),
            t("DIVIDEND", 3, symbol="A", cash_amount=D(5)),
            t("WITHDRAWAL", 4, cash_amount=D(100)),
            t("FEE", 5, cash_amount=D(10)),
        ]
    )
    assert s.cash == D(1000) - 100 + 5 - 100 - 10
    assert s.positions["A"].cost_basis == D(100)
    assert s.external_cash_flow == D(900)


def test_oversell_rejected():
    with pytest.raises(LedgerError) as e:
        replay(
            [
                t("DEPOSIT", 1, cash_amount=D(1000)),
                t("BUY", 2, symbol="A", quantity=D(1), price=D(10)),
                t("SELL", 3, symbol="A", quantity=D(2), price=D(10)),
            ]
        )
    assert e.value.code == "insufficient_shares"


def test_negative_cash_rejected():
    with pytest.raises(LedgerError) as e:
        replay(
            [
                t("DEPOSIT", 1, cash_amount=D(100)),
                t("BUY", 2, symbol="A", quantity=D(1), price=D(100), fee=D(1)),
            ]
        )
    assert e.value.code == "insufficient_cash"


def test_same_day_deposit_sorts_before_buy():
    replay([t("BUY", 1, symbol="A", quantity=D(1), price=D(10)), t("DEPOSIT", 1, cash_amount=D(10))])


def test_realized_gain_dividends_and_fees_tracked():
    s = replay(
        [
            t("DEPOSIT", 1, cash_amount=D(1000)),
            t("BUY", 2, symbol="A", quantity=D(10), price=D(50), fee=D(1)),
            t("SELL", 3, symbol="A", quantity=D(4), price=D(60), fee=D(2)),
            t("DIVIDEND", 4, symbol="A", cash_amount=D(5)),
            t("FEE", 5, cash_amount=D(3)),
        ]
    )
    assert s.realized == D(240) - 2 - D("200.4")  # proceeds - fee - removed cost (501 * 4/10)
    assert s.dividends == 5 and s.fees == 1 + 2 + 3
