import unittest
from datetime import date, timedelta
from decimal import Decimal

from expiryguard import rules
from expiryguard.models import StockError, make_lot

TODAY = date(2026, 10, 11)
CONFIG = {"return_window_days": 90, "sell_first_days": 180}


def lot(days, qty=10, barcode="8690000000012", name="Parasetamol 500mg"):
    return make_lot(barcode, name, f"L{days}", TODAY + timedelta(days=days), qty, Decimal("10"), "Selçuk")


class RulesTests(unittest.TestCase):
    def test_risk_level_boundaries(self):
        expected = {-1: rules.EXPIRED, 0: rules.RETURN, 90: rules.RETURN,
                    91: rules.SELL_FIRST, 180: rules.SELL_FIRST, 181: rules.OK}
        for days, risk in expected.items():
            with self.subTest(days=days):
                self.assertEqual(rules.classify(lot(days), TODAY, CONFIG), risk)

    def test_find_product(self):
        stock = [lot(30), lot(50, barcode="8690000000036", name="Parasetamol 1000mg"),
                 lot(50, barcode="8690000000029", name="İbuprofen 400mg")]
        self.assertEqual(len(rules.find_product(stock, "ıbuprofen")), 1)
        self.assertEqual(rules.find_product(stock, "para 1000")[0]["barcode"], "8690000000036")
        with self.assertRaises(StockError):
            rules.find_product(stock, "para")

    def test_fefo_sale_skips_expired_and_splits(self):
        stock = [lot(300, qty=10), lot(-3, qty=50), lot(20, qty=4)]
        plan = rules.plan_sale(stock, 6, TODAY)
        self.assertEqual([(l["lot"], take) for l, take in plan], [("L20", 4), ("L300", 2)])
        stock = rules.apply_plan(stock, plan)
        self.assertEqual([l["lot"] for l in stock], ["L300", "L-3"])

    def test_cannot_sell_more_than_sellable(self):
        with self.assertRaises(StockError):
            rules.plan_sale([lot(-3, qty=50), lot(20, qty=4)], 5, TODAY)

    def test_expiry_today_tomorrow_yesterday(self):
        today, tomorrow, yesterday = lot(0, qty=1), lot(1, qty=1), lot(-1, qty=1)
        plan = rules.plan_sale([tomorrow, yesterday, today], 2, TODAY)
        self.assertEqual([l["lot"] for l, take in plan], ["L0", "L1"])
        with self.assertRaises(StockError):
            rules.plan_sale([yesterday], 1, TODAY)
