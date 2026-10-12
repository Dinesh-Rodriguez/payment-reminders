"""The owner's page for payment reminders."""

import os
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from plan import build_plan, read_json

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(APP_DIR, "..", "data"))
if not os.path.isabs(DATA_DIR):
    DATA_DIR = os.path.join(APP_DIR, DATA_DIR)
DATA_DIR = os.path.abspath(DATA_DIR)
TODAY = os.environ.get("TODAY") or date.today().isoformat()
DECISIONS = {}


def human_reason(code):
    return {
        "duplicate_id": "Duplicate invoice ID",
        "invalid_amount": "Amount is missing or invalid",
        "missing_due_date": "Due date is missing",
        "invalid_due_date": "Due date is not a valid date",
        "invalid_paid_date": "Paid date is invalid or after today",
    }.get(code, code)


def load_plan():
    try:
        invoices = read_json(os.path.join(DATA_DIR, "invoices.json"))
        sent = read_json(os.path.join(DATA_DIR, "sent.json"))
        return build_plan(invoices, sent, TODAY), None
    except Exception as exc:  # pragma: no cover - UI error path
        return None, str(exc)


def render_page(plan, error_message):
    if error_message:
        content = (
            "<h1>Payment reminders</h1>"
            f"<p class='error'>Could not read the invoice data: {escape(error_message)}</p>"
            "<p>Please check the data files and try again.</p>"
        )
    elif not plan or (not plan["actions"] and not plan["skipped"]):
        content = (
            "<h1>Payment reminders</h1>"
            "<p>Nothing to do today.</p>"
        )
    else:
        action_rows = []
        for action in plan["actions"]:
            invoice_id = action["invoice_id"]
            decision = DECISIONS.get(invoice_id)
            status = "<span class='status'>No decision yet</span>"
            if decision == "approved":
                status = "<span class='status approved'>Approved</span>"
            elif decision == "rejected":
                status = "<span class='status rejected'>Rejected</span>"

            form = (
                "<form method='post' action='/decision'>"
                f"<input type='hidden' name='invoice_id' value='{escape(invoice_id, quote=True)}'>"
                f"<input type='hidden' name='step' value='{escape(action['step'], quote=True)}'>"
                "<button type='submit' name='decision' value='approved'>Approve</button>"
                "<button type='submit' name='decision' value='rejected'>Reject</button>"
                "</form>"
            )
            customer = action["message"].split(",")[0].replace("Dear ", "")
            amount = action["message"].split("amount due is ")[1].split(" and it is ")[0]
            action_rows.append(
                f"<article class='card'>"
                f"<h2>{escape(action['invoice_id'])}</h2>"
                f"<p><strong>Customer:</strong> {escape(customer)}</p>"
                f"<p><strong>Step:</strong> {escape(action['step'])}</p>"
                f"<p><strong>Days overdue:</strong> {action['days_overdue']}</p>"
                f"<p><strong>Amount:</strong> {escape(amount)}</p>"
                f"<p><strong>Message:</strong> {escape(action['message'].replace(chr(10), ' '))}</p>"
                f"<p><strong>Decision:</strong> {status}</p>"
                f"{form}"
                "</article>"
            )

        skipped_rows = []
        for item in plan["skipped"]:
            skipped_rows.append(
                f"<li>{escape(item['invoice_id'])}: {escape(human_reason(item['reason']))}</li>"
            )

        content = (
            "<h1>Payment reminders</h1>"
            f"<p><strong>Today:</strong> {escape(TODAY)}</p>"
            f"<section><h2>Actions</h2>{''.join(action_rows) if action_rows else '<p>Nothing to do today.</p>'}</section>"
            f"<section><h2>Skipped</h2><ul>{''.join(skipped_rows) if skipped_rows else '<li>None.</li>'}</ul></section>"
        )

    page = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Payment reminders</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 1rem; background: #f4f6f8; color: #1c2328; }}
    h1, h2 {{ margin-top: 0; }}
    .card {{ background: white; border-radius: 10px; padding: 1rem; margin-bottom: 1rem; box-shadow: 0 2px 10px rgba(0,0,0,.05); }}
    .status {{ display: inline-block; padding: .2rem .6rem; border-radius: 999px; background: #eceff1; }}
    .status.approved {{ background: #d8f3dc; color: #165d2b; }}
    .status.rejected {{ background: #f5d7d7; color: #7d1f1f; }}
    button {{ background: #1f6feb; color: white; border: none; border-radius: 6px; padding: .6rem .9rem; margin-right: .5rem; margin-top: .5rem; }}
    form {{ margin-top: .75rem; }}
    ul {{ padding-left: 1.2rem; }}
    .error {{ color: #8b1e1e; font-weight: bold; }}
    @media (max-width: 390px) {{ body {{ padding: .6rem; }} button {{ width: 100%; margin-right: 0; }} }}
  </style>
</head>
<body>
  {content}
</body>
</html>"""
    return page.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        plan, error_message = load_plan()
        data = render_page(plan, error_message)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/decision":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8")
        body = parse_qs(payload, keep_blank_values=True)
        invoice_id = body.get("invoice_id", [""])[0]
        decision = body.get("decision", [""])[0]
        if invoice_id and decision in {"approved", "rejected"}:
            DECISIONS[invoice_id] = decision
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


def main():
    server = ThreadingHTTPServer(("", PORT), Handler)
    print(f"Serving on http://localhost:{PORT}/")
    server.serve_forever()


if __name__ == "__main__":
    main()
