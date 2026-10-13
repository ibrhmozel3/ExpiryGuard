# ExpiryGuard: expiry tracking for pharmacies

Pharmacies often stock the same medicine across multiple **lots**, each with its own
expiry date (*"miad"* in Turkish). Expired stock means financial loss and legal risks, and suppliers
only accept returns within a limited window. To manage this, items must be sold using the
**FEFO** (First Expiry, First Out) method: the lot that expires first is sold first.

ExpiryGuard is a command-line tool that keeps the pharmacy's stock in plain CSV
files and answers, every morning, three questions:

1. What has **expired** and must leave the shelf?
2. What should be **returned to the supplier** while it is still possible?
3. What should be **sold first**?

It also sells boxes in FEFO order automatically, imports supplier deliveries
(including CSV files saved by Turkish Excel) and writes a monthly loss report.

Only the Python standard library is used. Python 3.9 or newer.
On macOS and Linux type `python3` instead of `python` in the commands below.

## Quick start

```
git clone https://github.com/ibrhmozel3/ExpiryGuard.git
cd ExpiryGuard
python cli.py demo        # creates a fictional pharmacy in data/
python cli.py check       # daily expiry check
```

## Commands

| Command | What it does | Changes data? |
|---|---|---|
| `demo [--force]` | Creates a demo pharmacy (dates are relative to today) | yes |
| `check [--all]` | Lists lots by risk: expired / return now / sell first | no |
| `add --barcode --name --lot --expiry --qty --price [--supplier]` | Adds a delivered lot, or adds boxes to an existing lot | yes |
| `sell PRODUCT [--qty N]` | Sells boxes, always from the lot that expires first; never sells expired boxes | yes |
| `fefo PRODUCT` | Shows the order in which lots of one medicine should be sold | no |
| `remove-expired [--apply]` | Removes expired lots and records the loss | only with `--apply` |
| `returns [--supplier S] [--apply]` | Lists lots to send back; with `--apply` saves the list to `reports/` | only with `--apply` |
| `import FILE [--apply]` | Imports lots from another CSV, skipping bad rows with a reason | only with `--apply` |
| `report [--month YYYY-MM]` | Monthly report: sold, returned, expired, loss rate, suggestions | no |
| `restore [--apply]` | Puts back `stock.csv.bak` (the stock before the last change). Run again to undo | only with `--apply` |

`PRODUCT` can be a barcode or words of the name (`parasetamol`, `para 1000`, `İbuprofen`, `b12`).
Turkish letters are optional (`selcuk` finds `Selçuk`). If the words match more than one
medicine, the tool asks for the barcode instead of guessing.

Options available on every command:

- `--today YYYY-MM-DD` pretends today is another date (useful for testing)
- `--data-dir DIR` uses another folder for the stock (default `data/`)
- `--config FILE` uses another settings file (default `config.json`)
- `--no-color` prints without colors

Example session:

```
python cli.py demo
python cli.py check
python cli.py sell parasetamol --qty 16
python cli.py fefo parasetamol
python cli.py returns --supplier "Selcuk Ecza"
python cli.py import samples/delivery_tr_excel.csv --apply
python cli.py report
```

## How data is stored

| File | Content |
|---|---|
| `data/stock.csv` | Current stock, one row per lot. Opens in Excel. |
| `data/stock.csv.bak` | The previous version, written before every save. |
| `data/history.csv` | Every ADD / SELL / EXPIRED / RETURN with date and value. Lines are only appended. |
| `config.json` | `return_window_days` and `sell_first_days`, the limits used for the risk levels. |
| `reports/` | Return lists created by `returns --apply`. |

`data/` and `reports/` are created by the tool and are not part of the repository.

Stock file format:

```
barcode,name,lot,expiry,qty,unit_price,supplier
8690000000012,Parasetamol 500mg 20 tb,A2231,2026-11-30,14,45.50,Selcuk Ecza
```

Accepted on input: `,` or `;` as separator, dates as `2026-11-30`, `30.11.2026`
or `2026-11` (last day of that month), prices as `45.50` or `45,50`.

## Safety and input validation

- Every row is validated: 13-digit barcode with a correct EAN-13 check digit,
  real calendar dates, positive whole quantities, finite non-negative prices,
  text without control characters and with a length limit.
  Bad rows are skipped and reported with their line number.
- Files over 5 MB, binary files and CSVs with missing columns are refused.
- Stock is saved to a temporary file first and swapped in with `os.replace`,
  so a crash never leaves a half-written `stock.csv`. The previous version is kept as `.bak`.
- If writing `history.csv` fails after the stock was saved, the old stock is put back, so the two
  files never disagree.
- `restore` checks the backup first; a broken or missing backup is refused and nothing is changed.
- The same lot added twice increases its quantity; the same lot with another expiry or price,
  or the same medicine name under two barcodes, is refused.
- If `stock.csv` contains broken rows (for example after editing it by hand), commands
  that save refuse to run, because saving would silently delete those rows.
- Text that starts with `=`, `+`, `-` or `@` is prefixed with `'` when saved,
  so a malicious name cannot run as a formula when the CSV is opened in Excel.
- Commands that remove or import data only preview unless `--apply` is given.
- Errors are printed as one clear line with exit code 1. Wrong arguments give exit code 2.

## Project structure

```
cli.py                    command-line interface: argument parsing and the commands
config.json               risk limits in days
expiryguard/
    models.py             what a lot looks like (a dict) and the error types
    storage.py            CSV/JSON reading and writing, atomic save, history log
    validation.py         checks for every field, row parsing, merging lots
    rules.py              risk levels, product search, FEFO sale planning
    reports.py            terminal output, money format, monthly report
    demo.py               builds the fictional demo pharmacy
samples/
    delivery_tr_excel.csv a delivery saved by Turkish Excel (; and 45,50)
    bad_rows.csv          a file full of broken rows to test validation
tests/                    unit tests, one file per module
contributions/            what each team member did
```

## Running the tests

```
python -m unittest -v
```

## Team

Group **AS**

| Member | Student ID | GitHub | Part of the project |
|---|---|---|---|
| Suhaib Altinavi | 2509115395 | [suhaib975](https://github.com/suhaib975) | Storage and data model (`models.py`, `storage.py`) |
| Aissam Ourahmoune | 2509115126 | [aissam1234567](https://github.com/aissam1234567) | Input validation and import (`validation.py`, `samples/`) |
| Ahmet Hakan Özel | 2509011074 | [hakanozel447-svg](https://github.com/hakanozel447-svg) | Business rules and FEFO (`rules.py`) |
| İbrahim Özel | 2509011075 | [ibrhmozel3](https://github.com/ibrhmozel3) | Command-line interface and reports (`cli.py`, `reports.py`, `demo.py`) |

Each member's detailed contribution is in the `contributions/` folder.
