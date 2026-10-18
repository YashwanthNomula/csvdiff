"""Core diff engine for csvdiff."""

from __future__ import annotations

import csv
import difflib
from dataclasses import dataclass, field

#: Minimum difflib SequenceMatcher ratio (on lowercased column names) for a
#: removed/added column pair to be reported as a possible rename.
RENAME_SIMILARITY_THRESHOLD = 0.6


@dataclass
class RenameSuggestion:
    """A fuzzy guess that a removed column was renamed to an added column."""

    old: str
    new: str
    similarity: float  # SequenceMatcher ratio on lowercased names


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
    key_display: dict[str, str] = field(default_factory=dict)
    """Map each row key to how it first appeared in the file.

    When ``ignore_case`` is on, row keys are folded to lowercase for
    matching, while ``key_display`` keeps the original casing so reports
    still show the value as written in the file. Without ``ignore_case``
    it maps every key to itself.
    """


def _index_rows(
    records: list[list[str]], key_index: int, ignore_case: bool = False
) -> tuple[dict[str, list[str]], list[str], dict[str, str]]:
    rows: dict[str, list[str]] = {}
    warnings: list[str] = []
    key_display: dict[str, str] = {}
    for line_no, record in enumerate(records, start=2):
        raw = record[key_index] if key_index < len(record) else ""
        key = raw.lower() if ignore_case else raw
        if key in rows:
            warnings.append(
                f"duplicate key {raw!r} on line {line_no}; keeping the first occurrence"
            )
            continue
        rows[key] = record
        key_display[key] = raw
    return rows, warnings, key_display


def drop_columns(table: Table, indices: set[int]) -> Table:
    """Return a copy of ``table`` with the given column indices removed.

    Used to implement ``--ignore-cols``: dropped columns are invisible to
    schema detection, cell comparison, and row snippets alike. ``indices``
    must not contain ``table.key_index``.
    """
    keep = [i for i in range(len(table.headers)) if i not in indices]
    return Table(
        headers=[table.headers[i] for i in keep],
        rows={
            key: [row[i] for i in keep if i < len(row)]
            for key, row in table.rows.items()
        },
        key_index=keep.index(table.key_index),
        warnings=table.warnings,
        key_display=table.key_display,
    )


def load_csv(
    path: str, key: str, no_header: bool, ignore_case: bool = False
) -> tuple[Table, str]:
    """Load a CSV file and index its rows by the key column.

    ``key`` may be a header name or a 0-based column index. When
    ``ignore_case`` is on, header names and key values are matched
    case-insensitively (reports still show each file's original casing).
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
        try:
            key_index = headers.index(key)
        except ValueError:
            if ignore_case:
                lowered = key.lower()
                matches = [i for i, h in enumerate(headers) if h.lower() == lowered]
                if matches:
                    key_index = matches[0]
                else:
                    raise ValueError(
                        f"unknown key column {key!r}; "
                        f"available: {', '.join(headers)}"
                    ) from None
            else:
                raise ValueError(f"unknown key column {key!r}") from None

    if not 0 <= key_index < max(len(headers), 1):
        raise ValueError(f"key column {key!r} out of range")

    warnings: list[str] = []
    if ignore_case and not no_header:
        seen: dict[str, str] = {}
        for header in headers:
            folded = header.lower()
            if folded in seen and seen[folded] != header:
                warnings.append(
                    f"headers {seen[folded]!r} and {header!r} differ only by "
                    "case; matching case-insensitively, using the first"
                )
            else:
                seen.setdefault(folded, header)

    rows, row_warnings, key_display = _index_rows(records, key_index, ignore_case)
    warnings.extend(row_warnings)
    key_name = headers[key_index] if headers and key_index < len(headers) else key
    return Table(
        headers=headers,
        rows=rows,
        key_index=key_index,
        warnings=warnings,
        key_display=key_display,
    ), key_name


@dataclass
class TableDiff:
    key_column: str
    added_columns: list[str] = field(default_factory=list)
    removed_columns: list[str] = field(default_factory=list)
    moved_columns: list[tuple[str, int, int]] = field(default_factory=list)
    rename_suggestions: list[RenameSuggestion] = field(default_factory=list)
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


def _try_float(text: str) -> float | None:
    """Parse ``text`` as a float, returning None when it is not numeric."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _cells_equal(old: str, new: str, tol: float) -> bool:
    """Decide whether two cell values count as equal.

    Identical strings are always equal. When ``tol > 0`` and both cells parse
    as numbers (ints, floats, scientific notation), an absolute difference
    of at most ``tol`` also counts as equal. Non-numeric cells fall back to
    plain string comparison.
    """
    if old == new:
        return True
    if tol <= 0:
        return False
    old_num, new_num = _try_float(old), _try_float(new)
    if old_num is None or new_num is None:
        return False
    return abs(old_num - new_num) <= tol


def suggest_renames(
    removed_columns: list[str],
    added_columns: list[str],
    threshold: float = RENAME_SIMILARITY_THRESHOLD,
) -> list[RenameSuggestion]:
    """Fuzzy-match removed columns against added ones to suggest renames.

    Every removed/added pair is scored with ``difflib.SequenceMatcher`` on
    lowercased names; pairs scoring at least ``threshold`` are candidates.
    The best-scoring pairs are then assigned greedily — the highest score
    wins, and neither a removed nor an added column is ever reused. Results
    are ordered by the removed columns' original order.
    """
    candidates: list[tuple[float, int, int]] = []
    for i, old in enumerate(removed_columns):
        for j, new in enumerate(added_columns):
            score = difflib.SequenceMatcher(None, old.lower(), new.lower()).ratio()
            if score >= threshold:
                candidates.append((score, i, j))
    # best score first; indexes as deterministic tie-breaks
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_old: set[int] = set()
    used_new: set[int] = set()
    matched: list[tuple[int, RenameSuggestion]] = []
    for score, i, j in candidates:
        if i in used_old or j in used_new:
            continue
        used_old.add(i)
        used_new.add(j)
        matched.append(
            (i, RenameSuggestion(old=removed_columns[i], new=added_columns[j], similarity=score))
        )
    matched.sort(key=lambda m: m[0])
    return [suggestion for _, suggestion in matched]


def _fold(name: str, ignore_case: bool) -> str:
    """Fold a header name for comparison when ``ignore_case`` is on."""
    return name.lower() if ignore_case else name


def diff_tables(
    old: Table,
    new: Table,
    key_name: str,
    tol: float = 0.0,
    detect_renames: bool = True,
    ignore_case: bool = False,
) -> TableDiff:
    """Compute the column-aware diff between two loaded tables.

    ``tol`` is the numeric tolerance for float-heavy data: two cells that
    both parse as numbers count as equal when ``abs(a - b) <= tol``.
    Defaults to 0, i.e. exact comparison only.

    ``detect_renames`` enables fuzzy rename suggestions between removed and
    added columns (see :func:`suggest_renames`). It never changes the
    added/removed lists themselves — suggestions are advisory only.

    ``ignore_case`` matches headers and key values case-insensitively, so
    ``ID`` vs ``id`` no longer shows up as a removed/added column pair.
    Reports still display each file's original casing; cell values (other
    than keys) are always compared case-sensitively.
    """
    result = TableDiff(key_column=key_name, warnings=old.warnings + new.warnings)

    old_fold = {_fold(h, ignore_case): i for i, h in enumerate(old.headers)}
    new_fold = {_fold(h, ignore_case): i for i, h in enumerate(new.headers)}
    result.added_columns = [
        h for h in new.headers if _fold(h, ignore_case) not in old_fold
    ]
    result.removed_columns = [
        h for h in old.headers if _fold(h, ignore_case) not in new_fold
    ]
    for folded, oi in old_fold.items():
        if folded in new_fold:
            ni = new_fold[folded]
            if oi != ni:
                # display the new file's header name for moved columns
                result.moved_columns.append((new.headers[ni], oi, ni))
    if detect_renames:
        result.rename_suggestions = suggest_renames(
            result.removed_columns, result.added_columns
        )

    # folded name -> (old index, new index) for columns present in both files
    shared = [
        (folded, oi, new_fold[folded])
        for folded, oi in old_fold.items()
        if folded in new_fold
    ]
    if ignore_case:
        # the key column is an identifier, not data: its folded value already
        # matched, so a case-only difference in the raw key must not count
        # as a cell change
        key_folds = set()
        if old.headers:
            key_folds.add(_fold(old.headers[old.key_index], ignore_case))
        if new.headers:
            key_folds.add(_fold(new.headers[new.key_index], ignore_case))
        shared = [s for s in shared if s[0] not in key_folds]

    for key in new.rows:
        if key not in old.rows:
            result.added_rows.append(
                (new.key_display.get(key, key), new.rows[key])
            )
            continue
        o, n = old.rows[key], new.rows[key]
        changes = []
        for _folded, oi, ni in shared:
            ov = o[oi] if oi < len(o) else ""
            nv = n[ni] if ni < len(n) else ""
            if not _cells_equal(ov, nv, tol):
                # display the new file's header name for changed cells
                changes.append(CellChange(column=new.headers[ni], old=ov, new=nv))
        display_key = old.key_display.get(key, key)
        if changes:
            result.changed_rows.append(RowChange(key=display_key, changes=changes))
        else:
            result.unchanged_row_count += 1

    for key in old.rows:
        if key not in new.rows:
            result.removed_rows.append(
                (old.key_display.get(key, key), old.rows[key])
            )

    return result
