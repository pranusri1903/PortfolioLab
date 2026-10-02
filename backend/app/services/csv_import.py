"""CSV import: validate every row, preview, then commit atomically.

Row statuses:
  valid     - will be imported on commit
  invalid   - rejected (malformed field, unknown symbol, or would break ledger rules)
  duplicate - skipped (same fingerprint as an existing transaction or an earlier row)
"""

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.calculations.ledger import ZERO, LedgerError, Txn, replay
from app.errors import ApiError
from app.models import Portfolio, Transaction
from app.repositories import data as repo
from app.schemas.portfolio import ImportCounts, ImportResponse, ImportRow
from app.services.ledger_io import to_txns
from app.services.snapshots import rebuild_snapshots
from app.services.validation import fingerprint, to_utc_datetime, validate_fields

EXPECTED_HEADER = ["trade_date", "type", "symbol", "quantity", "price", "fee", "cash_amount", "notes"]
MAX_BYTES = 1_000_000
MAX_ROWS = 1000
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


def _dec(name: str, raw: str | None, errors: list[str]) -> Decimal | None:
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


TYPE_ALIASES = {
    "BUY": "BUY",
    "BOUGHT": "BUY",
    "PURCHASE": "BUY",
    "SELL": "SELL",
    "SOLD": "SELL",
    "SALE": "SELL",
    "DIVIDEND": "DIVIDEND",
    "DIV": "DIVIDEND",
    "DEPOSIT": "DEPOSIT",
    "CREDIT": "DEPOSIT",
    "SIP": "BUY",
    "WITHDRAWAL": "WITHDRAWAL",
    "WITHDRAW": "WITHDRAWAL",
    "DEBIT": "WITHDRAWAL",
    "FEE": "FEE",
    "CHARGE": "FEE",
}


def normalize(text: str, mapping: dict[str, str], date_format: str) -> str:
    """Rewrite a broker export into our canonical CSV using a column mapping (our field -> their column)."""
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(EXPECTED_HEADER)
    for rec in csv.DictReader(io.StringIO(text)):

        def get(f, rec=rec):
            return (rec.get(mapping.get(f) or "") or "").strip()

        def num(f, get=get):  # drops currency symbols, commas and signs
            return re.sub(r"[^\d.]", "", get(f))

        raw_date = get("trade_date")
        try:
            iso = datetime.strptime(raw_date, date_format).date().isoformat()
        except ValueError:
            iso = raw_date  # left as-is so the row is rejected with a clear reason
        kind = TYPE_ALIASES.get(get("type").upper(), get("type").upper())
        w.writerow(
            [
                iso,
                kind,
                get("symbol").upper(),
                num("quantity"),
                num("price"),
                num("fee"),
                num("cash_amount"),
                get("notes"),
            ]
        )
    return out.getvalue()


def decode(content: bytes) -> str:
    if len(content) > MAX_BYTES:
        raise ApiError(413, "file_too_large", f"CSV exceeds {MAX_BYTES // 1000} KB.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_csv", "File is not valid UTF-8 text.") from exc


def parse_rows(text: str) -> list[Parsed]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        raise ApiError(422, "invalid_csv_header", "The file is empty.") from None
    if header != EXPECTED_HEADER:
        raise ApiError(
            422,
            "invalid_csv_header",
            "Header must be exactly: " + ",".join(EXPECTED_HEADER),
            {"expected": EXPECTED_HEADER, "received": header},
        )
    rows: list[Parsed] = []
    for n, cells in enumerate(reader, start=1):
        if not any(c.strip() for c in cells):
            continue  # blank line
        if len(rows) >= MAX_ROWS:
            raise ApiError(422, "too_many_rows", f"CSV has more than {MAX_ROWS} rows.")
        raw = {k: (cells[i] if i < len(cells) else None) for i, k in enumerate(EXPECTED_HEADER)}
        p = Parsed(row_number=n, raw=raw)
        if len(cells) != len(EXPECTED_HEADER):
            p.status = "invalid"
            p.reasons.append(f"Expected {len(EXPECTED_HEADER)} columns, found {len(cells)}")
            rows.append(p)
            continue
        rows.append(p)
    return rows


def _check_row(
    p: Parsed, assets: dict, existing_fps: set[str], seen: dict[str, int], pid, currency: str
) -> None:
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
    p.symbol = (raw["symbol"] or "").strip().upper() or None
    p.quantity = _dec("quantity", raw["quantity"], errors)
    p.price = _dec("price", raw["price"], errors)
    fee = _dec("fee", raw["fee"], errors)
    p.fee = fee if fee is not None else ZERO
    p.cash_amount = _dec("cash_amount", raw["cash_amount"], errors)
    p.notes = (raw["notes"] or "").strip()[:500] or None
    if not errors:
        errors.extend(
            validate_fields(
                type=p.type,
                symbol=p.symbol,
                quantity=p.quantity,
                price=p.price,
                fee=p.fee,
                cash_amount=p.cash_amount,
            )
        )
    if p.symbol and p.symbol not in assets:  # Indian brokers omit the exchange suffix
        p.symbol = next((p.symbol + x for x in (".NS", ".BO") if p.symbol + x in assets), p.symbol)
    if p.symbol and p.symbol not in assets:
        errors.append(f"Unknown symbol '{p.symbol}'")
    elif p.symbol and assets[p.symbol].currency != currency:
        errors.append(f"{p.symbol} trades in {assets[p.symbol].currency}, not {currency}")
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


def analyze(
    s: Session,
    portfolio: Portfolio,
    content: bytes,
    mapping: dict | None = None,
    date_format: str = "%Y-%m-%d",
) -> list[Parsed]:
    text = decode(content)
    rows = parse_rows(normalize(text, mapping, date_format) if mapping else text)
    assets = repo.assets_by_symbol(s)
    existing = repo.all_transactions(s, portfolio.id)
    existing_fps = {t.fingerprint for t in existing}
    seen: dict[str, int] = {}
    for p in rows:
        _check_row(p, assets, existing_fps, seen, portfolio.id, portfolio.base_currency)

    # Ledger rules: accept rows greedily in file order; a row that would overdraw cash
    # or oversell (given existing data and the rows accepted so far) is rejected.
    base = to_txns(existing)
    accepted: list[Txn] = []
    for p in rows:
        if p.status != "valid":
            continue
        candidate = _as_txn(p, len(base) + len(accepted) + 1)
        try:
            replay([*base, *accepted, candidate])
        except LedgerError as exc:
            p.status, p.reasons = "invalid", [str(exc)]
            continue
        accepted.append(candidate)
    return rows


def _response(rows: list[Parsed], committed: bool, result: ImportCounts | None) -> ImportResponse:
    out = [
        ImportRow(row_number=p.row_number, status=p.status, reasons=p.reasons, data=p.raw)  # type: ignore[arg-type]
        for p in rows
    ]
    return ImportResponse(
        committed=committed,
        total_rows=len(rows),
        valid=sum(p.status == "valid" for p in rows),
        invalid=sum(p.status == "invalid" for p in rows),
        duplicate=sum(p.status == "duplicate" for p in rows),
        rows=out,
        result=result,
    )


def preview(
    s: Session, portfolio: Portfolio, content: bytes, mapping=None, date_format="%Y-%m-%d"
) -> ImportResponse:
    return _response(analyze(s, portfolio, content, mapping, date_format), False, None)


def commit(
    s: Session, portfolio: Portfolio, content: bytes, mapping=None, date_format="%Y-%m-%d"
) -> ImportResponse:
    rows = analyze(s, portfolio, content, mapping, date_format)
    assets = repo.assets_by_symbol(s)
    good = [p for p in rows if p.status == "valid"]
    try:
        # One DB transaction: every valid row is written, or none are.
        for p in good:
            assert p.trade_date
            s.add(
                Transaction(
                    id=uuid.uuid4(),
                    portfolio_id=portfolio.id,
                    asset_id=assets[p.symbol].id if p.symbol else None,
                    type=p.type,
                    trade_date=to_utc_datetime(p.trade_date),
                    quantity=p.quantity,
                    price=p.price,
                    fee=p.fee,
                    cash_amount=p.cash_amount,
                    notes=p.notes,
                    fingerprint=p.fp,
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
    return _response(rows, True, counts)
