"""ExpiryGuard command line interface.

Examples:
    python cli.py demo
    python cli.py check
    python cli.py sell parasetamol --qty 3
    python cli.py returns --supplier "Selcuk Ecza" --apply
    python cli.py --help
"""

import argparse
import os
import sys
from datetime import date, datetime

from expiryguard import demo, reports, rules, storage
from expiryguard.models import ExpiryGuardError, StockError, StorageError, ValidationError, lot_key, make_lot
from expiryguard.validation import (
    clean_text, merge_lots, parse_barcode, parse_date, parse_price, parse_qty,
)

CONFIG_NEXT_TO_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def barcode_type(text):
    try:
        return parse_barcode(text)
    except ValidationError as error:
        raise argparse.ArgumentTypeError(str(error))


def date_type(text):
    try:
        return parse_date(text, "date")
    except ValidationError as error:
        raise argparse.ArgumentTypeError(str(error))


def today_type(text):
    day = date_type(text)
    if day.year < 2001 or day.year > 2098:
        raise argparse.ArgumentTypeError("date must be between 2001 and 2098")
    return day


def qty_type(text):
    try:
        return parse_qty(text)
    except ValidationError as error:
        raise argparse.ArgumentTypeError(str(error))


def price_type(text):
    try:
        return parse_price(text)
    except ValidationError as error:
        raise argparse.ArgumentTypeError(str(error))


def month_type(text):
    try:
        return datetime.strptime(text, "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise argparse.ArgumentTypeError(f"month {text[:20]!r} must look like 2026-09")


def stock_path(args):
    return os.path.join(args.data_dir, "stock.csv")


def history_path(args):
    return os.path.join(args.data_dir, "history.csv")


def load(args, will_save=False, missing_ok=False):
    """Loads the stock. Before saving, broken rows must be fixed, or they would be lost.

    missing_ok: only "add" and "import" may start from an empty pharmacy.
    """
    path = stock_path(args)
    if not os.path.exists(path):
        if missing_ok:
            return []
        raise StorageError(f"no stock found at {path}. "
                           "Run 'python cli.py demo' or add a lot with 'python cli.py add'.")
    lots, problems = storage.load_rows(path)
    for problem in problems:
        print(f"warning: {path} {problem}", file=sys.stderr)
    if problems and will_save:
        raise StockError(f"{path} has {len(problems)} invalid row(s). "
                         "Fix them first, otherwise saving would delete them.")
    return lots


def now(args):
    return datetime.combine(args.today, datetime.now().time())


def save(args, stock, entries):
    """Saves stock and history together.

    We first check that history.csv can be written, so a sale can never be
    saved in the stock but missing from the history.
    """
    had_stock = os.path.exists(stock_path(args))
    storage.check_writable(history_path(args))
    storage.save_stock(stock_path(args), stock)
    try:
        storage.append_history(history_path(args), entries)
    except BaseException:
        if had_stock:
            os.replace(stock_path(args) + ".bak", stock_path(args))
        else:
            os.remove(stock_path(args))
        raise


def free_file_name(path):
    """reports/x.csv -> reports/x_2.csv if x.csv already exists."""
    stem, extension = os.path.splitext(path)
    number = 2
    while os.path.exists(path):
        path = f"{stem}_{number}{extension}"
        number += 1
    return path


def file_name_part(text):
    """'Selçuk Ecza' -> 'selcuk_ecza' (safe to use in a file name)."""
    text = rules.normalize(text)
    result = ""
    for char in text:
        if char in "abcdefghijklmnopqrstuvwxyz0123456789":
            result += char
        else:
            result += "_"
    return result.strip("_")[:30] or "all"


def preview_note(apply):
    if not apply:
        print("\nPreview only - nothing was changed. Add --apply to do it.")


def cmd_demo(args, config):
    for path in [stock_path(args), history_path(args)]:
        if os.path.exists(path) and not args.force:
            raise StockError(f"{path} already exists. Use --force to replace it with demo data.")
    stock = demo.build_stock(args.today)
    history = demo.build_history(args.today, stock)
    storage.save_stock(stock_path(args), stock)
    rows = [[entry[column] for column in storage.HISTORY_COLUMNS] for entry in history]
    storage.write_csv(history_path(args), storage.HISTORY_COLUMNS, rows)
    print(f"Demo pharmacy created: {len(stock)} lots, {len(history)} history lines.")
    print("Try:  python cli.py check")


def cmd_check(args, config):
    groups = rules.group_by_risk(load(args), args.today, config)
    print(reports.render_check(groups, args.today, args.color, show_ok=args.all))


def cmd_add(args, config):
    stock = load(args, will_save=True, missing_ok=True)
    lot = make_lot(args.barcode, clean_text(args.name, "name"), clean_text(args.lot, "lot"),
                   args.expiry, args.qty, args.price, clean_text(args.supplier, "supplier", required=False))
    if lot["expiry"] < args.today:
        raise StockError(f"this lot already expired on {lot['expiry']}; it cannot be added")

    added, increased, conflicts = merge_lots(stock, [lot])
    if conflicts:
        raise StockError(conflicts[0])
    save(args, stock, [storage.make_entry("ADD", lot, lot["qty"], "manual add", now(args))])
    if added:
        print(f"Added new lot: {lot['name']} lot {lot['lot']} (+{lot['qty']} boxes)")
    else:
        print(f"Increased existing lot: {lot['name']} lot {lot['lot']} (+{lot['qty']} boxes)")


def cmd_sell(args, config):
    stock = load(args, will_save=True)
    product_lots = rules.find_product(stock, args.product)
    plan = rules.plan_sale(product_lots, args.qty, args.today)

    entries, messages = [], []
    for lot, take in plan:
        entries.append(storage.make_entry("SELL", lot, take, "", now(args)))
        messages.append(f"Sold {take} x {lot['name']} from lot {lot['lot']} "
                        f"(expires {lot['expiry']}), {lot['qty'] - take} left in that lot")

    stock = rules.apply_plan(stock, plan)
    save(args, stock, entries)
    print("\n".join(messages))


def cmd_fefo(args, config):
    lots = sorted(rules.find_product(load(args), args.product), key=rules.by_expiry)
    print(reports.render_fefo(lots, args.today, config, args.color))


def cmd_remove_expired(args, config):
    stock = load(args, will_save=args.apply)
    expired = rules.expired_lots(stock, args.today)
    if not expired:
        print("No expired lots. Nothing to remove.")
        return

    print(f"{'Removing' if args.apply else 'Would remove'} {len(expired)} expired lots:")
    for lot in expired:
        print(reports.lot_line(lot, args.today))
    print(f"Loss: {reports.money(rules.total_value(expired))}")

    if args.apply:
        entries = [storage.make_entry("EXPIRED", lot, lot["qty"], "removed from shelf", now(args))
                   for lot in expired]
        expired_keys = {lot_key(lot) for lot in expired}
        save(args, [lot for lot in stock if lot_key(lot) not in expired_keys], entries)
    preview_note(args.apply)


def cmd_returns(args, config):
    stock = load(args, will_save=args.apply)
    supplier = (args.supplier or "").strip()
    to_return = rules.lots_to_return(stock, args.today, config, supplier)
    who = supplier or "all suppliers"
    if not to_return:
        print(f"Nothing to return for {who}.")
        return

    print(f"Return list for {who} (lots expiring within {config['return_window_days']} days):")
    for lot in to_return:
        print(reports.lot_line(lot, args.today) + f"  [{lot['supplier'] or 'no supplier'}]")
    print(f"Refund value: {reports.money(rules.total_value(to_return))}")

    if args.apply:
        file_name = f"returns_{file_name_part(who)}_{args.today}.csv"
        out = free_file_name(os.path.join(args.out_dir, file_name))
        storage.write_csv(out, reports.RETURN_COLUMNS, reports.return_rows(to_return))
        entries = [storage.make_entry("RETURN", lot, lot["qty"], "sent to supplier", now(args))
                   for lot in to_return]
        return_keys = {lot_key(lot) for lot in to_return}
        save(args, [lot for lot in stock if lot_key(lot) not in return_keys], entries)
        print(f"Return list saved to {out}")
    preview_note(args.apply)


def cmd_import(args, config):
    incoming, problems = storage.load_rows(args.file)
    stock = load(args, will_save=args.apply, missing_ok=True)

    fresh = []
    for lot in incoming:
        if lot["expiry"] < args.today:
            problems.append(f"lot {lot['lot']} of {lot['name']} already expired on {lot['expiry']}")
        else:
            fresh.append(lot)

    working_copy = [dict(lot) for lot in stock]
    added, increased, conflicts = merge_lots(working_copy, fresh)

    print(f"Read {len(incoming)} valid rows from {args.file}")
    print(f"  new lots: {len(added)}   increased lots: {len(increased)}")
    for message in problems + conflicts:
        print(f"  skipped - {message}")

    if not added and not increased:
        print("\nNothing to import.")
        return
    if args.apply:
        note = f"import {os.path.basename(args.file)}"
        entries = [storage.make_entry("ADD", lot, lot["qty"], note, now(args)) for lot in added + increased]
        save(args, working_copy, entries)
        print("Stock updated.")
    preview_note(args.apply)


def cmd_restore(args, config):
    path = stock_path(args)
    backup = path + ".bak"
    if not os.path.exists(backup):
        raise StorageError(f"no backup found at {backup}")
    lots, problems = storage.load_rows(backup)
    if problems:
        raise StorageError(f"backup {backup} has {len(problems)} invalid row(s); not restoring it")
    print(f"Backup {backup} has {len(lots)} lots.")
    if args.apply:
        storage.restore_backup(path)
        print("Stock restored from the backup. Run 'restore --apply' again to undo.")
        print("Note: history.csv is not changed by a restore.")
    preview_note(args.apply)


def cmd_report(args, config):
    entries, problems = storage.load_history(history_path(args))
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)
    month = args.month or args.today.strftime("%Y-%m")
    print(reports.monthly_report(entries, month))


COMMANDS = {
    "demo": cmd_demo,
    "check": cmd_check,
    "add": cmd_add,
    "sell": cmd_sell,
    "fefo": cmd_fefo,
    "remove-expired": cmd_remove_expired,
    "returns": cmd_returns,
    "import": cmd_import,
    "report": cmd_report,
    "restore": cmd_restore,
}


class Parser(argparse.ArgumentParser):
    """argparse prints the full usage line before every error. We print only one clear line."""

    def error(self, message):
        message = message.replace("argument ", "", 1)
        print(f"error: {message}", file=sys.stderr)
        print(f"help:  python3 {self.prog} --help", file=sys.stderr)
        sys.exit(2)


HELP = {
    "demo": ("demo [--force]", "create a demo pharmacy",
             "python3 cli.py demo\n  python3 cli.py demo --force      (start again from zero)"),
    "check": ("check [--all]", "daily expiry check",
              "python3 cli.py check\n  python3 cli.py check --all        (also show lots that are OK)"),
    "add": ("add --barcode B --name N --lot L --expiry DATE --qty Q --price P [--supplier S]",
            "add a delivered lot",
            'python3 cli.py add --barcode 8690000000173 --name "Parasetamol 1000mg" --lot P77 '
            '--expiry 2027-09-30 --qty 10 --price 58'),
    "sell": ("sell PRODUCT [--qty Q]", "sell boxes (oldest expiry first)",
             'python3 cli.py sell "parasetamol 500" --qty 3\n  python3 cli.py sell 8690000000012'),
    "fefo": ("fefo PRODUCT", "show which lot to sell first",
             'python3 cli.py fefo "parasetamol 500"'),
    "remove-expired": ("remove-expired [--apply]", "take expired lots off the stock",
                       "python3 cli.py remove-expired            (preview)\n"
                       "  python3 cli.py remove-expired --apply    (really remove)"),
    "returns": ("returns [--supplier S] [--apply]", "list lots to send back to the supplier",
                "python3 cli.py returns --supplier selcuk\n"
                "  python3 cli.py returns --supplier selcuk --apply"),
    "import": ("import FILE [--apply]", "import lots from another CSV file",
               "python3 cli.py import samples/delivery_tr_excel.csv\n"
               "  python3 cli.py import samples/delivery_tr_excel.csv --apply"),
    "report": ("report [--month YYYY-MM]", "monthly loss report",
               "python3 cli.py report\n  python3 cli.py report --month 2026-09"),
    "restore": ("restore [--apply]", "put back the stock from before the last change",
                "python3 cli.py restore            (preview)\n"
                "  python3 cli.py restore --apply    (restore; run again to undo)"),
}


def build_parser():
    common = Parser(add_help=False)
    other = common.add_argument_group("other options")
    other.add_argument("--today", type=today_type, default=date.today(),
                       help="pretend today is this date (YYYY-MM-DD)")
    other.add_argument("--data-dir", default="data", help="folder with stock.csv and history.csv")
    other.add_argument("--config", help="settings file (default: config.json)")
    other.add_argument("--no-color", action="store_true", help="plain output without colors")

    parser = Parser(prog="cli.py", usage="python3 cli.py COMMAND [options]", description="ExpiryGuard - pharmacy expiry tracker",
                    epilog="Help for one command:  python3 cli.py sell --help")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    def add_command(name):
        usage, short_help, examples = HELP[name]
        return commands.add_parser(
            name, parents=[common], prog=f"cli.py {name}", help=short_help, description=short_help,
            usage=f"python3 cli.py {usage}", epilog="examples:\n  " + examples,
            formatter_class=argparse.RawDescriptionHelpFormatter)

    p = add_command("demo")
    p.add_argument("--force", action="store_true", help="overwrite existing data")

    p = add_command("check")
    p.add_argument("--all", action="store_true", help="also list lots that are OK")

    p = add_command("add")
    p.add_argument("--barcode", required=True, type=barcode_type, help="13 digits")
    p.add_argument("--name", required=True, help='use quotes if it has spaces: "Parasetamol 500mg"')
    p.add_argument("--lot", required=True, help="lot number printed on the box")
    p.add_argument("--expiry", required=True, type=date_type, help="2027-09-30, 30.09.2027 or 2027-09")
    p.add_argument("--qty", required=True, type=qty_type, help="number of boxes")
    p.add_argument("--price", required=True, type=price_type, help="price of one box: 58 or 58,50")
    p.add_argument("--supplier", default="", help="optional")

    p = add_command("sell")
    p.add_argument("product", help="barcode or words of the name")
    p.add_argument("--qty", type=qty_type, default=1, help="number of boxes (default 1)")

    p = add_command("fefo")
    p.add_argument("product", help="barcode or words of the name")

    p = add_command("remove-expired")
    p.add_argument("--apply", action="store_true", help="really do it (default is preview)")

    p = add_command("returns")
    p.add_argument("--supplier", help="only this supplier")
    p.add_argument("--out-dir", default="reports", help="where to save the return list")
    p.add_argument("--apply", action="store_true", help="save the list and remove the lots")

    p = add_command("import")
    p.add_argument("file", help="CSV with barcode,name,lot,expiry,qty,unit_price[,supplier]")
    p.add_argument("--apply", action="store_true", help="really import (default is preview)")

    p = add_command("report")
    p.add_argument("--month", type=month_type, help="YYYY-MM (default: this month)")

    p = add_command("restore")
    p.add_argument("--apply", action="store_true", help="really restore (default is preview)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.color = sys.stdout.isatty() and not args.no_color
    try:
        if args.config:
            config = storage.load_config(args.config, must_exist=True)
        else:
            config = storage.load_config(CONFIG_NEXT_TO_SCRIPT, must_exist=False)
        COMMANDS[args.command](args, config)
    except ExpiryGuardError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        where = f": {error.filename}" if error.filename else ""
        print(f"error: {error.strerror or error}{where}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ncancelled", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
