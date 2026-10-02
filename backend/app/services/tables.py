"""Read an uploaded CSV or Excel (.xlsx) file into tables of strings.

Statements often stack several small tables in one sheet (personal details, a summary, then the
holdings), separated by blank rows. ``read_tables`` finds every table; ``read_table`` returns the one
whose headers look most like holdings/transactions, or the one the user picked.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from openpyxl import load_workbook

from app.errors import ApiError

MAX_BYTES = 2_000_000
MAX_ROWS = 1000
MAX_SHEETS = 5
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


@dataclass
class Table:
    columns: list[str]
    rows: list[dict[str, str]]
    sheet: str = ""
    title: str = ""  # nearest single-cell line above the header, e.g. "HOLDINGS AS ON 2026-10-02"
    header_row: int = 1  # 1-based row number in the sheet
    score: float = 0.0
    extra: dict = field(default_factory=dict)


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return format(Decimal(repr(v)), "f")  # avoids 1e-05 style output
    return str(v).strip()


def _numeric(c: str) -> bool:
    return bool(re.fullmatch(r"[-+(]?[\d,]*\.?\d+\)?%?", c.replace("₹", "").replace("$", "").strip()))


def _is_header(cells: list[str]) -> bool:
    filled = [c for c in cells if c]
    return (
        len(filled) >= 3
        and len(set(filled)) == len(filled)
        and sum(not _numeric(c) for c in filled) >= 0.8 * len(filled)
    )


def _is_total(cells: list[str]) -> bool:
    first = next((c for c in cells if c), "")
    return bool(re.match(r"(grand\s+)?total\b", first, re.I))


def _build(sheet: str, raw: list[list[str]], h: int, *, until_blank: bool = True) -> Table:
    columns = [c or f"column_{i + 1}" for i, c in enumerate(raw[h])]
    rows: list[dict[str, str]] = []
    blanks, j = 0, h + 1
    while j < len(raw):
        cells = raw[j]
        if not any(cells):
            blanks += 1
            # a few spacer rows between header and data are common; once data started, a blank row ends it
            if (until_blank and rows) or blanks > 3:
                break
            j += 1
            continue
        if _is_total(cells):
            break
        blanks = 0
        if len(rows) >= MAX_ROWS:
            raise ApiError(422, "too_many_rows", f"The table has more than {MAX_ROWS} rows.")
        rec = {c: (cells[i] if i < len(cells) else "") for i, c in enumerate(columns)}
        if len(cells) > len(columns) and any(cells[len(columns) :]):
            rec[ROW_ERROR] = f"Expected {len(columns)} columns, found {len(cells)}"
        rows.append(rec)
        j += 1
    title = next(
        (
            next(c for c in raw[k] if c)
            for k in range(h - 1, max(h - 5, -1), -1)
            if sum(bool(c) for c in raw[k]) == 1
        ),
        "",
    )
    score = 10 * sum(any(re.search(p, c, re.I) for c in columns) for p in HINTS) + min(len(rows), 50) / 10
    return Table(columns, rows, sheet, title, h + 1, score)


def _find_tables(sheet: str, raw: list[list[str]]) -> list[Table]:
    tables, i = [], 0
    while i < len(raw):
        if _is_header(raw[i]) and any(any(r) for r in raw[i + 1 : i + 5]):
            t = _build(sheet, raw, i)
            tables.append(t)
            i += len(t.rows) + 1
        else:
            i += 1
    return tables


def _sheets(filename: str, content: bytes) -> list[tuple[str, list[list[str]]]]:
    if len(content) > MAX_BYTES:
        raise ApiError(413, "file_too_large", f"The file exceeds {MAX_BYTES // 1_000_000} MB.")
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")) or content[:2] == b"PK":
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            return [
                (ws.title, [[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)])
                for ws in wb.worksheets[:MAX_SHEETS]
            ]
        except Exception as exc:  # corrupt or password-protected workbook
            raise ApiError(
                422,
                "invalid_file",
                "Could not read this Excel file (is it .xlsx and not password-protected?).",
            ) from exc
    if name.endswith(".xls"):
        raise ApiError(
            422, "invalid_file", "Old .xls files aren't supported. Save it as .xlsx or .csv and try again."
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_csv", "File is not valid UTF-8 text.") from exc
    return [("", [[c.strip() for c in row] for row in csv.reader(io.StringIO(text))])]


def read_tables(filename: str, content: bytes) -> list[Table]:
    """Every table found in the file, in reading order."""
    sheets = _sheets(filename, content)
    found = [t for name, raw in sheets for t in _find_tables(name, raw)]
    if not found:  # tiny or oddly shaped file: treat the first non-empty row as the header
        for name, raw in sheets:
            h = next((i for i, r in enumerate(raw) if any(r)), None)
            if h is not None:
                return [_build(name, raw, h)]
        raise ApiError(422, "invalid_file", "The file is empty.")
    return found


def read_table(
    filename: str, content: bytes, table_index: int | None = None, header_row: int | None = None
) -> Table:
    """The table to import: a chosen one, one starting at a given sheet row, or the best-looking."""
    if header_row is not None:
        sheets = _sheets(filename, content)
        name, raw = sheets[0] if table_index is None else sheets[min(table_index, len(sheets) - 1)]
        if not 1 <= header_row <= len(raw) or not any(raw[header_row - 1]):
            raise ApiError(422, "invalid_file", f"Row {header_row} is empty or outside the sheet.")
        return _build(name, raw, header_row - 1, until_blank=False)
    tables = read_tables(filename, content)
    if table_index is not None:
        if not 0 <= table_index < len(tables):
            raise ApiError(
                422,
                "invalid_file",
                f"This file has {len(tables)} tables; there is no table {table_index + 1}.",
            )
        return tables[table_index]
    return max(tables, key=lambda t: t.score)  # ties go to the first (max keeps the earliest)


@dataclass
class Source:
    """An uploaded file plus which table in it to read."""

    filename: str
    content: bytes
    table_index: int | None = None
    header_row: int | None = None

    def table(self) -> Table:
        return read_table(self.filename, self.content, self.table_index, self.header_row)
