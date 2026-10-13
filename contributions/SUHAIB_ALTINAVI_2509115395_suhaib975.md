# Suhaib Altinavi: storage and data model

**Name:** Suhaib Altinavi · **Student ID:** 2509115395 · **GitHub:** [suhaib975](https://github.com/suhaib975)

## What I built

- `expiryguard/models.py`: `make_lot` and the helper functions for a lot (one batch of one medicine, stored as a dict) and the
  error classes (`ExpiryGuardError`, `ValidationError`, `StorageError`, `StockError`)
  that every other module uses.
- `expiryguard/storage.py`: everything that reads or writes files.
  - Reading CSV files, including files saved by Turkish Excel that use `;`.
  - Saving the stock safely: write to a temporary file, then `os.replace`, and keep a `.bak` copy.
  - The history log (`history.csv`), which is only ever appended to.
  - Loading and checking `config.json`.
  - Protection against CSV formula injection (`protect` / `unprotect`).
- `tests/test_storage.py`

## Decisions I made

- CSV instead of a database, because the pharmacist can open it in Excel and
  databases are the topic of Project 3.
- UTF-8 with BOM (`utf-8-sig`), because otherwise Excel shows Turkish letters wrong.
- A file size limit of 5 MB, so a huge file cannot freeze the program.
