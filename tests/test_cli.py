import contextlib
import io
import os
import shutil
import tempfile
import unittest

import cli
from expiryguard import storage
from unittest import mock


class CliTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.folder)

    def run_cli(self, *args):
        """Runs the real CLI and returns (exit code, normal output, error output)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main([*args, "--data-dir", self.folder, "--today", "2026-10-11"])
        return code, out.getvalue(), err.getvalue()

    def stock(self):
        return storage.load_rows(os.path.join(self.folder, "stock.csv"))[0]

    def test_demo_check_and_sell(self):
        self.assertEqual(self.run_cli("demo")[0], 0)
        code, out, _ = self.run_cli("check")
        self.assertIn("Value at risk", out)
        code, out, _ = self.run_cli("sell", "parasetamol", "--qty", "16")
        self.assertIn("A2231", out)
        self.assertNotIn("A2231", [lot["lot"] for lot in self.stock()])

    def test_preview_changes_nothing(self):
        self.run_cli("demo")
        before = self.stock()
        for command in ["remove-expired", "returns"]:
            self.run_cli(command)
        self.assertEqual(self.stock(), before)

    def test_errors_are_one_clean_line(self):
        for command in [["check"], ["sell", "parasetamol"], ["remove-expired", "--apply"]]:
            code, _, err = self.run_cli(*command)
            self.assertEqual(code, 1)
            self.assertIn("no stock found", err)
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                cli.main(["sell", "x", "--qty", "-5"])
        self.assertEqual(result.exception.code, 2)

    def test_broken_row_blocks_saving(self):
        self.run_cli("demo")
        with open(os.path.join(self.folder, "stock.csv"), "a", encoding="utf-8") as f:
            f.write("8690000000012,Broken,ZZ,not-a-date,1,1.00,\n")
        code, _, err = self.run_cli("sell", "parasetamol")
        self.assertEqual(code, 1)
        self.assertIn("invalid row", err)

    def test_failed_history_write_restores_stock(self):
        self.run_cli("demo")
        before = self.stock()
        with mock.patch("expiryguard.storage.append_history", side_effect=OSError("disk full")):
            code, out, err = self.run_cli("sell", "parasetamol", "--qty", "5")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(self.stock(), before)

    def test_missing_column_is_reported(self):
        self.run_cli("demo")
        path = os.path.join(self.folder, "stock.csv")
        with open(path, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
        lines[0] = lines[0].replace(",qty", "")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        code, _, err = self.run_cli("check")
        self.assertEqual(code, 1)
        self.assertIn("missing columns: qty", err)

    def test_duplicates_and_conflicts(self):
        self.run_cli("demo")
        new = ["add", "--barcode", "8690000000173", "--name", "  Test   Med ", "--lot", "A",
               "--expiry", "2027-01-01", "--qty", "1", "--price", "1"]
        self.assertEqual(self.run_cli(*new)[0], 0)
        code, out, _ = self.run_cli(*new)
        self.assertIn("Increased existing lot", out)
        other_expiry = new[:8] + ["2027-06-01"] + new[9:]
        self.assertEqual(self.run_cli(*other_expiry)[0], 1)
        other_barcode = ["add", "--barcode", "8690000000180"] + new[3:]
        self.assertEqual(self.run_cli(*other_barcode)[0], 1)

    def test_restore_backup(self):
        self.run_cli("demo")
        before = self.stock()
        self.run_cli("sell", "parasetamol", "--qty", "5")
        self.assertNotEqual(self.stock(), before)
        self.run_cli("restore")
        self.assertNotEqual(self.stock(), before)
        self.assertEqual(self.run_cli("restore", "--apply")[0], 0)
        self.assertEqual(self.stock(), before)

    def test_broken_backup_is_not_restored(self):
        self.run_cli("demo")
        self.run_cli("sell", "parasetamol")
        current = self.stock()
        with open(os.path.join(self.folder, "stock.csv.bak"), "a", encoding="utf-8") as f:
            f.write("8690000000012,Broken,ZZ,not-a-date,1,1.00,\n")
        code, _, err = self.run_cli("restore", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("not restoring", err)
        self.assertEqual(self.stock(), current)
