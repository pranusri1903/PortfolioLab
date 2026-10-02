"""Transaction-history import (CSV or Excel): validate every row, preview, then commit atomically.

Row statuses:
  valid     - will be imported on commit
  invalid   - rejected (malformed field, unknown asset, wrong asset class, or breaks ledger rules)
  duplicate - skipped (same fingerprint as an existing transaction or an earlier row)

Brokers and fund houses use their own layouts, so a column mapping converts them to our format:
trade_date,type,symbol,quantity,price,fee,cash_amount,notes
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.calculations.ledger import ZERO, LedgerError, Txn, replay
from app.errors import ApiError
from app.models import Portfolio, Transaction
from app.repositories import data as repo
from app.schemas.portfolio import ImportCounts, ImportResponse, ImportRow
from app.services import prices
from app.services.ledger_io import to_txns
from app.services.resolve import Resolved, Resolver
from app.services.snapshots import rebuild_snapshots
from app.services.tables import ROW_ERROR, Source, Table
from app.services.validation import fingerprint, to_utc_datetime, validate_fields

EXPECTED_HEADER = ["trade_date", "type", "symbol", "quantity", "price", "fee", "cash_amount", "notes"]
SCOPES = {"stock": {"STOCK", "ETF"}, "fund": {"MUTUAL_FUND"}}
SCOPE_NAME = {"stock": "stocks & ETFs", "fund": "mutual funds"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

TYPE_ALIASES = {
    "BOUGHT": "BUY",
    "PURCHASE": "BUY",
    "SOLD": "SELL",
    "SALE": "SELL",
    "REDEMPTION": "SELL",
    "REDEEM": "SELL",
    "DIV": "DIVIDEND",
    "CREDIT": "DEPOSIT",
    "SIP": "BUY",
    "WITHDRAW": "WITHDRAWAL",
    "DEBIT": "WITHDRAWAL",
    "CHARGE": "FEE",
    "SWITCH IN": "BUY",
    "SWITCH OUT": "SELL",
}


def kind_of(raw: str) -> str:
    """Map a broker's wording ("Redemption", "Systematic Investment", "Switch Out") to our types."""
    k = re.sub(r"\s+", " ", raw.strip().upper().replace("_", " ").replace("-", " "))
    if k in TYPE_ALIASES:
        return TYPE_ALIASES[k]
    if "REINVEST" in k:
        return "BUY"
    for pattern, kind in (
        (r"REDEEM|REDEMPTION|SWITCH OUT|SELL|SOLD|SALE", "SELL"),
        (r"PURCHASE|SIP|SWITCH IN|BUY|BOUGHT|INVESTMENT", "BUY"),
        (r"DIVIDEND|IDCW|\bDIV\b", "DIVIDEND"),
    ):
        if re.search(pattern, k):
            return kind
    return k


def clean_num(v: str) -> str:
    return re.sub(r"[^\d.]", "", v)  # drops currency symbols, commas and signs


def to_iso(raw: str, fmt: str) -> str:
    for f in (fmt, "%Y-%m-%d"):  # Excel date cells arrive as ISO already
        try:
            return datetime.strptime(raw, f).date().isoformat()
        except ValueError:
            continue
    return raw  # left as-is so the row is rejected with a clear reason


def dec(name: str, raw: str | None, errors: list[str]) -> Decimal | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        d = Decimal(raw.strip())
    except InvalidOperation:
        errors.append(f"{name} '{raw}' is not a valid number")
        return None
    if not d.is_finite():
        errors.append(f"{name} '{raw}' is not a valid number")
        return None
    return d


def derive_qty_price(qty: str, price: str, amount: str) -> tuple[str, str]:
    """Fund statements list amount + NAV (or amount + units); fill in whichever is missing."""
    try:
        if amount and price and not qty and Decimal(price) > 0:
            qty = str((Decimal(amount) / Decimal(price)).quantize(Decimal("1e-8")))
        elif amount and qty and not price and Decimal(qty) > 0:
            price = str((Decimal(amount) / Decimal(qty)).quantize(Decimal("1e-6")))
    except InvalidOperation:
        pass
    return qty, price


def normalize(rec: dict[str, str], mapping: dict[str, str], date_format: str) -> dict[str, str]:
    def get(f: str) -> str:
        return rec.get(mapping.get(f) or "", "").strip()

    kind = kind_of(get("type"))
    qty, price, amount, fee = (
        clean_num(get("quantity")),
        clean_num(get("price")),
        clean_num(get("cash_amount")),
        clean_num(get("fee")),
    )
    if kind in ("BUY", "SELL"):
        qty, price = derive_qty_price(qty, price, amount)
        amount = ""
    out = dict(
        zip(
            EXPECTED_HEADER,
            [
                to_iso(get("trade_date"), date_format),
                kind,
                get("symbol"),
                qty,
                price,
                fee,
                amount,
                get("notes"),
            ],
            strict=True,
        )
    )
    if ROW_ERROR in rec:
        out[ROW_ERROR] = rec[ROW_ERROR]
    return out


@dataclass
class Parsed:
    row_number: int
    raw: dict[str, str | None]
    status: str = "valid"
    reasons: list[str] = field(default_factory=list)
    trade_date: date | None = None
    type: str = ""
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal = ZERO
    cash_amount: Decimal | None = None
    notes: str | None = None
    fp: str = ""
    resolved: Resolved | None = None


def canonical_records(table: Table, mapping: dict | None, date_format: str) -> list[dict[str, str]]:
    if mapping:
        return [normalize(r, mapping, date_format) for r in table.rows]
    if table.columns != EXPECTED_HEADER:
        raise ApiError(
            422,
            "invalid_csv_header",
            "Header must be exactly: " + ",".join(EXPECTED_HEADER) + " (or map your columns).",
            {"expected": EXPECTED_HEADER, "received": table.columns},
        )
    return table.rows


def _check_row(
    p: Parsed,
    resolver: Resolver,
    existing_fps: set[str],
    seen: dict[str, int],
    pid,
    currency: str,
    scope: str | None,
):
    if p.status == "invalid":
        return
    errors: list[str] = []
    raw = p.raw
    d = (raw["trade_date"] or "").strip()
    if not _DATE_RE.match(d):
        errors.append(f"trade_date '{d}' must be YYYY-MM-DD")
    else:
        try:
            p.trade_date = date.fromisoformat(d)
        except ValueError:
            errors.append(f"trade_date '{d}' is not a real calendar date")
    p.type = (raw["type"] or "").strip().upper()
    given = (raw["symbol"] or "").strip()
    p.symbol = given.upper() or None
    if given:
        p.resolved = resolver.resolve(given)
        if p.resolved:
            p.symbol = p.resolved.symbol
    p.quantity = dec("quantity", raw["quantity"], errors)
    p.price = dec("price", raw["price"], errors)
    fee = dec("fee", raw["fee"], errors)
    p.fee = fee if fee is not None else ZERO
    p.cash_amount = dec("cash_amount", raw["cash_amount"], errors)
    p.notes = (raw["notes"] or "").strip()[:500] or None
    if not errors:
        errors += validate_fields(
            type=p.type,
            symbol=p.symbol,
            quantity=p.quantity,
            price=p.price,
            fee=p.fee,
            cash_amount=p.cash_amount,
        )
    if given and p.resolved is None:
        errors.append(
            f"Unknown {'fund' if scope == 'fund' else 'symbol'} '{given}'"
            + (" (use the exact scheme name or its AMFI code)" if scope == "fund" else "")
        )
    elif p.resolved and p.resolved.currency != currency:
        errors.append(f"{p.symbol} trades in {p.resolved.currency}, not {currency}")
    elif p.resolved and scope and p.resolved.asset_type not in SCOPES[scope]:
        other = "mutual funds" if scope == "stock" else "stocks & ETFs"
        errors.append(f"{p.symbol} is not in {SCOPE_NAME[scope]}; import it under {other}")
    if errors:
        p.status, p.reasons = "invalid", errors
        return
    assert p.trade_date
    p.fp = fingerprint(
        pid,
        trade_date=p.trade_date,
        type=p.type,
        symbol=p.symbol,
        quantity=p.quantity,
        price=p.price,
        fee=p.fee,
        cash_amount=p.cash_amount,
    )
    if p.fp in existing_fps:
        p.status, p.reasons = "duplicate", ["Already exists in this portfolio"]
    elif p.fp in seen:
        p.status, p.reasons = "duplicate", [f"Duplicate of row {seen[p.fp]} in this file"]
    else:
        seen[p.fp] = p.row_number


def _as_txn(p: Parsed, seq: int) -> Txn:
    assert p.trade_date
    return Txn(
        type=p.type,
        trade_date=to_utc_datetime(p.trade_date),
        symbol=p.symbol,
        quantity=p.quantity,
        price=p.price,
        fee=p.fee,
        cash_amount=p.cash_amount,
        seq=seq,
    )


def deposit_for(p: Parsed, seq: int) -> Txn:
    """Auto-funding: each BUY gets a same-day DEPOSIT of its cost plus fee (rounded up to 4 dp)."""
    assert p.trade_date and p.quantity and p.price
    cost = (p.quantity * p.price + p.fee).quantize(Decimal("0.0001"), rounding=ROUND_CEILING)
    return Txn(type="DEPOSIT", trade_date=to_utc_datetime(p.trade_date), cash_amount=cost, seq=seq)


def analyze_records(
    s: Session,
    portfolio: Portfolio,
    records: list[dict[str, str]],
    scope: str | None = None,
    provider=None,
    auto_fund: bool = False,
) -> list[Parsed]:
    rows = []
    for n, rec in enumerate(records, start=1):
        p = Parsed(row_number=n, raw={k: rec.get(k, "") for k in EXPECTED_HEADER})
        if ROW_ERROR in rec:
            p.status, p.reasons = "invalid", [rec[ROW_ERROR]]
        rows.append(p)
    resolver = Resolver(repo.assets_by_symbol(s), provider, portfolio.base_currency)
    existing = repo.all_transactions(s, portfolio.id)
    existing_fps = {t.fingerprint for t in existing}
    seen: dict[str, int] = {}
    for p in rows:
        _check_row(p, resolver, existing_fps, seen, portfolio.id, portfolio.base_currency, scope)

    # Ledger rules: accept rows greedily in file order; a row that would overdraw cash
    # or oversell (given existing data and the rows accepted so far) is rejected.
    base, accepted = to_txns(existing), list[Txn]()
    for p in rows:
        if p.status != "valid":
            continue
        step = [
            *([deposit_for(p, len(base) + len(accepted) + 1)] if auto_fund and p.type == "BUY" else []),
            _as_txn(p, len(base) + len(accepted) + 2),
        ]
        try:
            replay([*base, *accepted, *step])
        except LedgerError as exc:
            p.status, p.reasons = "invalid", [str(exc)]
            continue
        accepted += step
    return rows


def analyze(
    s: Session,
    portfolio: Portfolio,
    src: Source,
    mapping: dict | None = None,
    date_format: str = "%Y-%m-%d",
    scope: str | None = None,
    provider=None,
    auto_fund: bool = False,
) -> list[Parsed]:
    records = canonical_records(src.table(), mapping, date_format)
    return analyze_records(s, portfolio, records, scope, provider, auto_fund)


def to_response(rows: list[Parsed], committed: bool, result: ImportCounts | None) -> ImportResponse:
    return ImportResponse(
        committed=committed,
        total_rows=len(rows),
        valid=sum(p.status == "valid" for p in rows),
        invalid=sum(p.status == "invalid" for p in rows),
        duplicate=sum(p.status == "duplicate" for p in rows),
        rows=[
            ImportRow(
                row_number=p.row_number,
                status=p.status,
                reasons=p.reasons,
                data=p.raw,  # type: ignore[arg-type]
                resolved_symbol=p.resolved.symbol if p.resolved else None,
                resolved_name=p.resolved.name if p.resolved else None,
                will_add_asset=bool(p.resolved and p.resolved.hit),
            )
            for p in rows
        ],
        result=result,
    )


def preview(
    s,
    portfolio,
    src,
    mapping=None,
    date_format="%Y-%m-%d",
    scope=None,
    provider=None,
    auto_fund=False,
):
    return to_response(
        analyze(s, portfolio, src, mapping, date_format, scope, provider, auto_fund),
        False,
        None,
    )


def add_pending_assets(s: Session, provider, rows: list[Parsed]) -> None:
    """Add live-priced assets the file refers to that we haven't seen before."""
    for hit in {p.resolved.hit for p in rows if p.status == "valid" and p.resolved and p.resolved.hit}:
        prices.add_live_asset(s, provider, hit)  # type: ignore[arg-type]


def write_rows(
    s: Session,
    portfolio: Portfolio,
    rows: list[Parsed],
    provider,
    auto_fund: bool = False,
    opening_cash: Decimal = ZERO,
    cash_date: date | None = None,
) -> ImportResponse:
    add_pending_assets(s, provider, rows)
    assets = repo.assets_by_symbol(s)
    good = [p for p in rows if p.status == "valid"]

    def tx(**kw) -> Transaction:
        return Transaction(id=uuid.uuid4(), portfolio_id=portfolio.id, fee=ZERO, **kw)

    try:
        # One DB transaction: every valid row is written, or none are.
        for p in good:
            assert p.trade_date
            when = to_utc_datetime(p.trade_date)
            if auto_fund and p.type == "BUY":
                dep = deposit_for(p, 0)
                s.add(
                    tx(
                        type="DEPOSIT",
                        trade_date=when,
                        cash_amount=dep.cash_amount,
                        notes="Imported holding: funding",
                        fingerprint=fingerprint(
                            portfolio.id,
                            trade_date=p.trade_date,
                            type="DEPOSIT",
                            symbol=None,
                            quantity=None,
                            price=None,
                            fee=ZERO,
                            cash_amount=dep.cash_amount,
                        ),
                    )
                )
            t = tx(
                asset_id=assets[p.symbol].id if p.symbol else None,
                type=p.type,
                trade_date=when,
                quantity=p.quantity,
                price=p.price,
                cash_amount=p.cash_amount,
                notes=p.notes,
                fingerprint=p.fp,
            )
            t.fee = p.fee
            s.add(t)
        if opening_cash > 0 and cash_date and good:  # re-running a file must not add the cash again
            s.add(
                tx(
                    type="DEPOSIT",
                    trade_date=to_utc_datetime(cash_date),
                    cash_amount=opening_cash,
                    notes="Opening cash",
                    fingerprint=fingerprint(
                        portfolio.id,
                        trade_date=cash_date,
                        type="DEPOSIT",
                        symbol=None,
                        quantity=None,
                        price=None,
                        fee=ZERO,
                        cash_amount=opening_cash,
                    ),
                )
            )
        s.flush()
        rebuild_snapshots(s, portfolio.id)
        s.commit()
    except Exception:
        s.rollback()
        raise
    counts = ImportCounts(
        imported=len(good),
        skipped=sum(p.status == "duplicate" for p in rows),
        rejected=sum(p.status == "invalid" for p in rows),
    )
    return to_response(rows, True, counts)


def commit(
    s,
    portfolio,
    src,
    mapping=None,
    date_format="%Y-%m-%d",
    scope=None,
    provider=None,
    auto_fund=False,
):
    rows = analyze(s, portfolio, src, mapping, date_format, scope, provider, auto_fund)
    return write_rows(s, portfolio, rows, provider, auto_fund=auto_fund)
