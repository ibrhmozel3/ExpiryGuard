# Ahmet Hakan Özel: business rules

**Name:** Ahmet Hakan Özel · **Student ID:** 2509011074 · **GitHub:** [hakanozel447-svg](https://github.com/hakanozel447-svg)

## What I built

- `expiryguard/rules.py`
  - The four risk levels and `classify`, which decides if a lot is expired, should be
    returned, should be sold first, or is OK, using the limits from `config.json`.
  - `group_by_risk`: puts every lot in its group, sorted by expiry.
  - `normalize`: makes "SELÇUK" and "selcuk" equal, so Turkish letters are optional.
  - `find_product`: finds one medicine by barcode or by words of its name ("para 1000"),
    and refuses to guess when the words match several medicines.
  - `plan_sale` and `apply_plan`: the FEFO logic. A sale takes boxes from the lot that
    expires first, can be split across lots, and never uses expired lots.
  - `lots_to_return` and `expired_lots`
- `tests/test_rules.py`

## Decisions I made

- Planning a sale and applying it are two separate functions, so the plan can be
  checked (and printed) before anything changes.
- The day of expiry still counts as sellable; the lot is expired from the next day.
