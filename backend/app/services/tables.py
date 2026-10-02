"""Read an uploaded CSV or Excel (.xlsx) file into tables of strings.

Statements often stack several small tables in one sheet (personal details, a summary, then the
holdings). ``read_tables`` finds every table; ``read_table`` returns the one whose headers look most
like holdings/transactions, or the one the user picked. Tables are split wherever a new header row,
a title line, a totals row or a blank row appears, so files don't need blank-row separators.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import xlrd
from openpyxl import load_workbook

from app.errors import ApiError

MAX_BYTES = 2_000_000
MAX_ROWS = 1000
MAX_SHEETS = 5
PREVIEW_ROWS, PREVIEW_COLS = 80, 16
ROW_ERROR = "__row_error__"  # set on rows with more cells than the header

# Header words that suggest a table is about holdings or transactions (one point per category).
HINTS = [
    r"symbol|ticker|scrip|instrument|scheme|fund|isin|stock|name",
    r"qty|quantity|units|shares",
    r"price|nav|rate|avg|average|cost",
    r"invest|amount|value",
    r"date",
    r"type|action|side|transaction|narration",
]
_INVISIBLE = re.compile(r"[\s​‌‍⁠﻿ ]+")
_SENSITIVE_LABEL = re.compile(
    r"^(name|mobile|phone|contact|email|e-mail|pan|aadhaar|aadhar|dob|date of birth|address|client id|ucc)\b",
    re.I,
)
_SENSITIVE_VALUE = re.compile(r"^([A-Z]{5}\d{4}[A-Z]|\d{10,}|[^@\s]+@[^@\s]+\.[^@\s]+)$")


@dataclass
class Table:
    columns: list[str]
    rows: list[dict[str, str]]
    sheet: str = ""
    title: str = ""  # nearest single-cell line above the header, e.g. "HOLDINGS AS ON 2026-10-02"
    header_row: int = 1  # 1-based row number in the sheet
    end_row: int = 1  # 1-based last row of the table
    score: float = 0.0
    extra: dict = field(default_factory=dict)


def _clean(s: str) -> str:
    return _INVISIBLE.sub(" ", s).strip()


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):  # Excel stores 970.019 as 970.0189999999999; trim that noise
        return format(Decimal(repr(round(v, 8))).normalize(), "f")
    return _clean(str(v))


def _numeric(c: str) -> bool:
    return bool(re.fullmatch(r"[-+(]?[\d,]*\.?\d+\)?%?", c.replace("₹", "").replace("$", "").strip()))


def _filled(cells: list[str]) -> list[str]:
    return [c for c in cells if c]


def _header_like(cells: list[str]) -> bool:
    f = _filled(cells)
    return len(f) >= 3 and len(set(f)) == len(f) and sum(not _numeric(c) for c in f) >= 0.8 * len(f)


def _title_like(cells: list[str]) -> bool:
    f = _filled(cells)
    return len(f) == 1 and not _numeric(f[0])


def _total_like(cells: list[str]) -> bool:
    first = next(iter(_filled(cells)), "")
    return bool(re.match(r"(grand\s+)?total\b", first, re.I))


def _ends_table(cells: list[str]) -> bool:
    """After at least one data row: a title line, a totals row, or another header row starts something new."""
    return (
        _title_like(cells)
        or _total_like(cells)
        or (_header_like(cells) and not any(_numeric(c) for c in cells if c))
    )


def _build(sheet: str, raw: list[list[str]], h: int, *, until_blank: bool = True) -> Table:
    head = raw[h]
    width = max((i + 1 for i, c in enumerate(head) if c), default=0)  # ignore empty trailing header cells
    columns = [c or f"column_{i + 1}" for i, c in enumerate(head[:width])]
    rows: list[dict[str, str]] = []
    blanks, j, last = 0, h + 1, h
    while j < len(raw):
        cells = raw[j]
        if not any(cells):
            blanks += 1
            # a few spacer rows between header and data are common; once data started, a blank row ends it
            if (until_blank and rows) or blanks > 3:
                break
            j += 1
            continue
        if rows and _ends_table(cells):
            break
        blanks = 0
        if len(rows) >= MAX_ROWS:
            raise ApiError(422, "too_many_rows", f"The table has more than {MAX_ROWS} rows.")
        rec = {c: (cells[i] if i < len(cells) else "") for i, c in enumerate(columns)}
        if any(cells[width:]):
            rec[ROW_ERROR] = f"Expected {width} columns, found {max(i for i, c in enumerate(cells) if c) + 1}"
        rows.append(rec)
        last = j
        j += 1
    title = next((_filled(raw[k])[0] for k in range(h - 1, max(h - 5, -1), -1) if _title_like(raw[k])), "")
    score = 10 * sum(any(re.search(p, c, re.I) for c in columns) for p in HINTS) + min(len(rows), 50) / 10
    return Table(columns, rows, sheet, title, h + 1, last + 1, score)


def _find_tables(sheet: str, raw: list[list[str]]) -> list[Table]:
    tables, i = [], 0
    while i < len(raw):
        if _header_like(raw[i]) and any(any(r) for r in raw[i + 1 : i + 5]):
            t = _build(sheet, raw, i)
            tables.append(t)
            i = max(t.end_row, i + 1)  # continue right after this table
        else:
            i += 1
    return tables


def _xlsx_sheets(content: bytes) -> list[tuple[str, list[list[str]]]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets[:MAX_SHEETS]:
        ws.reset_dimensions()  # some exporters write a wrong sheet size, which would hide rows
        out.append((ws.title, [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)]))
    return out


def _xls_sheets(content: bytes) -> list[tuple[str, list[list[str]]]]:
    wb = xlrd.open_workbook(file_contents=content)
    out = []
    for ws in wb.sheets()[:MAX_SHEETS]:
        rows = []
        for r in range(ws.nrows):
            row = []
            for c in range(ws.ncols):
                cell = ws.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(xlrd.xldate_as_datetime(cell.value, wb.datemode).date().isoformat())
                elif cell.ctype == xlrd.XL_CELL_NUMBER:
                    row.append(_cell(int(cell.value) if cell.value == int(cell.value) else cell.value))
                else:
                    row.append(_cell(cell.value))
            rows.append(row)
        out.append((ws.name, rows))
    return out


def _decode(content: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):  # cp1252 covers CSVs saved by Excel on Windows
        try:
            return content.decode(enc)
        except UnicodeError:
            continue
    raise ApiError(422, "invalid_csv", "Could not read this text file's encoding.")


def _text_rows(content: bytes) -> list[list[str]]:
    text = _decode(content)
    sample = text[:4096]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    return [[_clean(c) for c in row] for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _sheets(filename: str, content: bytes) -> list[tuple[str, list[list[str]]]]:
    if len(content) > MAX_BYTES:
        raise ApiError(413, "file_too_large", f"The file exceeds {MAX_BYTES // 1_000_000} MB.")
    if content[:4] == b"%PDF":
        raise ApiError(
            422,
            "invalid_file",
            "PDF statements can't be read yet. Download the Excel or CSV version of the statement instead.",
        )
    try:
        if content[:2] == b"PK":  # .xlsx / .xlsm are zip archives
            return _xlsx_sheets(content)
        if content[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # old binary .xls
            return _xls_sheets(content)
    except Exception as exc:  # corrupt or password-protected workbook
        raise ApiError(
            422, "invalid_file", "Could not read this Excel file (is it password-protected or damaged?)."
        ) from exc
    if filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        raise ApiError(422, "invalid_file", "This doesn't look like a valid Excel file.")
    return [("", _text_rows(content))]


def _tables_from(sheets: list[tuple[str, list[list[str]]]]) -> list[Table]:
    found = [t for name, raw in sheets for t in _find_tables(name, raw)]
    if not found:  # tiny or oddly shaped file: treat the first non-empty row as the header
        for name, raw in sheets:
            h = next((i for i, r in enumerate(raw) if any(r)), None)
            if h is not None:
                return [_build(name, raw, h)]
        raise ApiError(422, "invalid_file", "The file is empty.")
    return found


def _choose(sheets, tables: list[Table], table_index: int | None, header_row: int | None) -> Table:
    if header_row is not None:
        name, raw = sheets[0] if table_index is None else sheets[min(table_index, len(sheets) - 1)]
        if not 1 <= header_row <= len(raw) or not any(raw[header_row - 1]):
            raise ApiError(422, "invalid_file", f"Row {header_row} is empty or outside the sheet.")
        return _build(name, raw, header_row - 1, until_blank=False)
    if table_index is not None:
        if not 0 <= table_index < len(tables):
            raise ApiError(
                422,
                "invalid_file",
                f"This file has {len(tables)} tables; there is no table {table_index + 1}.",
            )
        return tables[table_index]
    return max(tables, key=lambda t: t.score)  # ties go to the first (max keeps the earliest)


def read_tables(filename: str, content: bytes) -> list[Table]:
    """Every table found in the file, in reading order."""
    return _tables_from(_sheets(filename, content))


def read_table(
    filename: str, content: bytes, table_index: int | None = None, header_row: int | None = None
) -> Table:
    """The table to import: a chosen one, one starting at a given sheet row, or the best-looking."""
    sheets = _sheets(filename, content)
    return _choose(sheets, _tables_from(sheets), table_index, header_row)


def _mask(row: list[str]) -> list[str]:
    """Hide personal identifiers (PAN, phone, email, labelled name/address rows) in the on-screen preview."""
    labelled = bool(row and _SENSITIVE_LABEL.match(row[0]))
    return [
        c if (i == 0 or not c or not (labelled or _SENSITIVE_VALUE.match(c))) else "••••"
        for i, c in enumerate(row)
    ]


def inspect(
    filename: str, content: bytes, table_index: int | None = None, header_row: int | None = None
) -> dict:
    """Everything the import screen needs: the tables found, the chosen table's columns and sample rows,
    and a masked, spreadsheet-style view of each sheet with the tables located in it."""
    sheets = _sheets(filename, content)
    tables = _tables_from(sheets)
    chosen = _choose(sheets, tables, table_index, header_row)
    best = max(range(len(tables)), key=lambda i: tables[i].score)
    from app.services.mapping import date_format_hint, suggest  # local import: mapping depends on Table

    suggested = suggest(chosen)
    date_col = suggested["holdings"].get("trade_date") or suggested["transactions"].get("trade_date")
    return {
        "suggested": suggested,
        "date_format": date_format_hint(chosen, date_col) if date_col else "",
        "tables": [
            {
                "index": i,
                "sheet": t.sheet,
                "title": t.title,
                "header_row": t.header_row,
                "end_row": t.end_row,
                "columns": t.columns,
                "row_count": len(t.rows),
            }
            for i, t in enumerate(tables)
        ],
        "selected": None if header_row is not None else (table_index if table_index is not None else best),
        "columns": chosen.columns,
        "sample": chosen.rows[:5],
        "row_count": len(chosen.rows),
        "header_row": chosen.header_row,
        "chosen": {"sheet": chosen.sheet, "header_row": chosen.header_row, "end_row": chosen.end_row},
        "sheets": [
            {
                "name": name,
                "total_rows": len(raw),
                "rows": [_mask(r[:PREVIEW_COLS]) for r in raw[:PREVIEW_ROWS]],
                "columns": min(PREVIEW_COLS, max((len(r) for r in raw), default=0)),
            }
            for name, raw in sheets
        ],
    }


@dataclass
class Source:
    """An uploaded file plus which table in it to read."""

    filename: str
    content: bytes
    table_index: int | None = None
    header_row: int | None = None

    def table(self) -> Table:
        return read_table(self.filename, self.content, self.table_index, self.header_row)
