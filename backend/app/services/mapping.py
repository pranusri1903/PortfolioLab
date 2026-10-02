"""Guessing: which of the file's columns mean what, and how its dates are written."""

import re
from datetime import date, datetime, timedelta

from app.services.tables import Table

DAY_FIRST = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d-%b-%Y", "%d-%b-%y", "%d/%m/%y", "%d %B %Y"]
MONTH_FIRST = ["%m/%d/%Y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y", "%m/%d/%y"]
OTHER = ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
_EXCEL_EPOCH = date(1899, 12, 30)


def parse_date(raw: str, fmt: str | None = None, day_first: bool = True) -> date | None:
    """Parse a date written in almost any common way. ``fmt`` (the user's choice) is tried first;
    ambiguous values like 03/04/2025 follow ``day_first`` (India/most of the world) or month-first (US)."""
    raw = raw.strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{5}(\.\d+)?", raw) and 20000 <= float(raw) <= 70000:  # an Excel serial number
        return _EXCEL_EPOCH + timedelta(days=int(float(raw)))
    raw = re.sub(r"[T ]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?$", "", raw)  # drop a time of day
    order = [*OTHER, *(DAY_FIRST + MONTH_FIRST if day_first else MONTH_FIRST + DAY_FIRST)]
    for f in ([fmt] if fmt else []) + order:
        try:
            return datetime.strptime(raw, f).date()
        except ValueError:
            continue
    return None


def _values(table: Table, col: str) -> list[str]:
    return [r.get(col, "") for r in table.rows if r.get(col, "")]


def _mostly(vals: list[str], test, share: float = 0.8) -> bool:
    return bool(vals) and sum(bool(test(v)) for v in vals) >= share * len(vals)


def _numeric(v: str) -> bool:
    return bool(re.fullmatch(r"[-+(]?[\d,]*\.?\d+\)?", re.sub(r"[₹$%\s]|Rs\.?", "", v)))


# Columns that describe today's value or performance are never the cost or the quantity bought.
NOT_COST = re.compile(r"current|market|present|latest|return|p&l|profit|loss|gain|xirr|%|change|day", re.I)

PATTERNS: dict[str, list[tuple[str, bool]]] = {
    # (regex, may match a NOT_COST column)
    "trade_date": [
        (r"buy.?date|purchase.?date|trade.?date|transaction.?date|txn.?date|^date$", True),
        (r"date", True),
    ],
    "type": [
        (r"^type$|trade.?type|transaction.?type|action|side|^txn", True),
        (r"transaction|narration|description", True),
    ],
    "symbol": [(r"symbol|ticker|scrip|instrument|stock", True), (r"scheme|fund|isin|security|name", True)],
    "quantity": [(r"qty|quantity|units|shares", True)],
    "price": [
        (r"avg.*(price|cost|nav)|average|buy.?price|purchase.?(price|nav)", False),
        (r"price|nav|rate", False),
    ],
    "fee": [(r"fee|brokerage|charge|stt|stamp", True)],
    "cash_amount": [
        (r"invested|cost|buy.?value|purchase.?(value|amount)", False),
        (r"amount", False),
        (r"value|net", False),
    ],
    "notes": [(r"note|remark|narration|comment", True)],
}
KINDS = {
    "transactions": ["trade_date", "type", "symbol", "quantity", "price", "fee", "cash_amount", "notes"],
    "holdings": ["symbol", "quantity", "price", "cash_amount", "trade_date"],
}


def suggest(table: Table) -> dict[str, dict[str, str]]:
    """Best-guess column for each field, by header words first, then by what the values look like."""
    out: dict[str, dict[str, str]] = {}
    for kind, fields in KINDS.items():
        used: set[str] = set()
        pick: dict[str, str] = {}
        for f in fields:
            for rx, allow_bad in PATTERNS[f]:
                col = next(
                    (
                        c
                        for c in table.columns
                        if c not in used and re.search(rx, c, re.I) and (allow_bad or not NOT_COST.search(c))
                    ),
                    "",
                )
                if col:
                    pick[f] = col
                    used.add(col)
                    break
            else:
                pick[f] = ""
        if not pick.get("trade_date"):  # no helpful header: a column full of dates
            col = next(
                (
                    c
                    for c in table.columns
                    if c not in used
                    and _mostly(
                        _values(table, c),
                        lambda v: (
                            parse_date(v) is not None
                            and not _numeric(v)
                            or re.fullmatch(r"\d{5}", v) is None
                            and parse_date(v) is not None
                        ),
                    )
                ),
                "",
            )
            if col and not NOT_COST.search(col):
                pick["trade_date"] = col
                used.add(col)
        if not pick.get("symbol"):  # the first column of mostly words is probably the asset
            col = next(
                (
                    c
                    for c in table.columns
                    if c not in used
                    and _mostly(_values(table, c), lambda v: not _numeric(v) and parse_date(v) is None)
                ),
                "",
            )
            pick["symbol"] = col
        out[kind] = pick
    return out


def date_format_hint(table: Table, column: str) -> str:
    """strptime format that reads every value in the column, or '' if none single one does."""
    vals = _values(table, column)
    for f in [*OTHER[:2], *DAY_FIRST, *MONTH_FIRST]:
        if vals and all(_try(v, f) for v in vals):
            return f
    return ""


def _try(v: str, f: str) -> bool:
    try:
        datetime.strptime(v.strip(), f)
        return True
    except ValueError:
        return False
