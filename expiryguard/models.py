"""What a lot looks like, and the error types every module uses.

A lot is one batch of one medicine. We store it as a dictionary:

    {
        "barcode": "8690000000012",
        "name": "Parasetamol 500mg 20 tb",
        "lot": "A2231",
        "expiry": date(2026, 11, 30),
        "qty": 14,
        "unit_price": Decimal("45.50"),
        "supplier": "Selcuk Ecza",
    }
"""


class ExpiryGuardError(Exception):
    """Parent of all errors we expect. main() catches this one."""


class ValidationError(ExpiryGuardError):
    """A value from the user or a file is not acceptable."""


class StorageError(ExpiryGuardError):
    """A file could not be read or written."""


class StockError(ExpiryGuardError):
    """The stock operation is not possible (not enough boxes, etc.)."""


def make_lot(barcode, name, lot, expiry, qty, unit_price, supplier=""):
    return {
        "barcode": barcode,
        "name": name,
        "lot": lot,
        "expiry": expiry,
        "qty": qty,
        "unit_price": unit_price,
        "supplier": supplier,
    }


def lot_key(lot):
    return (lot["barcode"], lot["lot"])


def lot_value(lot):
    return lot["unit_price"] * lot["qty"]


def days_left(lot, today):
    return (lot["expiry"] - today).days
