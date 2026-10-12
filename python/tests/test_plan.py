"""Rule tests for the reminder engine."""

import json
import subprocess
import sys
import unittest
from pathlib import Path

from plan import build_plan


class ReminderRulesTest(unittest.TestCase):
    def test_empty_input_gives_empty_plan(self):
        plan = build_plan([], [], "2026-10-12")
        self.assertEqual(plan, {"today": "2026-10-12", "actions": [], "skipped": []})

    def test_sample_data_matches_expected_actions_and_skips(self):
        invoices = json.loads(Path("../data/invoices.json").read_text(encoding="utf-8"))
        sent = json.loads(Path("../data/sent.json").read_text(encoding="utf-8"))

        plan = build_plan(invoices, sent, "2026-10-12")

        self.assertEqual(
            [item["invoice_id"] for item in plan["actions"]],
            ["INV-1001", "INV-1002", "INV-1004", "INV-1009", "INV-1011"],
        )
        self.assertEqual(
            [item["invoice_id"] for item in plan["skipped"]],
            ["INV-1007", "INV-1008", "INV-1010"],
        )
        self.assertEqual(plan["actions"][0]["step"], "firm")
        self.assertEqual(plan["actions"][0]["needs_approval"], True)
        self.assertIn("Alder Fabrication Ltd", plan["actions"][0]["message"])
        self.assertEqual(plan["actions"][1]["step"], "friendly")
        self.assertEqual(plan["actions"][3]["step"], "firm")
        self.assertEqual(plan["skipped"][0]["reason"], "invalid_due_date")
        self.assertEqual(plan["skipped"][1]["reason"], "missing_due_date")
        self.assertEqual(plan["skipped"][2]["reason"], "duplicate_id")

    def test_invalid_today_date_exits_nonzero(self):
        result = subprocess.run(
            [sys.executable, "plan.py", "--invoices", "../data/invoices.json", "--sent", "../data/sent.json", "--today", "2026-99-99", "--out", "../tmp-actions.json"],
            cwd=".",
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Invalid date", result.stderr or result.stdout)

    def test_empty_paid_date_is_invalid_paid_date(self):
        invoices = [{
            "id": "INV-EMPTY-PAID",
            "customer": "Example Ltd",
            "email": "accounts@example.test",
            "amount": 100.0,
            "currency": "EUR",
            "due_date": "2026-10-01",
            "paid_date": "",
        }]
        plan = build_plan(invoices, [], "2026-10-12")
        self.assertEqual(plan["skipped"], [{"invoice_id": "INV-EMPTY-PAID", "reason": "invalid_paid_date"}])


if __name__ == "__main__":
    unittest.main()
