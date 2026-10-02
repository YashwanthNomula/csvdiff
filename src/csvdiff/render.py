"""Terminal rendering for csvdiff — colors, truncation, layout."""

from __future__ import annotations

from .diff import TableDiff

# ANSI styles
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_STRIKE = "\033[9m"
_RESET = "\033[0m"


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: max(width - 1, 0)] + "…"


def _row_snippet(
    headers: list[str], row: list[str], width: int, key_index: int
) -> str:
    parts = []
    for i, name in enumerate(headers):
        if i == key_index:
            continue
        value = row[i] if i < len(row) else ""
        parts.append(f"{name}={_truncate(value, width)}")
    return " ".join(parts)


class Renderer:
    def __init__(
        self,
        color: bool,
        width: int,
        old_headers: list[str],
        new_headers: list[str],
        old_key_index: int,
        new_key_index: int,
    ) -> None:
        self.color = color
        self.width = width
        self.old_headers = old_headers
        self.new_headers = new_headers
        self.old_key_index = old_key_index
        self.new_key_index = new_key_index

    def _s(self, code: str) -> str:
        return code if self.color else ""

    def render(self, diff: TableDiff, old_name: str, new_name: str) -> str:
        lines: list[str] = []
        r, d, g, y, c, b, strike, dim = (
            self._s(_RED),
            self._s(_DIM),
            self._s(_GREEN),
            self._s(_YELLOW),
            self._s(_CYAN),
            self._s(_BOLD),
            self._s(_STRIKE),
            self._s(_DIM),
        )
        reset = self._s(_RESET)

        lines.append(
            f"{b}csvdiff{reset} {dim}{old_name}{reset} {b}→{reset} {dim}{new_name}{reset}"
        )
        lines.append(f"key column: {b}{diff.key_column}{reset}")
        lines.append("")

        if diff.warnings:
            for w in diff.warnings:
                lines.append(f"{y}warning:{reset} {w}")
            lines.append("")

        if diff.is_empty:
            lines.append(f"{g}✓ identical{reset} — no differences found.")
            return "\n".join(lines)

        # --- schema changes ---
        schema: list[str] = []
        for col in diff.added_columns:
            schema.append(f"{g}+ column{reset} {col}")
        for col in diff.removed_columns:
            schema.append(f"{r}- column{reset} {col}")
        for name, oi, ni in diff.moved_columns:
            schema.append(f"{y}~ column{reset} {name} moved {oi} → {ni}")
        if schema:
            lines.append(f"{b}schema{reset}")
            lines.extend(schema)
            lines.append("")

        # --- changed rows ---
        if diff.changed_rows:
            lines.append(f"{b}changed rows{reset}")
            for row in diff.changed_rows:
                lines.append(f"{y}~{reset} {b}{diff.key_column}={row.key}{reset}")
                for ch in row.changes:
                    old = _truncate(ch.old, self.width)
                    new = _truncate(ch.new, self.width)
                    lines.append(
                        f"    {c}{ch.column}{reset}: "
                        f"{r}{strike}{old}{reset} {b}→{reset} {g}{new}{reset}"
                    )
            lines.append("")

        # --- added rows ---
        if diff.added_rows:
            lines.append(f"{b}added rows{reset}")
            for key, row in diff.added_rows:
                snippet = _row_snippet(
                    self.new_headers, row, self.width, self.new_key_index
                )
                lines.append(
                    f"{g}+{reset} {b}{diff.key_column}={key}{reset}"
                    + (f" {dim}{snippet}{reset}" if snippet else "")
                )
            lines.append("")

        # --- removed rows ---
        if diff.removed_rows:
            lines.append(f"{b}removed rows{reset}")
            for key, row in diff.removed_rows:
                snippet = _row_snippet(
                    self.old_headers, row, self.width, self.old_key_index
                )
                lines.append(
                    f"{r}-{reset} {b}{diff.key_column}={key}{reset}"
                    + (f" {dim}{snippet}{reset}" if snippet else "")
                )
            lines.append("")

        # --- summary ---
        rows_changed = len(diff.changed_rows)
        stats = [
            f"{g}{len(diff.added_rows)} added{reset}",
            f"{r}{len(diff.removed_rows)} removed{reset}",
            f"{y}{rows_changed} changed{reset} ({diff.cells_changed} cells)",
            f"{dim}{diff.unchanged_row_count} unchanged{reset}",
        ]
        cols = []
        if diff.added_columns:
            cols.append(f"{g}+{len(diff.added_columns)} cols{reset}")
        if diff.removed_columns:
            cols.append(f"{r}-{len(diff.removed_columns)} cols{reset}")
        if diff.moved_columns:
            cols.append(f"{y}~{len(diff.moved_columns)} cols moved{reset}")
        summary = "rows: " + ", ".join(stats)
        if cols:
            summary += " | columns: " + ", ".join(cols)
        lines.append(summary)

        return "\n".join(lines)
