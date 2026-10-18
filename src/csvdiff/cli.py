"""Command-line interface for csvdiff."""

from __future__ import annotations

import argparse
import sys

from .diff import diff_tables, drop_columns, load_csv
from .html_report import render_html
from .render import Renderer


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="csvdiff",
        description="Beautiful column-aware diffs for CSV files.",
    )
    p.add_argument("old", help="baseline CSV file")
    p.add_argument("new", help="updated CSV file")
    p.add_argument(
        "--key",
        default="0",
        help="key column: header name or 0-based index (default: first column)",
    )
    p.add_argument(
        "--no-header",
        action="store_true",
        help="treat the first row as data, not headers",
    )
    p.add_argument(
        "--width",
        type=int,
        default=40,
        help="truncate cell values to this many characters (default: 40)",
    )
    p.add_argument(
        "--ignore-cols",
        default="",
        metavar="COLS",
        help="comma-separated columns (header names or 0-based indexes) "
        "to exclude from the comparison, e.g. --ignore-cols updated_at,ts",
    )
    p.add_argument(
        "--tol",
        type=float,
        default=0.0,
        metavar="TOL",
        help="numeric tolerance for float-heavy data: two cells that both "
        "parse as numbers count as equal when their absolute difference "
        "is at most TOL (default: 0)",
    )
    p.add_argument(
        "--ignore-case",
        action="store_true",
        help="match headers and key values case-insensitively, so 'ID' vs "
        "'id' no longer shows up as a schema diff; reports still show each "
        "file's original casing",
    )
    color = p.add_mutually_exclusive_group()
    color.add_argument(
        "--color", dest="color", action="store_true", help="force colored output"
    )
    color.add_argument(
        "--no-color", dest="color", action="store_false", help="disable colors"
    )
    p.set_defaults(color=None)
    renames = p.add_mutually_exclusive_group()
    renames.add_argument(
        "--suggest-renames",
        dest="suggest_renames",
        action="store_true",
        help="fuzzy-match removed/added columns and suggest renames "
        "(default: on)",
    )
    renames.add_argument(
        "--no-suggest-renames",
        dest="suggest_renames",
        action="store_false",
        help="disable rename suggestions",
    )
    p.set_defaults(suggest_renames=True)
    p.add_argument(
        "--format",
        choices=["text", "html"],
        default="text",
        help="output format: 'text' terminal report (default) or "
        "'html' standalone report",
    )
    p.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=None,
        help="write the report to FILE instead of stdout",
    )
    p.add_argument(
        "--version", action="version", version="%(prog)s 1.4.0"
    )
    return p


def _resolve_ignore(
    table_headers: list[str], key_index: int, spec: str, ignore_case: bool = False
) -> set[int]:
    """Turn a ``--ignore-cols`` spec into column indices for one file.

    Each token is a header name or a 0-based index. Raises ValueError on
    unknown names, out-of-range indexes, or attempts to ignore the key column.
    With ``ignore_case`` on, name tokens match headers case-insensitively.
    """
    indices: set[int] = set()
    for raw in spec.split(","):
        token = raw.strip()
        if not token:
            continue
        if token.isdigit():
            index = int(token)
            if not 0 <= index < len(table_headers):
                raise ValueError(
                    f"--ignore-cols: column index {index} out of range"
                )
        else:
            try:
                index = table_headers.index(token)
            except ValueError:
                if ignore_case:
                    lowered = token.lower()
                    matches = [
                        i
                        for i, h in enumerate(table_headers)
                        if h.lower() == lowered
                    ]
                    if not matches:
                        raise ValueError(
                            f"--ignore-cols: unknown column {token!r}"
                        ) from None
                    index = matches[0]
                else:
                    raise ValueError(
                        f"--ignore-cols: unknown column {token!r}"
                    ) from None
        if index == key_index:
            raise ValueError("--ignore-cols: cannot ignore the key column")
        indices.add(index)
    return indices


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        old_table, key_name = load_csv(
            args.old, args.key, args.no_header, ignore_case=args.ignore_case
        )
    except FileNotFoundError:
        print(f"csvdiff: file not found: {args.old}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"csvdiff: {args.old}: {exc}", file=sys.stderr)
        return 2

    try:
        new_table, key_name_new = load_csv(
            args.new, args.key, args.no_header, ignore_case=args.ignore_case
        )
    except FileNotFoundError:
        print(f"csvdiff: file not found: {args.new}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"csvdiff: {args.new}: {exc}", file=sys.stderr)
        return 2

    if args.ignore_cols:
        try:
            old_ignored = _resolve_ignore(
                old_table.headers,
                old_table.key_index,
                args.ignore_cols,
                ignore_case=args.ignore_case,
            )
            new_ignored = _resolve_ignore(
                new_table.headers,
                new_table.key_index,
                args.ignore_cols,
                ignore_case=args.ignore_case,
            )
        except ValueError as exc:
            print(f"csvdiff: {exc}", file=sys.stderr)
            return 2
        old_table = drop_columns(old_table, old_ignored)
        new_table = drop_columns(new_table, new_ignored)

    names_match = key_name == key_name_new or (
        args.ignore_case and key_name.lower() == key_name_new.lower()
    )
    if not names_match:
        print(
            f"csvdiff: key column differs between files: "
            f"{key_name!r} vs {key_name_new!r}",
            file=sys.stderr,
        )
        return 2

    if args.tol < 0:
        print("csvdiff: --tol must be >= 0", file=sys.stderr)
        return 2

    diff = diff_tables(
        old_table,
        new_table,
        key_name,
        tol=args.tol,
        detect_renames=args.suggest_renames,
        ignore_case=args.ignore_case,
    )

    if args.format == "html":
        output = render_html(
            diff,
            args.old,
            args.new,
            old_headers=old_table.headers,
            new_headers=new_table.headers,
            old_key_index=old_table.key_index,
            new_key_index=new_table.key_index,
            width=args.width,
        )
    else:
        use_color = args.color if args.color is not None else sys.stdout.isatty()
        renderer = Renderer(
            color=use_color,
            width=args.width,
            old_headers=old_table.headers,
            new_headers=new_table.headers,
            old_key_index=old_table.key_index,
            new_key_index=new_table.key_index,
        )
        output = renderer.render(diff, args.old, args.new)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as fh:
                fh.write(output + "\n")
        except OSError as exc:
            print(
                f"csvdiff: cannot write {args.output}: {exc}", file=sys.stderr
            )
            return 2
    else:
        print(output)
    return 0 if diff.is_empty else 1


if __name__ == "__main__":
    sys.exit(main())
