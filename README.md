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
| `--color` / `--no-color` | force colors on/off (auto-detects TTY) |

Exit code is `0` when the files are identical, `1` when differences are found
(like `grep`), `2` on usage errors — so it slots straight into scripts and CI:

```bash
csvdiff baseline.csv current.csv --no-color | tee diff-report.txt
```

Other niceties:

- **Moved-column detection** — reordered columns are reported as moves, not churn
- **Duplicate-key warnings** — tells you when a key appears twice instead of silently guessing
- **Delimiter sniffing** — handles `,`, `;`, `\t`, and `|` files automatically

## Examples

Two sample inventory files live in `examples/` — run the transcript above with:

```bash
python -m csvdiff examples/old.csv examples/new.csv   # PYTHONPATH=src
# or, after pip install:
csvdiff examples/old.csv examples/new.csv
```

## Tests

```bash
python -m pytest tests/   # 11 tests: engine, renderer, CLI edge cases
```

## License

MIT — see [LICENSE](LICENSE).
