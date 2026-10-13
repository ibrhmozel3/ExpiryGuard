"""Everything that reads or writes files: stock.csv, history.csv, config.json.

Three safety ideas:
1. Safe save: we write a temporary file first and then swap it in, so a crash
   can never leave a half-written stock.csv. The old version is kept as .bak.
2. UTF-8 with BOM ("utf-8-sig"), so Excel shows Turkish letters correctly.
3. Text starting with = + - @ gets a ' in front (CSV formula injection).
"""

import csv
import json
import os
import shutil
from datetime import datetime

from .models import StorageError, ValidationError, lot_key
from .validation import (
    MAX_PRICE, MAX_QTY, clean_text, missing_columns, parse_price, parse_qty, parse_row,
)

STOCK_COLUMNS = ["barcode", "name", "lot", "expiry", "qty", "unit_price", "supplier"]
HISTORY_COLUMNS = ["timestamp", "action", "barcode", "name", "lot", "qty", "value", "note"]
TEXT_COLUMNS = ["name", "lot", "supplier", "note"]
ACTIONS = ["ADD", "SELL", "EXPIRED", "RETURN"]
TIME_FORMAT = "%Y-%m-%d %H:%M"
MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_HISTORY_SIZE = 50 * 1024 * 1024
DANGEROUS_START = ("=", "+", "-", "@", "'")
DEFAULT_CONFIG = {"return_window_days": 90, "sell_first_days": 180}


def check_file(path, max_size=MAX_FILE_SIZE):
    if os.path.isdir(path):
        raise StorageError(f"{path} is a folder, not a file")
    if not os.path.isfile(path):
        raise StorageError(f"file not found: {path}")
    if os.path.getsize(path) > max_size:
        raise StorageError(f"{path} is too large (max {max_size // 1024} KB)")


def read_csv(path, max_size=MAX_FILE_SIZE):
    """Returns (column names, list of (line number, row dict))."""
    check_file(path, max_size)
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            first_line = f.readline()
            delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
            f.seek(0)
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = []
            for row in reader:
                rows.append((reader.line_num, row))
            return reader.fieldnames or [], rows
    except UnicodeDecodeError:
        raise StorageError(f"{path} is not a UTF-8 text file")
    except csv.Error as error:
        raise StorageError(f"{path} is not a valid CSV file ({error})")


def protect(text):
    """Excel runs a cell that starts with = as a formula. A leading ' stops that."""
    if text.startswith(DANGEROUS_START):
        return "'" + text
    return text


def unprotect(text):
    """The reverse of protect(), used when we read the file back."""
    if text.startswith("'") and text[1:2].startswith(DANGEROUS_START):
        return text[1:]
    return text


def to_cells(columns, values):
    cells = []
    for column, value in zip(columns, values):
        if column in TEXT_COLUMNS:
            cells.append(protect(str(value)))
        else:
            cells.append(str(value))
    return cells


def write_csv(path, columns, rows, keep_backup=False):
    """Safe save: write everything to a temp file, then swap it in."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    if keep_backup and os.path.exists(path):
        shutil.copy2(path, path + ".bak")

    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(to_cells(columns, row))
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def load_rows(path):
    """Reads lots from a CSV file. Bad rows are skipped and reported.

    Returns (lots, problems). Each problem looks like "line 7: reason".
    """
    columns, rows = read_csv(path)
    missing = missing_columns(columns)
    if missing:
        raise StorageError(f"{path} is missing columns: {', '.join(missing)}")

    lots, problems, seen = [], [], set()
    for line_number, row in rows:
        values = [v for v in row.values() if isinstance(v, str)]
        if "".join(values).strip() == "":
            continue
        for field in ["name", "lot", "supplier"]:
            if isinstance(row.get(field), str):
                row[field] = unprotect(row[field].strip())
        try:
            lot = parse_row(row)
        except ValidationError as error:
            problems.append(f"line {line_number}: {error}")
            continue
        if lot_key(lot) in seen:
            problems.append(f"line {line_number}: lot {lot['lot']} of {lot['barcode']} appears twice")
            continue
        seen.add(lot_key(lot))
        lots.append(lot)
    return lots, problems


def sort_key(lot):
    return (lot["name"].lower(), lot["expiry"], lot["lot"])


def save_stock(path, lots):
    rows = []
    for lot in sorted(lots, key=sort_key):
        rows.append([lot["barcode"], lot["name"], lot["lot"], lot["expiry"].isoformat(),
                     lot["qty"], f"{lot['unit_price']:.2f}", lot["supplier"]])
    write_csv(path, STOCK_COLUMNS, rows, keep_backup=True)


def restore_backup(path):
    """Puts stock.csv.bak back. The current stock becomes the new .bak (so it can be undone).

    The backup is fully checked first: if it is missing or broken, nothing is touched.
    """
    backup = path + ".bak"
    if not os.path.exists(backup):
        raise StorageError(f"no backup found at {backup}")
    lots, problems = load_rows(backup)
    if problems:
        raise StorageError(f"backup {backup} has {len(problems)} invalid row(s); not restoring it")
    save_stock(path, lots)
    return lots


def check_writable(path):
    """Opens history.csv for appending, to fail early before the stock changes."""
    if os.path.isdir(path):
        raise StorageError(f"{path} is a folder, not a file")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8"):
        pass


def make_entry(action, lot, qty, note, when):
    return {
        "timestamp": when.strftime(TIME_FORMAT),
        "action": action,
        "barcode": lot["barcode"],
        "name": lot["name"],
        "lot": lot["lot"],
        "qty": qty,
        "value": f"{lot['unit_price'] * qty:.2f}",
        "note": note,
    }


def ends_with_newline(path):
    with open(path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        return f.read(1) == b"\n"


def append_history(path, entries):
    """Adds lines at the end of history.csv. Old lines are never changed."""
    check_writable(path)
    is_empty = os.path.getsize(path) == 0
    if not is_empty and not ends_with_newline(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n")

    with open(path, "a", encoding="utf-8-sig" if is_empty else "utf-8", newline="") as f:
        writer = csv.writer(f)
        if is_empty:
            writer.writerow(HISTORY_COLUMNS)
        for entry in entries:
            values = [entry[column] for column in HISTORY_COLUMNS]
            writer.writerow(to_cells(HISTORY_COLUMNS, values))


def load_history(path):
    """Returns (entries, problems). History lines are checked like stock lines."""
    if not os.path.exists(path):
        return [], []
    columns, rows = read_csv(path, MAX_HISTORY_SIZE)
    entries, problems = [], []
    for line_number, row in rows:
        try:
            when = datetime.strptime((row.get("timestamp") or "").strip(), TIME_FORMAT)
            action = (row.get("action") or "").strip().upper()
            if action not in ACTIONS:
                raise ValidationError(f"unknown action {action[:20]!r}")
            entries.append({
                "when": when,
                "action": action,
                "name": clean_text(unprotect((row.get("name") or "").strip()), "name"),
                "qty": parse_qty(row.get("qty")),
                "value": parse_price(row.get("value"), limit=MAX_PRICE * MAX_QTY),
            })
        except (ValueError, ValidationError) as error:
            problems.append(f"history line {line_number}: {error}")
    return entries, problems


def load_config(path, must_exist):
    config = dict(DEFAULT_CONFIG)
    if not os.path.exists(path) and not must_exist:
        return config
    check_file(path, max_size=64 * 1024)
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (ValueError, RecursionError, UnicodeDecodeError) as error:
        raise StorageError(f"{path} is not valid JSON ({str(error)[:60]})")
    if not isinstance(data, dict):
        raise StorageError(f"{path} must contain a JSON object")

    for key, value in data.items():
        if key not in DEFAULT_CONFIG:
            raise StorageError(f"unknown setting {key[:30]!r} in {path}")
        if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 3650:
            raise StorageError(f"'{key}' must be a whole number of days (1-3650)")
        config[key] = value

    if config["sell_first_days"] < config["return_window_days"]:
        raise StorageError("sell_first_days must be >= return_window_days")
    return config
