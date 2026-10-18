"""Tests for csvdiff's diff engine and renderer."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from csvdiff.diff import (
    Table,
    TableDiff,
    diff_tables,
    drop_columns,
    load_csv,
    suggest_renames,
)
from csvdiff.cli import main
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


# --- --ignore-cols ---------------------------------------------------------

def test_drop_columns_removes_noisy_cell_changes():
    old, new, key = _tables(
        "id,ts,name\n1,2024-01-01,x\n",
        "id,ts,name\n1,2024-06-30,y\n",
    )
    diff = diff_tables(drop_columns(old, {1}), drop_columns(new, {1}), key)
    assert len(diff.changed_rows) == 1
    assert [c.column for c in diff.changed_rows[0].changes] == ["name"]


def test_drop_columns_adjusts_key_index():
    old, new, key = _tables(
        "ts,id,name\n2024-01-01,1,x\n",
        "ts,id,name\n2024-06-30,1,y\n",
        key="id",
    )
    old_d, new_d = drop_columns(old, {0}), drop_columns(new, {0})
    assert old_d.headers == ["id", "name"]
    assert old_d.key_index == 0
    assert old_d.rows["1"] == ["1", "x"]
    diff = diff_tables(old_d, new_d, key)
    assert diff.changed_rows[0].changes[0].column == "name"


def test_ignore_cols_flag_makes_noisy_diff_identical():
    o = _write_csv("id,updated_at\n1,2024-01-01\n2,2024-01-01\n")
    n = _write_csv("id,updated_at\n1,2024-06-30\n2,2024-06-30\n")
    try:
        assert main([o, n, "--no-color"]) == 1
        assert main([o, n, "--ignore-cols", "updated_at", "--no-color"]) == 0
    finally:
        os.unlink(o)
        os.unlink(n)


def test_ignore_cols_accepts_index_and_multiple():
    o = _write_csv("id,ts,exported_by,name\n1,a,u,x\n")
    n = _write_csv("id,ts,exported_by,name\n1,b,v,y\n")
    try:
        assert main([o, n, "--ignore-cols", "ts,2", "--no-color"]) == 1
    finally:
        os.unlink(o)
        os.unlink(n)


def test_ignore_cols_unknown_column_errors():
    o = _write_csv("id\n1\n")
    n = _write_csv("id\n1\n")
    try:
        assert main([o, n, "--ignore-cols", "nope"]) == 2
    finally:
        os.unlink(o)
        os.unlink(n)


def test_ignore_cols_cannot_ignore_key_column():
    o = _write_csv("id\n1\n")
    n = _write_csv("id\n1\n")
    try:
        assert main([o, n, "--ignore-cols", "id"]) == 2
    finally:
        os.unlink(o)
        os.unlink(n)


def test_ignore_cols_hidden_from_row_snippets():
    import io
    from contextlib import redirect_stdout

    o = _write_csv("id,ts,name\n1,2024-01-01,x\n")
    n = _write_csv("id,ts,name\n1,2024-01-01,x\n2,2024-06-30,y\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--ignore-cols", "ts", "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert "ts=" not in out
    assert "name=y" in out


# --- --tol -----------------------------------------------------------------

def test_tol_equal_within_tolerance():
    old, new, key = _tables(
        "id,price\n1,1.000\n",
        "id,price\n1,1.005\n",
    )
    diff = diff_tables(old, new, key, tol=0.01)
    assert diff.is_empty
    assert diff.unchanged_row_count == 1


def test_tol_boundary_diff_equals_tol():
    # diff == tol is accepted (<= semantics); values chosen binary-exact
    old, new, key = _tables(
        "id,price\n1,2.0\n",
        "id,price\n1,2.125\n",
    )
    assert diff_tables(old, new, key, tol=0.125).is_empty
    # ...but a hair more is not
    assert not diff_tables(old, new, key, tol=0.124).is_empty


def test_tol_outside_tolerance_still_changes():
    old, new, key = _tables(
        "id,price\n1,1.00\n",
        "id,price\n1,1.20\n",
    )
    diff = diff_tables(old, new, key, tol=0.01)
    assert len(diff.changed_rows) == 1
    change = diff.changed_rows[0].changes[0]
    assert change.column == "price"
    assert change.old == "1.00" and change.new == "1.20"


def test_tol_non_numeric_cells_unaffected():
    # non-numeric cells fall back to plain string comparison
    old, new, key = _tables(
        "id,name,code\n1,apple,A100\n",
        "id,name,code\n1,banana,B200\n",
    )
    diff = diff_tables(old, new, key, tol=100.0)
    assert {c.column for c in diff.changed_rows[0].changes} == {"name", "code"}


def test_tol_mixed_numeric_and_non_numeric():
    # only the numeric pair gets tolerance; the rest compares normally
    old, new, key = _tables(
        "id,price,name\n1,1.001,x\n",
        "id,price,name\n1,1.002,y\n",
    )
    diff = diff_tables(old, new, key, tol=0.01)
    assert len(diff.changed_rows) == 1
    assert [c.column for c in diff.changed_rows[0].changes] == ["name"]


def test_tol_scientific_notation():
    # binary-exact values so the <= boundary is precise
    old, new, key = _tables(
        "id,mass\n1,1.0e0\n",
        "id,mass\n1,1.0625e0\n",
    )
    assert diff_tables(old, new, key, tol=0.0625).is_empty
    assert not diff_tables(old, new, key, tol=0.0624).is_empty


def test_tol_integers_parse_as_numbers():
    old, new, key = _tables(
        "id,count\n1,100\n",
        "id,count\n1,102\n",
    )
    assert diff_tables(old, new, key, tol=2).is_empty
    assert not diff_tables(old, new, key, tol=1).is_empty


def test_default_tol_zero_unchanged():
    # without --tol, any numeric difference still counts as a change
    old, new, key = _tables(
        "id,price\n1,1.000\n",
        "id,price\n1,1.0001\n",
    )
    assert not diff_tables(old, new, key).is_empty
    assert len(diff_tables(old, new, key).changed_rows) == 1


def test_tol_cli_text_and_html_agree():
    import io
    from contextlib import redirect_stdout

    o = _write_csv("id,price\n1,1.000\n")
    n = _write_csv("id,price\n1,1.005\n")
    try:
        # without --tol: difference found
        assert main([o, n, "--no-color"]) == 1
        # with --tol: identical in text output ...
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--tol", "0.01", "--no-color"])
        assert rc == 0
        assert "identical" in buf.getvalue()
        # ... and in HTML output
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--tol", "0.01", "--format", "html"])
        assert rc == 0
        assert "no differences found" in buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)


def test_tol_cli_negative_errors():
    o = _write_csv("id\n1\n")
    n = _write_csv("id\n1\n")
    try:
        assert main([o, n, "--tol", "-0.5"]) == 2
    finally:
        os.unlink(o)
        os.unlink(n)


def test_tol_cli_tolerance_boundary_exit_code():
    o = _write_csv("id,price\n1,2.0\n")
    n = _write_csv("id,price\n1,2.125\n")
    try:
        assert main([o, n, "--tol", "0.125", "--no-color"]) == 0
        assert main([o, n, "--tol", "0.124", "--no-color"]) == 1
    finally:
        os.unlink(o)
        os.unlink(n)


# --- --suggest-renames --------------------------------------------------------

def test_suggest_renames_detects_obvious_rename():
    old, new, key = _tables(
        "id,product_name\n1,x\n",
        "id,productName\n1,x\n",
    )
    diff = diff_tables(old, new, key)
    assert len(diff.rename_suggestions) == 1
    suggestion = diff.rename_suggestions[0]
    assert suggestion.old == "product_name"
    assert suggestion.new == "productName"
    assert suggestion.similarity >= 0.6
    # suggestions are advisory: the schema churn is still reported
    assert diff.added_columns == ["productName"]
    assert diff.removed_columns == ["product_name"]


def test_suggest_renames_no_suggestion_when_dissimilar():
    # 'category' vs 'rating' scores ~0.43 — too far apart to be a rename
    old, new, key = _tables(
        "id,category\n1,x\n",
        "id,rating\n1,x\n",
    )
    diff = diff_tables(old, new, key)
    assert diff.rename_suggestions == []
    assert diff.added_columns == ["rating"]
    assert diff.removed_columns == ["category"]


def test_suggest_renames_greedy_no_reuse():
    suggestions = suggest_renames(
        ["customer_id", "order_total", "notes"],
        ["customerid", "ordertotal"],
    )
    pairs = [(s.old, s.new) for s in suggestions]
    assert pairs == [("customer_id", "customerid"), ("order_total", "ordertotal")]
    # 'notes' has no partner and no column is suggested twice
    old_names = [s.old for s in suggestions]
    new_names = [s.new for s in suggestions]
    assert len(set(old_names)) == len(old_names)
    assert len(set(new_names)) == len(new_names)


def test_suggest_renames_best_score_wins_no_reuse():
    # 'name' alone scores best against 'full_name'; the loser gets nothing
    suggestions = suggest_renames(["name", "nickname"], ["full_name"])
    assert len(suggestions) == 1
    assert (suggestions[0].old, suggestions[0].new) == ("name", "full_name")


def test_suggest_renames_matches_case_insensitively():
    suggestions = suggest_renames(["ProductID"], ["product_id"])
    assert len(suggestions) == 1
    assert (suggestions[0].old, suggestions[0].new) == ("ProductID", "product_id")


def test_suggest_renames_threshold_parameter():
    removed, added = ["email"], ["email_address"]  # scores ~0.556
    assert suggest_renames(removed, added) == []  # below the 0.6 default
    assert len(suggest_renames(removed, added, threshold=0.5)) == 1
    assert suggest_renames(["product_name"], ["productName"], threshold=0.99) == []


def test_suggest_renames_on_by_default_in_cli():
    import io
    from contextlib import redirect_stdout

    o = _write_csv("id,product_name\n1,x\n")
    n = _write_csv("id,productName\n1,x\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert "column renamed" in out
    assert "'product_name' → 'productName'" in out
    assert "similarity 0.96" in out


def test_no_suggest_renames_flag_hides_suggestions():
    import io
    from contextlib import redirect_stdout

    o = _write_csv("id,product_name\n1,x\n")
    n = _write_csv("id,productName\n1,x\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--no-suggest-renames", "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert "column renamed" not in out
    # the plain schema churn is still reported
    assert "+ column productName" in out
    assert "- column product_name" in out


def _tables_ic(old: str, new: str, key: str = "id", ignore_case: bool = True,
              check_keys: bool = True):
    """Like _tables but passes ignore_case through to load_csv."""
    o = _write_csv(old)
    n = _write_csv(new)
    try:
        old_t, old_key = load_csv(o, key, False, ignore_case=ignore_case)
        new_t, new_key = load_csv(n, key, False, ignore_case=ignore_case)
    finally:
        os.unlink(o)
        os.unlink(n)
    if check_keys:
        if ignore_case:
            assert old_key.lower() == new_key.lower()
        else:
            assert old_key == new_key
    return old_t, new_t, old_key


def test_ignore_case_headers_no_schema_diff():
    old, new, key = _tables_ic(
        "ID,Name,Price\n1,apple,1.00\n",
        "id,name,price\n1,apple,1.00\n",
    )
    diff = diff_tables(old, new, key, ignore_case=True)
    assert diff.is_empty
    assert not diff.added_columns and not diff.removed_columns


def test_ignore_case_off_still_sees_case_schema_diff():
    old, new, key = _tables_ic(
        "ID,Name,Price\n1,apple,1.00\n",
        "id,name,price\n1,apple,1.00\n",
        key="0",
        ignore_case=False,
        check_keys=False,
    )
    diff = diff_tables(old, new, key)
    assert not diff.is_empty
    assert set(diff.removed_columns) == {"ID", "Name", "Price"}
    assert set(diff.added_columns) == {"id", "name", "price"}


def test_ignore_case_key_lookup_by_name():
    o = _write_csv("id,name\n1,x\n")
    try:
        table, key_name = load_csv(o, "ID", False, ignore_case=True)
        assert key_name == "id"
        assert table.key_index == 0
    finally:
        os.unlink(o)
    # still strict without the flag
    o = _write_csv("id,name\n1,x\n")
    try:
        try:
            load_csv(o, "ID", False)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for unknown key column")
    finally:
        os.unlink(o)


def test_ignore_case_key_values_match_rows():
    old, new, key = _tables_ic(
        "id,name\nA100,apple\n",
        "id,name\na100,apple\n",
    )
    diff = diff_tables(old, new, key, ignore_case=True)
    assert diff.is_empty
    assert diff.unchanged_row_count == 1
    assert not diff.added_rows and not diff.removed_rows


def test_ignore_case_reports_original_casing():
    old, new, key = _tables_ic(
        "ID,name\nA100,apple\n",
        "id,NAME\nA100,apricot\n",
    )
    diff = diff_tables(old, new, key, ignore_case=True)
    assert len(diff.changed_rows) == 1
    row = diff.changed_rows[0]
    # display uses the old file's key casing and the new file's header casing
    assert row.key == "A100"
    assert row.changes[0].column == "NAME"
    assert row.changes[0].old == "apple"
    assert row.changes[0].new == "apricot"
    assert diff.key_column == "ID"


def test_ignore_case_cell_values_still_case_sensitive():
    old, new, key = _tables_ic(
        "id,name\n1,Keyboard\n",
        "id,name\n1,keyboard\n",
    )
    diff = diff_tables(old, new, key, ignore_case=True)
    assert len(diff.changed_rows) == 1
    assert diff.changed_rows[0].changes[0].old == "Keyboard"
    assert diff.changed_rows[0].changes[0].new == "keyboard"


def test_ignore_case_moved_column_detected():
    old, new, key = _tables_ic(
        "id,a,b\n1,2,3\n",
        "ID,b,a\n1,3,2\n",
    )
    diff = diff_tables(old, new, key, ignore_case=True)
    moved = {name: (oi, ni) for name, oi, ni in diff.moved_columns}
    # moved columns display the new file's header names
    assert moved["b"] == (2, 1)
    assert moved["a"] == (1, 2)
    assert not diff.changed_rows


def test_ignore_case_duplicate_keys_folded():
    o = _write_csv("id,name\nA1,x\nA2,y\na1,z\n")
    try:
        table, _ = load_csv(o, "id", False, ignore_case=True)
    finally:
        os.unlink(o)
    assert len(table.rows) == 2
    assert any("duplicate key 'a1'" in w for w in table.warnings)


def test_ignore_case_duplicate_folded_headers_warn():
    o = _write_csv("ID,id,name\n1,2,x\n")
    try:
        table, _ = load_csv(o, "0", False, ignore_case=True)
    finally:
        os.unlink(o)
    assert any("differ only by case" in w for w in table.warnings)


def test_ignore_case_rename_suggestions_still_fire():
    old, new, key = _tables_ic(
        "id,customer_id\n1,x\n",
        "id,CUSTOMERID\n1,x\n",
    )
    diff = diff_tables(old, new, key, ignore_case=True)
    # 'customer_id' vs 'customerid' differ beyond case, so still churn...
    assert diff.removed_columns == ["customer_id"]
    assert diff.added_columns == ["CUSTOMERID"]
    # ...and the fuzzy rename hint still fires
    assert len(diff.rename_suggestions) == 1
    assert diff.rename_suggestions[0].old == "customer_id"
    assert diff.rename_suggestions[0].new == "CUSTOMERID"


def test_ignore_case_cli_identical_exit_zero():
    import io
    from contextlib import redirect_stdout

    o = _write_csv("ID,name\nA100,apple\n")
    n = _write_csv("id,NAME\na100,apple\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--key", "ID", "--ignore-case", "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 0
    assert "identical" in out


def test_ignore_case_cli_without_flag_sees_diff():
    import io
    from contextlib import redirect_stdout

    # without the flag, key values that differ only in case are
    # distinct rows -> false added/removed churn
    o = _write_csv("ID,name\nA100,apple\n")
    n = _write_csv("ID,name\na100,apple\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--key", "ID", "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert "- ID=A100" in out
    assert "+ ID=a100" in out
    # ...while the flag matches them and reports identical
    o = _write_csv("ID,name\nA100,apple\n")
    n = _write_csv("ID,name\na100,apple\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--key", "ID", "--ignore-case", "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 0
    assert "identical" in out


def test_ignore_case_cli_key_name_lookup():
    import io
    from contextlib import redirect_stderr, redirect_stdout

    o = _write_csv("SKU,name\n1,x\n")
    n = _write_csv("sku,name\n1,y\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf), redirect_stderr(io.StringIO()):
            rc = main([o, n, "--key", "SKU", "--ignore-case", "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert "key column: SKU" in out
    # without the flag the new file's key lookup fails -> usage error
    o = _write_csv("SKU,name\n1,x\n")
    n = _write_csv("sku,name\n1,y\n")
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            rc = main([o, n, "--key", "SKU", "--no-color"])
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 2


def test_ignore_case_cli_ignore_cols_token():
    import io
    from contextlib import redirect_stdout

    o = _write_csv("id,Name,price\n1,x,1.00\n")
    n = _write_csv("id,name,price\n1,x,2.00\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--ignore-case", "--ignore-cols", "PRICE", "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 0
    assert "identical" in out


def test_ignore_case_cli_html_renders():
    import io
    from contextlib import redirect_stdout

    o = _write_csv("ID,name\nA100,apple\n")
    n = _write_csv("id,NAME\nA100,apricot\n")
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--ignore-case", "--format", "html"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert "<html" in out
    assert "A100" in out  # original key casing shown
    assert "apricot" in out
