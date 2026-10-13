import unittest
from datetime import date
from decimal import Decimal

from expiryguard.models import ValidationError, make_lot
from expiryguard.validation import clean_text, merge_lots, parse_barcode, parse_date, parse_price, parse_qty


class ValidationTests(unittest.TestCase):
    def check_all_rejected(self, function, bad_values):
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    function(value)

    def test_dates(self):
        self.assertEqual(parse_date("2026-11-30"), date(2026, 11, 30))
        self.assertEqual(parse_date("30.11.2026"), date(2026, 11, 30))
        self.assertEqual(parse_date("2028-02"), date(2028, 2, 29))
        self.check_all_rejected(parse_date, ["2026-13-45", "2026-02-30", "", "tomorrow", "9" * 50])

    def test_barcodes(self):
        self.assertEqual(parse_barcode(" 8690000000012 "), "8690000000012")
        self.check_all_rejected(parse_barcode, ["8690000000013", "123", "86900000000ab", "٨٦٩٠٠٠٠٠٠٠٠١٢"])

    def test_quantities_and_prices(self):
        self.assertEqual(parse_qty("12"), 12)
        self.assertEqual(parse_price("45,5"), Decimal("45.50"))
        self.check_all_rejected(parse_qty, ["0", "-4", "1_000", "2.5", "999999999"])
        self.check_all_rejected(parse_price, ["abc", "-1", "-0", "NaN", "1e400", "1,000", "1."])

    def test_merge(self):
        def lot(code, qty=5, price="10"):
            return make_lot("8690000000012", "Test", code, date(2027, 1, 1), qty, Decimal(price))

        stock = [lot("A1")]
        added, increased, conflicts = merge_lots(stock, [lot("A1", qty=3), lot("A2"), lot("A1", price="99")])
        self.assertEqual((len(added), len(increased), len(conflicts)), (1, 1, 1))
        self.assertEqual(stock[0]["qty"], 8)

    def test_names_are_cleaned_and_unique(self):
        self.assertEqual(clean_text("  Test   Med ", "name"), "Test Med")
        stock = [make_lot("8690000000012", "Test Med", "A1", date(2027, 1, 1), 5, Decimal("1"))]
        other = make_lot("8690000000029", "test med", "B1", date(2027, 1, 1), 5, Decimal("1"))
        added, increased, conflicts = merge_lots(stock, [other])
        self.assertEqual((added, len(conflicts)), ([], 1))
