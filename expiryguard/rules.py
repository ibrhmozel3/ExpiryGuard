"""Business rules: how risky is a lot, and which lot do we sell first?"""

from decimal import Decimal

from .models import StockError, days_left, lot_value

EXPIRED = "EXPIRED"
RETURN = "RETURN"
SELL_FIRST = "SELL_FIRST"
OK = "OK"
RISK_LEVELS = [EXPIRED, RETURN, SELL_FIRST, OK]

RISK_LABELS = {
    EXPIRED: "Expired - remove from shelf",
    RETURN: "Return to supplier now",
    SELL_FIRST: "Sell first - move to front",
    OK: "OK",
}


def classify(lot, today, config):
    days = days_left(lot, today)
    if days < 0:
        return EXPIRED
    if days <= config["return_window_days"]:
        return RETURN
    if days <= config["sell_first_days"]:
        return SELL_FIRST
    return OK


def by_expiry(lot):
    return (lot["expiry"], lot["lot"])


def group_by_risk(lots, today, config):
    """Returns {"EXPIRED": [...], "RETURN": [...], "SELL_FIRST": [...], "OK": [...]}."""
    groups = {}
    for risk in RISK_LEVELS:
        groups[risk] = []
    for lot in sorted(lots, key=by_expiry):
        groups[classify(lot, today, config)].append(lot)
    return groups


def total_value(lots):
    total = Decimal("0")
    for lot in lots:
        total += lot_value(lot)
    return total


TURKISH_LETTERS = {"ç": "c", "ğ": "g", "ı": "i", "İ": "i", "ö": "o", "ş": "s", "ü": "u",
                   "Ç": "c", "Ğ": "g", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u"}


def normalize(text):
    """'Selçuk ECZA' -> 'selcuk ecza', so users can type with or without Turkish letters.

    We replace İ before lower(), because "İ".lower() gives two characters in Python.
    """
    result = ""
    for char in text.strip():
        result += TURKISH_LETTERS.get(char, char)
    return result.lower()


def find_product(lots, query):
    """Finds all lots of ONE medicine by its barcode or by words of its name.

    "para 1000" matches "Parasetamol 1000mg": every typed word must be in the name.
    If two different medicines match, we stop instead of guessing.
    """
    query = query.strip()
    if query == "":
        raise StockError("empty product name")

    matches = []
    if len(query) == 13 and query.isdigit():
        for lot in lots:
            if lot["barcode"] == query:
                matches.append(lot)
    else:
        words = normalize(query).split()
        for lot in lots:
            name = normalize(lot["name"])
            if all(word in name for word in words):
                matches.append(lot)

    products = {}
    for lot in matches:
        products[lot["barcode"]] = lot["name"]

    if len(products) == 0:
        raise StockError(f"no medicine matches '{query}'")
    if len(products) > 1:
        lines = [f"'{query}' matches {len(products)} medicines:"]
        for barcode, name in sorted(products.items()):
            lines.append(f"  {name:<30} barcode {barcode}")
        lines.append("Type more of the name (for example the strength, like \"500\") or use the barcode.")
        raise StockError("\n".join(lines))
    return matches


def plan_sale(product_lots, qty, today):
    """FEFO (First Expiry, First Out): decides which lots a sale takes boxes from.

    Expired lots are never sold. One sale can use several lots.
    Nothing is changed here. Returns a list of (lot, boxes_taken).
    """
    sellable = []
    for lot in sorted(product_lots, key=by_expiry):
        if days_left(lot, today) >= 0:
            sellable.append(lot)

    available = 0
    for lot in sellable:
        available += lot["qty"]
    if qty > available:
        raise StockError(f"only {available} sellable boxes in stock, cannot sell {qty}")

    plan = []
    remaining = qty
    for lot in sellable:
        take = min(lot["qty"], remaining)
        plan.append((lot, take))
        remaining -= take
        if remaining == 0:
            break
    return plan


def apply_plan(stock, plan):
    """Takes the boxes out and returns the new stock without empty lots."""
    for lot, take in plan:
        lot["qty"] -= take
    return [lot for lot in stock if lot["qty"] > 0]


def lots_to_return(lots, today, config, supplier=None):
    result = []
    for lot in sorted(lots, key=by_expiry):
        if classify(lot, today, config) != RETURN:
            continue
        if supplier and normalize(supplier) not in normalize(lot["supplier"]):
            continue
        result.append(lot)
    return result


def expired_lots(lots, today):
    return [lot for lot in sorted(lots, key=by_expiry) if days_left(lot, today) < 0]
