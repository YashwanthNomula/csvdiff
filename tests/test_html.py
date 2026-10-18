"""Tests for csvdiff --format html."""

import io
import os
import sys
import tempfile
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from csvdiff.cli import main
from csvdiff.diff import diff_tables, load_csv
from csvdiff.html_report import render_html


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


def _report(old: str, new: str, key: str = "id"):
    old_t, new_t, key_name = _tables(old, new, key)
    diff = diff_tables(old_t, new_t, key_name)
    report = render_html(
        diff,
        "a.csv",
        "b.csv",
        old_headers=old_t.headers,
        new_headers=new_t.headers,
        old_key_index=old_t.key_index,
        new_key_index=new_t.key_index,
        width=40,
    )
    return report, diff


OLD = "id,name,price\n1,apple,1.00\n2,banana,0.50\n3,cherry,2.00\n"
NEW = "id,name,price\n1,apple,1.20\n2,banana,0.50\n4,date,3.00\n"


def test_html_document_structure():
    report, _ = _report(OLD, NEW)
    assert report.startswith("<!DOCTYPE html>")
    assert "<title>csvdiff report" in report
    assert "<style>" in report  # inline CSS, no external assets
    assert "<table" in report
    assert report.rstrip().endswith("</html>")


def test_html_summary_counts():
    report, _ = _report(OLD, NEW)
    for token in ("1 added", "1 removed", "1 changed", "1 unchanged"):
        assert token in report
    # summary badge classes
    assert 'class="badge badge-added"' in report
    assert 'class="badge badge-removed"' in report


def test_html_sections_render():
    report, _ = _report(OLD, NEW)
    assert "<h2>Added rows (1)</h2>" in report
    assert "<h2>Removed rows (1)</h2>" in report
    assert "<h2>Changed rows (1)</h2>" in report
    assert 'class="added"' in report
    assert 'class="removed"' in report
    # changed cells render old → new side by side
    assert "1.00" in report and "1.20" in report
    assert '<td class="old">1.00</td>' in report
    assert '<td class="new">1.20</td>' in report
    # added/removed row keys render
    assert '<td class="key">4</td>' in report
    assert '<td class="key">3</td>' in report


def test_html_has_column_headers():
    report, _ = _report(OLD, NEW)
    for header in ("<th>id</th>", "<th>name</th>", "<th>price</th>"):
        assert header in report
    # changed-rows table headers
    assert "<th>column</th>" in report
    assert "<th>old</th>" in report
    assert "<th>new</th>" in report


def test_html_identical_files():
    report, _ = _report(OLD, OLD)
    assert "no differences found" in report
    assert "<h2>Added rows" not in report
    assert "<h2>Removed rows" not in report
    assert "<h2>Changed rows" not in report
    assert "<h2>Summary</h2>" not in report


def test_html_escapes_cell_values():
    report, _ = _report(
        "id,name\n1,<b>bold</b>\n",
        "id,name\n1,a&b\n",
    )
    assert "&lt;b&gt;bold&lt;/b&gt;" in report
    assert "a&amp;b" in report
    assert "<b>bold</b>" not in report


def test_html_schema_changes():
    report, _ = _report(
        "id,name,old_col\n1,x,9\n",
        "id,name,new_col\n1,x,9\n",
    )
    assert "<h2>Schema changes</h2>" in report
    assert "+ column <code>new_col</code>" in report
    assert "- column <code>old_col</code>" in report


def test_html_shows_warnings():
    o = _write_csv("id,name\n1,x\n1,y\n")
    n = _write_csv("id,name\n1,x\n")
    try:
        old_t, _ = load_csv(o, "id", False)
        new_t, key_name = load_csv(n, "id", False)
    finally:
        os.unlink(o)
        os.unlink(n)
    diff = diff_tables(old_t, new_t, key_name)
    report = render_html(
        diff,
        "a.csv",
        "b.csv",
        old_headers=old_t.headers,
        new_headers=new_t.headers,
        old_key_index=old_t.key_index,
        new_key_index=new_t.key_index,
    )
    assert "<h2>Warnings</h2>" in report
    assert "duplicate key" in report


def test_cli_format_html_stdout():
    o = _write_csv(OLD)
    n = _write_csv(NEW)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--format", "html"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert out.startswith("<!DOCTYPE html>")
    assert "1 added" in out


def test_cli_format_html_writes_file():
    o = _write_csv(OLD)
    n = _write_csv(NEW)
    out_fh = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    out_fh.close()
    try:
        rc = main([o, n, "--format", "html", "-o", out_fh.name])
        with open(out_fh.name, encoding="utf-8") as fh:
            content = fh.read()
    finally:
        os.unlink(o)
        os.unlink(n)
        os.unlink(out_fh.name)
    assert rc == 1
    assert content.startswith("<!DOCTYPE html>")
    assert content.rstrip().endswith("</html>")
    assert "<table" in content
    # single self-contained file: inline style, no link/script src tags
    assert "<style>" in content
    assert 'src="' not in content and "<link" not in content


def test_cli_format_html_identical_exit_zero():
    o = _write_csv(OLD)
    n = _write_csv(OLD)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--format", "html"])
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 0


def test_cli_output_unwritable_errors():
    o = _write_csv(OLD)
    n = _write_csv(NEW)
    try:
        rc = main([o, n, "--format", "html", "-o", "/nonexistent/dir/r.html"])
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 2


def test_text_format_is_default():
    o = _write_csv(OLD)
    n = _write_csv(NEW)
    try:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = main([o, n, "--no-color"])
        out = buf.getvalue()
    finally:
        os.unlink(o)
        os.unlink(n)
    assert rc == 1
    assert "<!DOCTYPE html>" not in out
    assert "csvdiff" in out and "→" in out
    assert "1 added" in out and "1 removed" in out and "1 changed" in out


def test_html_includes_rename_suggestion():
    report, diff = _report(
        "id,product_name\n1,x\n",
        "id,productName\n1,x\n",
    )
    assert len(diff.rename_suggestions) == 1
    assert "column renamed" in report
    assert "<code>product_name</code>" in report
    assert "<code>productName</code>" in report
    assert "similarity 0.96" in report


def test_html_escapes_rename_names():
    report, diff = _report(
        "id,a<b_name\n1,x\n",
        "id,a<bname\n1,x\n",
    )
    assert len(diff.rename_suggestions) == 1
    assert "&lt;" in report
    # raw angle brackets from column names must not leak into the report
    assert "<b_name" not in report and "<bname" not in report
