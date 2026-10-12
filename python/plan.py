"""Payment reminder rules engine."""

import argparse
import json
import sys
from datetime import date

STEP_RANK = {"friendly": 1, "firm": 2, "final": 3}
STEP_LABELS = {
    "duplicate_id": "Duplicate invoice ID",
    "invalid_amount": "Amount is missing or invalid",
    "missing_due_date": "Due date is missing",
    "invalid_due_date": "Due date is not a valid date",
    "invalid_paid_date": "Paid date is invalid or after today",
}


def parse_iso_date(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def format_amount(amount, currency):
    return f"{currency} {amount:,.2f}"


def build_message(invoice, days_overdue):
    customer = invoice.get("customer", "Customer")
    invoice_id = invoice.get("id", "")
    due_date = invoice.get("due_date", "")
    currency = invoice.get("currency", "EUR")
    amount = invoice.get("amount", 0)
    phrase = "day" if days_overdue == 1 else "days"
    return (
        f"Dear {customer},\n\n"
        f"This is a reminder for invoice {invoice_id} due on {due_date}. "
        f"The amount due is {format_amount(float(amount), currency)} and it is {days_overdue} {phrase} overdue.\n\n"
        "Kind regards,\nThe business"
    )


def build_plan(invoices, sent, today):
    """Return the plan for `today` as a dict with today, actions, and skipped."""
    if not isinstance(invoices, list):
        invoices = []
    if not isinstance(sent, list):
        sent = []

    today_date = parse_iso_date(today)
    if today_date is None:
        raise ValueError(f"Invalid date '{today}'. Use YYYY-MM-DD.")

    invoice_counts = {}
    for invoice in invoices:
        invoice_id = invoice.get("id")
        if invoice_id is None:
            continue
        invoice_counts[invoice_id] = invoice_counts.get(invoice_id, 0) + 1
    duplicate_ids = {invoice_id for invoice_id, count in invoice_counts.items() if count > 1}

    skipped = []
    skipped_map = {}
    actions = []
    valid_sent = {
        entry.get("invoice_id"): entry.get("step")
        for entry in sent
        if isinstance(entry, dict)
        and isinstance(entry.get("invoice_id"), str)
        and entry.get("step") in STEP_RANK
    }

    for invoice in invoices:
        if not isinstance(invoice, dict):
            continue
        invoice_id = invoice.get("id")
        if invoice_id in duplicate_ids:
            skipped_map[invoice_id] = "duplicate_id"
            continue

        amount = invoice.get("amount")
        if "amount" not in invoice or not isinstance(amount, (int, float)) or isinstance(amount, bool) or amount <= 0:
            skipped_map[invoice_id] = "invalid_amount"
            continue

        due_date_raw = invoice.get("due_date")
        if due_date_raw in (None, ""):
            skipped_map[invoice_id] = "missing_due_date"
            continue
        due_date = parse_iso_date(due_date_raw)
        if due_date is None:
            skipped_map[invoice_id] = "invalid_due_date"
            continue

        paid_date_raw = invoice.get("paid_date")
        if paid_date_raw not in (None, ""):
            paid_date = parse_iso_date(paid_date_raw)
            if paid_date is None or paid_date > today_date:
                skipped_map[invoice_id] = "invalid_paid_date"
                continue
            if paid_date <= today_date:
                continue

        days_overdue = (today_date - due_date).days
        if days_overdue < 3:
            continue

        if days_overdue >= 24:
            highest_step = "final"
        elif days_overdue >= 10:
            highest_step = "firm"
        else:
            highest_step = "friendly"

        seen_steps_for_invoice = []
        for invoice_key, step in valid_sent.items():
            if invoice_key == invoice_id:
                seen_steps_for_invoice.append(step)

        if any(STEP_RANK.get(step, 0) >= STEP_RANK[highest_step] for step in seen_steps_for_invoice):
            continue

        actions.append(
            {
                "invoice_id": invoice_id,
                "step": highest_step,
                "needs_approval": highest_step in {"firm", "final"},
                "days_overdue": days_overdue,
                "message": build_message(invoice, days_overdue),
            }
        )

    for invoice_id, reason in sorted(skipped_map.items(), key=lambda item: item[0]):
        skipped.append({"invoice_id": invoice_id, "reason": reason})
    for action in sorted(actions, key=lambda item: item["invoice_id"]):
        action["invoice_id"] = action["invoice_id"]
    actions = sorted(actions, key=lambda item: item["invoice_id"])

    return {"today": today, "actions": actions, "skipped": skipped}


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Plan today's payment reminders.")
    parser.add_argument("--invoices", required=True, help="path to invoices.json")
    parser.add_argument("--sent", required=True, help="path to sent.json")
    parser.add_argument("--today", required=True, help="date as YYYY-MM-DD")
    parser.add_argument("--out", required=True, help="path to write the plan JSON")
    args = parser.parse_args()

    try:
        invoices = read_json(args.invoices)
        sent = read_json(args.sent)
        plan = build_plan(invoices, sent, args.today)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
            f.write("\n")
        return 0
    except FileNotFoundError as exc:
        print(f"Error: Could not read file: {exc.filename}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in {exc.doc!r}: {exc.msg}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
