"""Checks every value before it can enter the stock.

Nothing from a file or from the command line is trusted. Every parse_
function returns a clean value or raises ValidationError with a clear message.
"""

import calendar
from datetime import date, datetime
from decimal import Decimal

from .models import ValidationError, lot_key, make_lot

DIGITS = "0123456789"
REQUIRED_COLUMNS = ["barcode", "name", "lot", "expiry", "qty", "unit_price"]
MAX_LENGTH = {"name": 80, "lot": 20, "supplier": 60}
MAX_QTY = 100000
MAX_PRICE = Decimal("1000000")


def only_digits(text):
    """True for "123", False for "", "12a", "-5" or "1_000".

    We don't use str.isdigit() because it also accepts Arabic digits and "²".
    """
    if text == "":
        return False
    for char in text:
        if char not in DIGITS:
            return False
    return True


def short(text):
    """Cuts user input for error messages, so a huge input can't flood the screen."""
    text = text[:20]
    if not text.isprintable():
        return repr(text)
    return f'"{text}"'


def clean_text(value, field, required=True):
    text = " ".join((value or "").split())
    if text == "":
        if required:
            raise ValidationError(f"{field} is empty")
        return ""
    if len(text) > MAX_LENGTH[field]:
        raise ValidationError(f"{field} is too long (max {MAX_LENGTH[field]} characters)")
    if not text.isprintable():
        raise ValidationError(f"{field} contains hidden control characters")
    return text


def parse_date(value, field="expiry"):
    """Accepts 2026-11-30, 30.11.2026, or 2026-11 (= last day of that month)."""
    text = (value or "").strip()
    if len(text) > 10:
        raise ValidationError(f"{field} {short(text)} is not a valid date")

    result = None
    for date_format in ["%Y-%m-%d", "%d.%m.%Y"]:
        try:
            result = datetime.strptime(text, date_format).date()
            break
        except ValueError:
            pass

    if result is None:
        try:
            month = datetime.strptime(text, "%Y-%m")
        except ValueError:
            raise ValidationError(f"{field} {short(text)} is not a valid date (use YYYY-MM-DD)")
        last_day = calendar.monthrange(month.year, month.month)[1]
        result = date(month.year, month.month, last_day)

    if result.year < 1990 or result.year > 2100:
        raise ValidationError(f"{field} year {result.year} is out of range")
    return result


def check_digit(first_twelve):
    """EAN-13: digits in odd places count once, digits in even places count 3 times."""
    total = 0
    for position in range(12):
        digit = int(first_twelve[position])
        if position % 2 == 0:
            total += digit
        else:
            total += digit * 3
    return (10 - total % 10) % 10


def parse_barcode(value):
    code = (value or "").strip()
    if len(code) != 13 or not only_digits(code):
        raise ValidationError(f"barcode {short(code)} must be exactly 13 digits")
    if int(code[12]) != check_digit(code[:12]):
        raise ValidationError(f"barcode {code} has a wrong check digit (typo?)")
    return code


def parse_qty(value):
    text = (value or "").strip()
    if not only_digits(text):
        raise ValidationError(f"quantity {short(text)} must be a positive whole number")
    qty = int(text)
    if qty < 1 or qty > MAX_QTY:
        raise ValidationError(f"quantity must be between 1 and {MAX_QTY}")
    return qty


def parse_price(value, limit=MAX_PRICE):
    """Accepts 45, 45.5, 45.50 and the Turkish 45,50. Nothing else.

    We check the characters ourselves because Decimal() would also accept
    "NaN", "-0" and "1e400", and "1,000" must not silently become 1.00.
    """
    original = (value or "").strip()
    text = original.replace(",", ".")
    whole, separator, cents = text.partition(".")
    if not only_digits(whole) or len(whole) > 12:
        raise ValidationError(f"price {short(original)} must look like 45.50 or 45,50")
    if separator and (not only_digits(cents) or len(cents) > 2):
        raise ValidationError(f"price {short(original)} must look like 45.50 or 45,50")

    price = Decimal(text).quantize(Decimal("0.01"))
    if price > limit:
        raise ValidationError(f"amount must be at most {limit}")
    return price


def missing_columns(column_names):
    present = []
    for name in column_names:
        present.append((name or "").strip().lower())
    return [column for column in REQUIRED_COLUMNS if column not in present]


def parse_row(row):
    """Turns one CSV row (a dict of strings) into a lot dict."""
    clean = {}
    for key, value in row.items():
        if key is not None and isinstance(value, str):
            clean[key.strip().lower()] = value

    return make_lot(
        barcode=parse_barcode(clean.get("barcode")),
        name=clean_text(clean.get("name"), "name"),
        lot=clean_text(clean.get("lot"), "lot"),
        expiry=parse_date(clean.get("expiry")),
        qty=parse_qty(clean.get("qty")),
        unit_price=parse_price(clean.get("unit_price")),
        supplier=clean_text(clean.get("supplier"), "supplier", required=False),
    )


def merge_lots(stock, incoming):
    """Adds new lots to the stock list (changes the list).

    Same barcode + lot   -> the quantities are added.
    Same lot, different expiry or price, same barcode with another name,
    or same name with another barcode -> conflict: reported, nothing changed.
    Returns three lists: added, increased, conflicts.
    """
    by_key = {}
    names = {}
    barcodes = {}
    for lot in stock:
        by_key[lot_key(lot)] = lot
        names[lot["barcode"]] = lot["name"]
        barcodes[lot["name"].lower()] = lot["barcode"]

    added, increased, conflicts = [], [], []
    for new in incoming:
        known_name = names.get(new["barcode"])
        if known_name is not None and known_name.lower() != new["name"].lower():
            conflicts.append(f"{new['barcode']}: name '{new['name']}' differs from '{known_name}'")
            continue
        known_barcode = barcodes.get(new["name"].lower())
        if known_barcode is not None and known_barcode != new["barcode"]:
            conflicts.append(f"'{new['name']}' already exists with barcode {known_barcode}")
            continue

        old = by_key.get(lot_key(new))
        if old is None:
            stock.append(new)
            by_key[lot_key(new)] = new
            names[new["barcode"]] = new["name"]
            barcodes[new["name"].lower()] = new["barcode"]
            added.append(new)
        elif old["expiry"] != new["expiry"] or old["unit_price"] != new["unit_price"]:
            conflicts.append(f"{new['barcode']} lot {new['lot']}: expiry or price differs from stock")
        elif old["qty"] + new["qty"] > MAX_QTY:
            conflicts.append(f"{new['barcode']} lot {new['lot']}: quantity would be too large")
        else:
            old["qty"] += new["qty"]
            increased.append(new)

    return added, increased, conflicts
