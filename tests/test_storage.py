import os
import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal

from expiryguard import storage
from expiryguard.models import StorageError, make_lot


def sample_lot(name="Parasetamol"):
    return make_lot("8690000000012", name, "A1", date(2027, 1, 1), 5, Decimal("9.90"))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.stock = os.path.join(self.folder, "stock.csv")

    def tearDown(self):
        shutil.rmtree(self.folder)

    def write_file(self, name, text):
        path = os.path.join(self.folder, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_save_and_load_give_the_same_lots(self):
        lots = [sample_lot("İlaç Şurup"), sample_lot("=HYPERLINK(1)")]
        lots[1]["lot"] = "A2"
        storage.save_stock(self.stock, lots)
        loaded, problems = storage.load_rows(self.stock)
        self.assertEqual(problems, [])
        self.assertEqual(sorted(l["name"] for l in loaded), ["=HYPERLINK(1)", "İlaç Şurup"])
        with open(self.stock, encoding="utf-8-sig") as f:
            self.assertIn("'=HYPERLINK", f.read())

    def test_save_keeps_backup_and_leaves_no_temp_file(self):
        storage.save_stock(self.stock, [sample_lot()])
        storage.save_stock(self.stock, [])
        self.assertEqual(sorted(os.listdir(self.folder)), ["stock.csv", "stock.csv.bak"])

    def test_turkish_excel_file_and_bad_rows(self):
        path = self.write_file("in.csv", "barcode;name;lot;expiry;qty;unit_price\n"
                                         "8690000000012;Ok;A1;31.12.2027;5;9,90\n"
                                         "8690000000012;Bad;A2;2027-99-99;5;1\n")
        lots, problems = storage.load_rows(path)
        self.assertEqual(len(lots), 1)
        self.assertIn("line 3", problems[0])

    def test_files_we_refuse(self):
        with self.assertRaises(StorageError):
            storage.load_rows(os.path.join(self.folder, "missing.csv"))
        with self.assertRaises(StorageError):
            storage.load_rows(self.write_file("columns.csv", "a,b\n1,2\n"))
        with self.assertRaises(StorageError):
            storage.load_config(self.write_file("c.json", '{"return_window_days": true}'), True)
