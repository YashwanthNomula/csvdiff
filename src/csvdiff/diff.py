"""Core diff engine for csvdiff."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field


@dataclass
class CellChange:
    column: str
    old: str
    new: str


@dataclass
class RowChange:
    key: str
    changes: list[CellChange] = field(default_factory=list)


@dataclass
class Table:
    """A parsed CSV: ordered headers plus rows keyed by the key column."""

    headers: list[str]
    rows: dict[str, list[str]]  # key -> row values
    key_index: int
    warnings: list[str] = field(default_factory=list)


def _index_rows(
    records: list[list[str]], key_index: int
) -> tuple[dict[str, list[str]], list[str]]:
    rows: dict[str, list[str]] = {}
    warnings: list[str] = []
    for line_no, record in enumerate(records, start=2):
        key = record[key_index] if key_index < len(record) else ""
        if key in rows:
            warnings.append(
                f"duplicate key {key!r} on line {line_no}; keeping the first occurrence"
            )
            continue
        rows[key] = record
    return rows, warnings


def load_csv(path: str, key: str, no_header: bool) -> tuple[Table, str]:
    """Load a CSV file and index its rows by the key column.

    ``key`` may be a header name or a 0-based column index.
    """
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(fh, dialect)
        records = [row for row in reader if row]

    if no_header:
        ncols = max((len(r) for r in records), default=0)
        headers = [f"col_{i}" for i in range(ncols)]
    else:
        headers = records.pop(0) if records else []

    if key.isdigit():
        key_index = int(key)
    else:
        key_index = headers.index(key)  # raises ValueError if unknown

    if not 0 <= key_index < max(len(headers), 1):
        raise ValueError(f"key column {key!r} out of range")

    rows, warnings = _index_rows(records, key_index)
    key_name = headers[key_index] if headers and key_index < len(headers) else key
    return Table(
        headers=headers, rows=rows, key_index=key_index, warnings=warnings
    ), key_name


@dataclass
class TableDiff:
    key_column: str
    added_columns: list[str] = field(default_factory=list)
    removed_columns: list[str] = field(default_factory=list)
    moved_columns: list[tuple[str, int, int]] = field(default_factory=list)
    added_rows: list[tuple[str, list[str]]] = field(default_factory=list)
    removed_rows: list[tuple[str, list[str]]] = field(default_factory=list)
    changed_rows: list[RowChange] = field(default_factory=list)
    unchanged_row_count: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def cells_changed(self) -> int:
        return sum(len(r.changes) for r in self.changed_rows)

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_columns
            or self.removed_columns
            or self.moved_columns
            or self.added_rows
            or self.removed_rows
            or self.changed_rows
        )


def _col_of(headers: list[str], name: str, row: list[str]) -> str:
    try:
        idx = headers.index(name)
    except ValueError:
        return ""
    return row[idx] if idx < len(row) else ""


def diff_tables(old: Table, new: Table, key_name: str) -> TableDiff:
    """Compute the column-aware diff between two loaded tables."""
    result = TableDiff(key_column=key_name, warnings=old.warnings + new.warnings)

    old_set, new_set = set(old.headers), set(new.headers)
    result.added_columns = [h for h in new.headers if h not in old_set]
    result.removed_columns = [h for h in old.headers if h not in new_set]
    for name in old.headers:
        if name in new_set and name not in result.added_columns:
            oi, ni = old.headers.index(name), new.headers.index(name)
            if oi != ni:
                result.moved_columns.append((name, oi, ni))

    shared = [h for h in old.headers if h in new_set]

    for key in new.rows:
        if key not in old.rows:
            result.added_rows.append((key, new.rows[key]))
            continue
        o, n = old.rows[key], new.rows[key]
        changes = []
        for col in shared:
            ov, nv = _col_of(old.headers, col, o), _col_of(new.headers, col, n)
            if ov != nv:
                changes.append(CellChange(column=col, old=ov, new=nv))
        if changes:
            result.changed_rows.append(RowChange(key=key, changes=changes))
        else:
            result.unchanged_row_count += 1

    for key in old.rows:
        if key not in new.rows:
            result.removed_rows.append((key, old.rows[key]))

    return result
