# Aissam Ourahmoune: validation and import

**Name:** Aissam Ourahmoune · **Student ID:** 2509115126 · **GitHub:** [aissam1234567](https://github.com/aissam1234567)

## What I built

- `expiryguard/validation.py`: the checks that every value has to pass.
  - `parse_date`: three date formats, including month-only dates like `2027-05`.
  - `parse_barcode`: 13 digits and a correct EAN-13 check digit (`check_digit`).
  - `parse_qty` and `parse_price`: positive whole numbers, finite prices, Turkish decimal comma.
  - `clean_text`: no empty values, no control characters, a length limit.
  - `parse_row`: turns one CSV row into a `Lot`.
  - `merge_lots`: adds imported lots to the stock and detects conflicts.
- `samples/delivery_tr_excel.csv` and `samples/bad_rows.csv`
- `tests/test_validation.py`

## Decisions I made

- Bad rows are skipped and reported with their line number instead of stopping the whole import.
- `only_digits` checks every character against "0123456789", because `isdigit()` also accepts Arabic digits and `²`, and `int()` accepts "1_000".
- Prices use `Decimal`, not `float`, so money is never rounded wrongly.
