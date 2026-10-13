"""Turns lots and history into text the pharmacist reads in the terminal."""

from decimal import Decimal

from .models import days_left, lot_value
from .rules import EXPIRED, OK, RETURN, RISK_LABELS, SELL_FIRST, classify, total_value

COLORS = {EXPIRED: "\033[91m", RETURN: "\033[33m", SELL_FIRST: "\033[93m", OK: "\033[92m"}
RESET = "\033[0m"
RETURN_COLUMNS = ["barcode", "name", "lot", "expiry", "qty", "unit_price", "value", "supplier"]


def money(amount):
    """Decimal("14380.5") -> "14.380,50 TL" (Turkish style)."""
    text = f"{amount:,.2f}"
    text = text.replace(",", "#").replace(".", ",").replace("#", ".")
    return text + " TL"


def colored(text, risk, use_color):
    if use_color:
        return COLORS[risk] + text + RESET
    return text


def lot_line(lot, today):
    days = days_left(lot, today)
    if days < 0:
        when = f"{-days} days ago"
    else:
        when = f"{days} days left"
    name = lot["name"][:28]
    return (f"   {name:<28} lot {lot['lot']:<8} exp {lot['expiry']}  "
            f"{lot['qty']:>4} boxes  {money(lot_value(lot)):>14}  ({when})")


def render_check(groups, today, use_color=False, show_ok=False):
    lines = [f"Stock check for {today}", ""]
    for risk, lots in groups.items():
        if risk == OK and not show_ok:
            continue
        lines.append(colored(f"{RISK_LABELS[risk].upper()} ({len(lots)})", risk, use_color))
        if not lots:
            lines.append("   nothing")
        for lot in lots:
            lines.append(lot_line(lot, today))
        lines.append("")

    at_risk = groups[EXPIRED] + groups[RETURN] + groups[SELL_FIRST]
    all_count = sum(len(lots) for lots in groups.values())
    lines.append(f"Lots needing attention: {len(at_risk)} of {all_count}")
    lines.append(f"Value at risk: {money(total_value(at_risk))}")
    return "\n".join(lines)


def render_fefo(lots, today, config, use_color=False):
    lines = [f"{lots[0]['name']} ({lots[0]['barcode']}) - sell in this order:"]
    number = 1
    for lot in lots:
        risk = classify(lot, today, config)
        label = "DO NOT SELL" if risk == EXPIRED else RISK_LABELS[risk]
        lines.append(f"  {number}. {lot_line(lot, today).strip()}  {colored(label, risk, use_color)}")
        number += 1
    return "\n".join(lines)


def return_rows(lots):
    rows = []
    for lot in lots:
        rows.append([lot["barcode"], lot["name"], lot["lot"], lot["expiry"].isoformat(), lot["qty"],
                     f"{lot['unit_price']:.2f}", f"{lot_value(lot):.2f}", lot["supplier"]])
    return rows


def monthly_report(entries, month):
    """Totals for one month (YYYY-MM) plus advice from the whole history."""
    boxes = {}
    values = {}
    losses = {}
    for entry in entries:
        if entry["when"].strftime("%Y-%m") != month:
            continue
        action = entry["action"]
        boxes[action] = boxes.get(action, 0) + entry["qty"]
        values[action] = values.get(action, Decimal("0")) + entry["value"]
        if action == "EXPIRED":
            losses[entry["name"]] = losses.get(entry["name"], Decimal("0")) + entry["value"]

    lines = [f"Monthly report {month}", ""]
    if not boxes:
        lines.append("No activity recorded in this month.")
        return "\n".join(lines)

    for action, label in [("ADD", "Received"), ("SELL", "Sold"),
                          ("RETURN", "Returned"), ("EXPIRED", "Expired (loss)")]:
        lines.append(f"  {label:<16}{boxes.get(action, 0):>6} boxes  "
                     f"{money(values.get(action, Decimal('0'))):>15}")

    sold = values.get("SELL", Decimal("0"))
    lost = values.get("EXPIRED", Decimal("0"))
    if sold + lost > 0:
        lines.append(f"\n  Loss rate: {lost / (sold + lost):.1%} of outgoing stock value expired")

    if losses:
        lines.append("\n  Biggest losses:")
        biggest = sorted(losses.items(), key=lambda item: item[1], reverse=True)
        for name, value in biggest[:3]:
            lines.append(f"    {name[:28]:<28} {money(value):>15}")

    expired_months = {}
    for entry in entries:
        if entry["action"] == "EXPIRED":
            expired_months.setdefault(entry["name"], set()).add(entry["when"].strftime("%Y-%m"))
    repeat = sorted(name for name, months in expired_months.items() if len(months) >= 2)
    if repeat:
        lines.append("\n  Suggestion: order less of " + ", ".join(repeat) + " (expired in several months)")
    return "\n".join(lines)
