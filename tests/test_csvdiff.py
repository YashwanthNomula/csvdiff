"""Tests for csvdiff's diff engine and renderer."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from csvdiff.diff import Table, TableDiff, diff_tables, load_csv
from csvdiff.render import Renderer


def _write_csv(content: str) -> str:
    fh = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    fh.write(content)
    fh.close()
    return fh.name


def _tables(old: str, new: str, key: str = "id"):
    o = _write_csv(old)
    n = _write_csv(new)
    try:
        old_t, old_key = load_csv(o, key, False)
        new_t, new_key = load_csv(n, key, False)
    finally:
        os.unlink(o)
        os.unlink(n)
    assert old_key == new_key
    return old_t, new_t, old_key


def _renderer(old: Table, new: Table) -> Renderer:
    return Renderer(
        color=False,
        width=40,
        old_headers=old.headers,
        new_headers=new.headers,
        old_key_index=old.key_index,
        new_key_index=new.key_index,
    )


OLD = "id,name,price\n1,apple,1.00\n2,banana,0.50\n3,cherry,2.00\n"
NEW = "id,name,price\n1,apple,1.20\n2,banana,0.50\n4,date,3.00\n"


def test_identical_files():
    old, new, key = _tables(OLD, OLD)
    diff = diff_tables(old, new, key)
    assert diff.is_empty
    out = _renderer(old, new).render(diff, "a.csv", "b.csv")
    assert "identical" in out


def test_cell_change_detected():
    old, new, key = _tables(OLD, NEW)
    diff = diff_tables(old, new, key)
    assert len(diff.changed_rows) == 1
    row = diff.changed_rows[0]
    assert row.key == "1"
    assert row.changes[0].column == "price"
    assert row.changes[0].old == "1.00"
    assert row.changes[0].new == "1.20"


def test_added_and_removed_rows():
    old, new, key = _tables(OLD, NEW)
    diff = diff_tables(old, new, key)
    assert [k for k, _ in diff.added_rows] == ["4"]
    assert [k for k, _ in diff.removed_rows] == ["3"]
    assert diff.unchanged_row_count == 1  # id=2 unchanged


def test_render_shows_old_to_new():
    old, new, key = _tables(OLD, NEW)
    diff = diff_tables(old, new, key)
    out = _renderer(old, new).render(diff, "a.csv", "b.csv")
    assert "1.00" in out and "1.20" in out
    assert "→" in out
    assert "1 added" in out and "1 removed" in out and "1 changed" in out


def test_added_and_removed_columns():
    old, new, key = _tables(
        "id,name,old_col\n1,x,9\n",
        "id,name,new_col\n1,x,9\n",
    )
    diff = diff_tables(old, new, key)
    assert diff.added_columns == ["new_col"]
    assert diff.removed_columns == ["old_col"]
    assert not diff.is_empty


def test_moved_column_detected():
    old, new, key = _tables(
        "id,a,b\n1,2,3\n",
        "id,b,a\n1,3,2\n",
    )
    diff = diff_tables(old, new, key)
    moved = {name: (oi, ni) for name, oi, ni in diff.moved_columns}
    assert moved["a"] == (1, 2)
    assert moved["b"] == (2, 1)
    # values aligned by name, so no cell changes
    assert not diff.changed_rows


def test_key_by_index():
    old, new, key = _tables("id,name\n1,x\n", "id,name\n1,y\n", key="0")
    assert key == "id"
    diff = diff_tables(old, new, key)
    assert diff.changed_rows[0].key == "1"


def test_no_header_mode():
    o = _write_csv("a,1\nb,2\n")
    n = _write_csv("a,1\nb,3\n")
    try:
        old_t, old_key = load_csv(o, "0", True)
        new_t, new_key = load_csv(n, "0", True)
    finally:
        os.unlink(o)
        os.unlink(n)
    assert old_t.headers == ["col_0", "col_1"]
    diff = diff_tables(old_t, new_t, old_key)
    assert diff.changed_rows[0].changes[0].column == "col_1"


def test_duplicate_key_warns():
    o = _write_csv("id,name\n1,x\n1,y\n")
    try:
        table, _ = load_csv(o, "id", False)
    finally:
        os.unlink(o)
    assert len(table.warnings) == 1
    assert "duplicate key" in table.warnings[0]


def test_missing_file_raises():
    try:
        load_csv("/nonexistent/xyz.csv", "id", False)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError")


def test_empty_diff_properties():
    diff = TableDiff(key_column="id")
    assert diff.is_empty
    assert diff.cells_changed == 0
