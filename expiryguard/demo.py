"""Builds a fictional pharmacy so the tool can be tried in seconds.

All dates are relative to 'today', so the demo always shows every risk level.
Medicine names are generic; prices and barcodes are made up.
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal

from .models import make_lot
from .storage import make_entry
from .validation import check_digit


def fake_barcode(number):
    first_twelve = f"8690000{number:05d}"
    return first_twelve + str(check_digit(first_twelve))


PRODUCTS = [
    ("Parasetamol 500mg 20 tb", "45.50", "Selcuk Ecza"),
    ("Ibuprofen 400mg 20 tb", "62.00", "Selcuk Ecza"),
    ("Amoksisilin 1000mg 14 tb", "210.00", "Hedef Ecza"),
    ("Vitamin B12 Surup 150ml", "138.75", "Hedef Ecza"),
    ("Omeprazol 20mg 28 kps", "96.40", "Selcuk Ecza"),
    ("Setirizin 10mg 20 tb", "54.90", "Alliance"),
    ("Metformin 1000mg 100 tb", "120.00", "Alliance"),
    ("D Vitamini Damla 50ml", "88.00", "Hedef Ecza"),
    ("Burun Spreyi 15ml", "74.25", "Alliance"),
    ("Insulin Kalemi 3ml", "640.00", "Selcuk Ecza"),
    ("Oksimetazolin Damla 10ml", "39.90", "Alliance"),
    ("Magnezyum 365mg 30 tb", "155.00", "Hedef Ecza"),
]

DEMO_LOTS = [
    (2, "B118", -6, 3), (3, "V901", -20, 5),
    (0, "A2231", 50, 14), (6, "M440", 28, 9), (9, "I077", 75, 2),
    (4, "O310", 150, 12), (7, "D550", 110, 6), (5, "S203", 170, 18),
    (0, "A2310", 262, 40), (1, "F118", 400, 25), (2, "B140", 330, 10),
    (3, "V950", 290, 8), (4, "O355", 520, 20), (5, "S260", 600, 22),
    (6, "M470", 380, 15), (7, "D600", 450, 12), (8, "N101", 240, 30),
    (9, "I090", 300, 6), (10, "K12", 210, 16), (11, "G77", 365, 24),
]


def build_stock(today):
    lots = []
    for number, lot_code, days, qty in DEMO_LOTS:
        name, price, supplier = PRODUCTS[number]
        lots.append(make_lot(fake_barcode(number + 1), name, lot_code,
                             today + timedelta(days=days), qty, Decimal(price), supplier))
    return lots


def build_history(today, stock):
    """Three months of made-up activity, oldest first."""
    rng = random.Random(42)
    midnight = datetime(today.year, today.month, today.day)
    start = midnight - timedelta(days=90)
    entries = []

    for lot in stock:
        received = start + timedelta(days=rng.randint(0, 20), hours=9)
        entries.append(make_entry("ADD", lot, lot["qty"] + rng.randint(5, 30), "delivery", received))

    for day in range(90):
        when = start + timedelta(days=day, hours=rng.randint(9, 19), minutes=rng.randint(0, 59))
        sellable = [lot for lot in stock if lot["expiry"] >= when.date()]
        for lot in rng.sample(sellable, 3):
            entries.append(make_entry("SELL", lot, rng.randint(1, 3), "", when))

    syrup = PRODUCTS[3]
    spray = PRODUCTS[8]
    for days_ago, product, number, old_code, qty in [(70, syrup, 4, "V820", 4), (38, spray, 9, "N060", 3),
                                                     (35, syrup, 4, "V860", 6), (8, syrup, 4, "V880", 5)]:
        when = midnight - timedelta(days=days_ago) + timedelta(hours=9)
        old_lot = make_lot(fake_barcode(number), product[0], old_code, when.date(), qty,
                           Decimal(product[1]), product[2])
        entries.append(make_entry("EXPIRED", old_lot, qty, "removed from shelf", when))

    entries.sort(key=lambda entry: entry["timestamp"])
    return entries
