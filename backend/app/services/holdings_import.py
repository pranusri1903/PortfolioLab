"""Holdings-file import: "what I own today" (CSV or Excel) becomes one DEPOSIT + BUY per row.

Columns: symbol (ticker, scheme name or AMFI code), quantity/units, and either an average buy
price or the invested amount. A buy date is optional; rows without one use ``default_date``.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Portfolio
from app.schemas.portfolio import ImportResponse
from app.services import csv_import as ci
from app.services.mapping import suggest
from app.services.tables import Source, Table

FIELDS = ["symbol", "quantity", "price", "cash_amount", "trade_date"]


def detect(table: Table) -> dict[str, str]:
    found = suggest(table)["holdings"]
    if not found.get("symbol") or not found.get("quantity"):
        raise ApiError(
            422,
            "invalid_csv_header",
            "Couldn't find the holding and quantity columns. Map them, "
            "or use: symbol, quantity, average_price, date.",
            {"received": table.columns},
        )
    return found


def to_records(
    src: Source, mapping: dict | None, date_format: str, default_date: date, day_first: bool = True
):
    table = src.table()
    cols = mapping or detect(table)
    records = []
    for rec in table.rows:

        def get(f: str, rec=rec) -> str:
            return rec.get(cols.get(f) or "", "").strip()

        qty, price = ci.derive_qty_price(
            ci.clean_num(get("quantity")), ci.clean_num(get("price")), ci.clean_num(get("cash_amount"))
        )
        records.append(
            {
                "trade_date": ci.to_iso(get("trade_date"), date_format, day_first)
                if get("trade_date")
                else default_date.isoformat(),
                "type": "BUY",
                "symbol": get("symbol"),
                "quantity": qty,
                "price": price,
                "fee": "0",
                "cash_amount": "",
                "notes": "Imported holding",
                **({"__row_error__": rec["__row_error__"]} if "__row_error__" in rec else {}),
            }
        )
    return records


def run(
    s: Session,
    portfolio: Portfolio,
    src: Source,
    *,
    commit: bool,
    mapping: dict | None,
    date_format: str,
    scope: str | None,
    provider,
    default_date: date,
    cash: Decimal,
) -> ImportResponse:
    if default_date > date.today():
        raise ApiError(422, "invalid_date", "The default buy date can't be in the future.")
    rows = ci.analyze_records(
        s,
        portfolio,
        to_records(src, mapping, date_format, default_date, portfolio.base_currency == "INR"),
        scope,
        provider,
        auto_fund=True,
    )
    if not commit:
        return ci.to_response(rows, False, None)
    return ci.write_rows(
        s, portfolio, rows, provider, auto_fund=True, opening_cash=cash, cash_date=default_date
    )
