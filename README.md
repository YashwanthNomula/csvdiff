# csvdiff

A beautiful, **column-aware diff for CSV files** — in plain Python, zero dependencies.

Plain `diff` on CSVs shows raw line noise. `csvdiff` understands your data:
it aligns rows by a **key column**, compares **cell-by-cell**, and calls out
**added/removed/moved columns** separately from row changes.

```
$ csvdiff old.csv new.csv

csvdiff examples/old.csv → examples/new.csv
key column: sku

schema
+ column rating
- column category

changed rows
~ sku=A100
    price: 129.99 → 149.99
~ sku=A101
    stock: 120 → 98
~ sku=B200
    name: Mechanical Keyboard → Mechanical Keyboard Pro
~ sku=C300
    stock: 15 → 0

added rows
+ sku=B202 name=Noise-Cancel Headphones price=199.00 stock=30 rating=4.7

removed rows
- sku=B201 name=USB-C Hub price=39.99 stock=60 category=electronics

rows: 1 added, 1 removed, 4 changed (4 cells), 1 unchanged | columns: +1 cols, -1 cols
```

*(transcript captured from a real run of `csvdiff examples/old.csv examples/new.csv`)*

## Install & run

```bash
# zero dependencies — just add src/ to your path, or:
pip install .

# basic usage
csvdiff old.csv new.csv
```

## Options

| Flag | What it does |
|---|---|
| `--key NAME` | key column as a header name or 0-based index (default: first column) |
| `--no-header` | first row is data, not headers (`col_0`, `col_1`, …) |
| `--width N` | truncate long cell values to N chars (default 40) |
| `--ignore-cols COLS` | comma-separated columns (names or 0-based indexes) to exclude from the comparison — handy for noisy columns like `updated_at` |
| `--tol TOL` | numeric tolerance: two cells that both parse as numbers count as equal when their absolute difference is ≤ TOL (default: 0) — handy for float-heavy data with rounding noise |
| `--ignore-case` | match headers and key values case-insensitively, so `ID` vs `id` no longer shows up as a schema diff; reports still show each file's original casing |
| `--suggest-renames` / `--no-suggest-renames` | fuzzy-match removed/added column names (difflib ratio ≥ 0.6, case-insensitive) and suggest renames like `~ column renamed: 'category' → 'rating' (similarity 0.75)` — on by default; shows in text and HTML reports |
| `--color` / `--no-color` | force colors on/off (auto-detects TTY) |
| `--format text\|html` | output format: terminal text report (default) or a standalone HTML report |
| `-o`, `--output FILE` | write the report to FILE instead of stdout |

Exit code is `0` when the files are identical, `1` when differences are found
(like `grep`), `2` on usage errors — so it slots straight into scripts and CI:

```bash
csvdiff baseline.csv current.csv --no-color | tee diff-report.txt
```

Other niceties:

- **Moved-column detection** — reordered columns are reported as moves, not churn
- **Rename suggestions** — `--suggest-renames` (on by default) fuzzy-matches
  removed/added columns and flags likely renames (case-insensitive,
  similarity ≥ 0.6), shown in both text and HTML reports:

```bash
csvdiff baseline.csv current.csv --suggest-renames --no-color
# schema
# + column customerid
# - column customer_id
# ~ column renamed: 'customer_id' → 'customerid' (similarity 0.95)
```
- **Duplicate-key warnings** — tells you when a key appears twice instead of silently guessing
- **Delimiter sniffing** — handles `,`, `;`, `\t`, and `|` files automatically
- **Noisy-column exclusion** — `--ignore-cols updated_at` drops ever-changing columns from the comparison entirely:

```bash
csvdiff baseline.csv current.csv --ignore-cols updated_at,exported_by --no-color
```

- **Numeric tolerance** — `--tol 0.01` treats two numeric cells as equal when
  their absolute difference is at most TOL, so rounding noise in float-heavy
  exports (prices, metrics, sensor readings) doesn't drown the real changes.
  Applies to text and HTML output alike; non-numeric cells compare normally:

```bash
csvdiff baseline.csv current.csv --tol 0.001 --no-color
```

- **Case-insensitive matching** — `--ignore-case` folds headers and key
  values before comparing, so a column named `ID` in one export and `id` in
  the next no longer shows up as a removed/added column pair, and rows keyed
  `A100` still match rows keyed `a100`. Reports keep each file's original
  casing; ordinary cell values stay case-sensitive:

```bash
csvdiff baseline.csv current.csv --ignore-case --no-color
```

- **HTML reports** — `--format html` exports a single self-contained HTML file
  (inline CSS, no external assets) with a summary header, schema changes,
  old → new cell tables, and green/red tables for added/removed rows — handy
  for attaching to tickets or CI artifacts:

```bash
csvdiff baseline.csv current.csv --format html -o report.html
```

## Examples

Two sample inventory files live in `examples/` — run the transcript above with:

```bash
python -m csvdiff examples/old.csv examples/new.csv   # PYTHONPATH=src
# or, after pip install:
csvdiff examples/old.csv examples/new.csv
```

## Tests

```bash
python -m pytest tests/   # 67 tests: engine, renderer, CLI edge cases, --ignore-cols, --format html, --tol, --suggest-renames, --ignore-case
```

## License

MIT — see [LICENSE](LICENSE).
