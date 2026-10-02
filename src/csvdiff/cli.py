"""Command-line interface for csvdiff."""

from __future__ import annotations

import argparse
import sys

from .diff import diff_tables, load_csv
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
    color = p.add_mutually_exclusive_group()
    color.add_argument(
        "--color", dest="color", action="store_true", help="force colored output"
    )
    color.add_argument(
        "--no-color", dest="color", action="store_false", help="disable colors"
    )
    p.set_defaults(color=None)
    p.add_argument(
        "--version", action="version", version="%(prog)s 1.0.0"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        old_table, key_name = load_csv(args.old, args.key, args.no_header)
    except FileNotFoundError:
        print(f"csvdiff: file not found: {args.old}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"csvdiff: {args.old}: {exc}", file=sys.stderr)
        return 2

    try:
        new_table, key_name_new = load_csv(args.new, args.key, args.no_header)
    except FileNotFoundError:
        print(f"csvdiff: file not found: {args.new}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"csvdiff: {args.new}: {exc}", file=sys.stderr)
        return 2

    if key_name != key_name_new:
        print(
            f"csvdiff: key column differs between files: "
            f"{key_name!r} vs {key_name_new!r}",
            file=sys.stderr,
        )
        return 2

    use_color = args.color if args.color is not None else sys.stdout.isatty()

    diff = diff_tables(old_table, new_table, key_name)
    renderer = Renderer(
        color=use_color,
        width=args.width,
        old_headers=old_table.headers,
        new_headers=new_table.headers,
        old_key_index=old_table.key_index,
        new_key_index=new_table.key_index,
    )
    print(renderer.render(diff, args.old, args.new))
    return 0 if diff.is_empty else 1


if __name__ == "__main__":
    sys.exit(main())
