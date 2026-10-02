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
from app.services.tables import read_table

FIELDS = ["symbol", "quantity", "price", "cash_amount", "trade_date"]
# Column names recognised without a mapping (case-insensitive)
ALIASES = {
    "symbol": [
        "symbol",
        "ticker",
        "scheme",
        "scheme name",
        "fund",
        "fund name",
        "instrument",
        "name",
        "scheme code",
    ],
    "quantity": ["quantity", "qty", "units", "shares"],
    "price": [
        "average_price",
        "avg_price",
        "average price",
        "avg price",
        "avg cost",
        "price",
        "nav",
        "buy price",
    ],
    "cash_amount": ["invested", "invested amount", "amount", "cost", "cost value"],
    "trade_date": ["date", "buy date", "trade_date", "purchase date", "purchase_date"],
}


def detect(columns: list[str]) -> dict[str, str]:
    lower = {c.lower().strip(): c for c in columns}
    found = {f: next((lower[a] for a in ALIASES[f] if a in lower), "") for f in FIELDS}
    if not found["symbol"] or not found["quantity"]:
        raise ApiError(
            422,
            "invalid_csv_header",
            "Couldn't find the holding and quantity columns. Map them, "
            "or use: symbol, quantity, average_price, date.",
            {"received": columns},
        )
    return found


def to_records(filename: str, content: bytes, mapping: dict | None, date_format: str, default_date: date):
    table = read_table(filename, content)
    cols = mapping or detect(table.columns)
    records = []
    for rec in table.rows:

        def get(f: str, rec=rec) -> str:
            return rec.get(cols.get(f) or "", "").strip()

        qty, price = ci.derive_qty_price(
            ci.clean_num(get("quantity")), ci.clean_num(get("price")), ci.clean_num(get("cash_amount"))
        )
        records.append(
            {
                "trade_date": ci.to_iso(get("trade_date"), date_format)
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
    filename: str,
    content: bytes,
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
        to_records(filename, content, mapping, date_format, default_date),
        scope,
        provider,
        auto_fund=True,
    )
    if not commit:
        return ci.to_response(rows, False, None)
    return ci.write_rows(
        s, portfolio, rows, provider, auto_fund=True, opening_cash=cash, cash_date=default_date
    )
