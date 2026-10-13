# İbrahim Özel: command-line interface and reports

**Name:** İbrahim Özel · **Student ID:** 2509011075 · **GitHub:** [ibrhmozel3](https://github.com/ibrhmozel3)

## What I built

- `cli.py`: the command-line interface with `argparse` subcommands
  (`demo`, `check`, `add`, `sell`, `fefo`, `remove-expired`, `returns`, `import`, `report`).
  - Commands are chosen with a dictionary (`COMMANDS`) instead of a long if/elif chain.
  - Arguments are converted and validated by argparse using our own type functions
    (`barcode_type`, `qty_type`, ...).
  - Preview by default; `--apply` is needed for anything that removes or imports data.
  - All expected errors become one readable line and exit code 1.
- `expiryguard/reports.py`: terminal output, colors, Turkish money format, the monthly report.
- `expiryguard/demo.py`: the demo pharmacy, with dates relative to today.
- `README.md`, `config.json`
- `tests/test_cli.py`

## Decisions I made

- `main()` takes an optional argument list, so the tests can run the real CLI without a terminal.
- Colors are switched off automatically when the output is not a terminal.
