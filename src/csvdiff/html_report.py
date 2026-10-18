"""Standalone HTML diff reports for csvdiff — inline CSS, no external assets."""

from __future__ import annotations

from html import escape

from .diff import TableDiff


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: max(width - 1, 0)] + "…"


_CSS = """\
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    Helvetica, Arial, sans-serif;
  margin: 2rem auto;
  max-width: 1024px;
  padding: 0 1.25rem;
  color: #1f2937;
  background: #ffffff;
  line-height: 1.45;
}
header h1 { font-size: 1.7rem; margin: 0 0 0.25rem; }
header .files, header .meta { color: #4b5563; margin: 0.15rem 0; }
code {
  background: #f3f4f6;
  padding: 0.1rem 0.45rem;
  border-radius: 0.3rem;
  font-size: 0.9em;
}
h2 { font-size: 1.15rem; margin: 1.75rem 0 0.5rem; }
ul.stats { list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: 0.5rem; }
.badge {
  display: inline-block;
  padding: 0.2rem 0.75rem;
  border-radius: 999px;
  font-weight: 600;
  font-size: 0.9rem;
}
.badge-added { background: #dcfce7; color: #166534; }
.badge-removed { background: #fee2e2; color: #991b1b; }
.badge-changed { background: #fef3c7; color: #92400e; }
.badge-unchanged { background: #f3f4f6; color: #4b5563; }
table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; }
th, td {
  border: 1px solid #e5e7eb;
  padding: 0.4rem 0.65rem;
  text-align: left;
  vertical-align: top;
  font-size: 0.9rem;
  overflow-wrap: anywhere;
}
th { background: #f9fafb; font-weight: 600; }
td.key { font-weight: 600; white-space: nowrap; }
tr.added td { background: #f0fdf4; }
tr.removed td { background: #fef2f2; }
td.old { background: #fee2e2; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
td.new { background: #dcfce7; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
ul.schema { list-style: none; padding: 0; }
ul.schema li { margin: 0.25rem 0; }
.schema-added { color: #166534; }
.schema-removed { color: #991b1b; }
.schema-moved { color: #92400e; }
.schema-renamed { color: #92400e; }
.warnings {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 0.5rem;
  padding: 0.5rem 1rem;
}
p.identical { color: #166534; font-size: 1.05rem; }
footer { margin: 2.5rem 0 1rem; color: #9ca3af; font-size: 0.8rem; }
.arrow { color: #6b7280; }
"""


def _render_summary(diff: TableDiff) -> str:
    stats = [
        ("added", f"{len(diff.added_rows)} added"),
        ("removed", f"{len(diff.removed_rows)} removed"),
        ("changed", f"{len(diff.changed_rows)} changed ({diff.cells_changed} cells)"),
        ("unchanged", f"{diff.unchanged_row_count} unchanged"),
    ]
    if diff.added_columns:
        stats.append(("added", f"+{len(diff.added_columns)} columns"))
    if diff.removed_columns:
        stats.append(("removed", f"-{len(diff.removed_columns)} columns"))
    if diff.moved_columns:
        stats.append(("changed", f"~{len(diff.moved_columns)} columns moved"))
    items = "".join(
        f'<li><span class="badge badge-{cls}">{escape(text)}</span></li>'
        for cls, text in stats
    )
    return f"<h2>Summary</h2>\n<ul class=\"stats\">\n{items}\n</ul>"


def _render_schema(diff: TableDiff) -> str:
    items: list[str] = []
    for col in diff.added_columns:
        items.append(
            f'<li class="schema-added">+ column <code>{escape(col)}</code></li>'
        )
    for col in diff.removed_columns:
        items.append(
            f'<li class="schema-removed">- column <code>{escape(col)}</code></li>'
        )
    for name, old_idx, new_idx in diff.moved_columns:
        items.append(
            f'<li class="schema-moved">~ column <code>{escape(name)}</code> '
            f'moved {old_idx} <span class="arrow">→</span> {new_idx}</li>'
        )
    for suggestion in diff.rename_suggestions:
        items.append(
            f'<li class="schema-renamed">~ column renamed '
            f'<code>{escape(suggestion.old)}</code> <span class="arrow">→</span> '
            f'<code>{escape(suggestion.new)}</code> '
            f'(similarity {suggestion.similarity:.2f})</li>'
        )
    if not items:
        return ""
    return (
        "<h2>Schema changes</h2>\n<ul class=\"schema\">\n"
        + "\n".join(items)
        + "\n</ul>"
    )


def _render_changed(diff: TableDiff, width: int) -> str:
    if not diff.changed_rows:
        return ""
    rows: list[str] = []
    for row in diff.changed_rows:
        for ch in row.changes:
            rows.append(
                "<tr>"
                f'<td class="key">{escape(row.key)}</td>'
                f"<td>{escape(ch.column)}</td>"
                f'<td class="old">{escape(_truncate(ch.old, width))}</td>'
                f'<td class="new">{escape(_truncate(ch.new, width))}</td>'
                "</tr>"
            )
    return (
        f"<h2>Changed rows ({len(diff.changed_rows)})</h2>\n"
        "<table>\n<thead><tr>"
        f"<th>{escape(diff.key_column)}</th>"
        "<th>column</th><th>old</th><th>new</th>"
        "</tr></thead>\n<tbody>\n" + "\n".join(rows) + "\n</tbody>\n</table>"
    )


def _render_row_table(
    title: str,
    headers: list[str],
    key_index: int,
    rows: list[tuple[str, list[str]]],
    css_class: str,
    width: int,
) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body: list[str] = []
    for _key, row in rows:
        cells = []
        for i in range(len(headers)):
            value = row[i] if i < len(row) else ""
            cls = ' class="key"' if i == key_index else ""
            cells.append(f"<td{cls}>{escape(_truncate(value, width))}</td>")
        body.append(f'<tr class="{css_class}">' + "".join(cells) + "</tr>")
    return (
        f"<h2>{title} ({len(rows)})</h2>\n"
        "<table>\n<thead><tr>" + head + "</tr></thead>\n<tbody>\n"
        + "\n".join(body)
        + "\n</tbody>\n</table>"
    )


def _render_warnings(diff: TableDiff) -> str:
    if not diff.warnings:
        return ""
    items = "".join(f"<li>{escape(w)}</li>" for w in diff.warnings)
    return (
        '<div class="warnings">\n<h2>Warnings</h2>\n<ul>\n'
        + items
        + "\n</ul>\n</div>"
    )


def render_html(
    diff: TableDiff,
    old_name: str,
    new_name: str,
    *,
    old_headers: list[str],
    new_headers: list[str],
    old_key_index: int,
    new_key_index: int,
    width: int = 40,
) -> str:
    """Render ``diff`` as a standalone HTML document.

    All CSS is inlined and every dynamic value is HTML-escaped, so the
    result is a single self-contained file safe to open or attach.
    """
    title = f"csvdiff report: {old_name} → {new_name}"
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{escape(title)}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>csvdiff</h1>",
        f'<p class="files"><code>{escape(old_name)}</code> '
        f'<span class="arrow">→</span> <code>{escape(new_name)}</code></p>',
        f'<p class="meta">key column: <code>{escape(diff.key_column)}</code></p>',
        "</header>",
        _render_warnings(diff),
    ]
    if diff.is_empty:
        parts.append(
            '<p class="identical">✓ identical — no differences found.</p>'
        )
    else:
        parts.append(_render_summary(diff))
        schema = _render_schema(diff)
        if schema:
            parts.append(schema)
        changed = _render_changed(diff, width)
        if changed:
            parts.append(changed)
        if diff.added_rows:
            parts.append(
                _render_row_table(
                    "Added rows",
                    new_headers,
                    new_key_index,
                    diff.added_rows,
                    "added",
                    width,
                )
            )
        if diff.removed_rows:
            parts.append(
                _render_row_table(
                    "Removed rows",
                    old_headers,
                    old_key_index,
                    diff.removed_rows,
                    "removed",
                    width,
                )
            )
    parts += [
        "<footer>generated by csvdiff</footer>",
        "</body>",
        "</html>",
    ]
    return "\n".join(p for p in parts if p)
