"""Read an uploaded CSV or Excel (.xlsx) file into a header + rows of strings."""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from openpyxl import load_workbook

from app.errors import ApiError

MAX_BYTES = 2_000_000
MAX_ROWS = 1000
ROW_ERROR = "__row_error__"  # set on CSV rows whose cell count doesn't match the header


@dataclass
class Table:
    columns: list[str]
    rows: list[dict[str, str]]


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


def _from_rows(raw: list[list[str]]) -> Table:
    # Broker sheets often start with titles; the header is the first row with 3+ filled cells.
    start = next((i for i, r in enumerate(raw) if sum(bool(c) for c in r) >= 3), None)
    if start is None:  # tiny file: treat the first non-empty row as the header
        start = next((i for i, r in enumerate(raw) if any(r)), None)
    if start is None:
        raise ApiError(422, "invalid_file", "The file is empty.")
    columns = [c or f"column_{i + 1}" for i, c in enumerate(raw[start])]
    rows: list[dict[str, str]] = []
    for cells in raw[start + 1 :]:
        if not any(cells):
            continue
        if len(rows) >= MAX_ROWS:
            raise ApiError(422, "too_many_rows", f"The file has more than {MAX_ROWS} rows.")
        rec = {c: (cells[i] if i < len(cells) else "") for i, c in enumerate(columns)}
        if len(cells) > len(columns) and any(cells[len(columns) :]):
            rec[ROW_ERROR] = f"Expected {len(columns)} columns, found {len(cells)}"
        rows.append(rec)
    return Table(columns, rows)


def read_table(filename: str, content: bytes) -> Table:
    if len(content) > MAX_BYTES:
        raise ApiError(413, "file_too_large", f"The file exceeds {MAX_BYTES // 1_000_000} MB.")
    if filename.lower().endswith((".xlsx", ".xlsm")) or content[:2] == b"PK":
        try:
            ws = load_workbook(io.BytesIO(content), read_only=True, data_only=True).worksheets[0]
            return _from_rows([[_cell(c) for c in row] for row in ws.iter_rows(values_only=True)])
        except ApiError:
            raise
        except Exception as exc:  # corrupt or password-protected workbook
            raise ApiError(
                422,
                "invalid_file",
                "Could not read this Excel file (is it .xlsx and not password-protected?).",
            ) from exc
    if filename.lower().endswith(".xls"):
        raise ApiError(
            422, "invalid_file", "Old .xls files aren't supported. Save it as .xlsx or .csv and try again."
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ApiError(422, "invalid_csv", "File is not valid UTF-8 text.") from exc
    return _from_rows([[c.strip() for c in row] for row in csv.reader(io.StringIO(text))])
