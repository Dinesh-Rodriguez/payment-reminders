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
            "<div class='page-shell'>"
            "<header class='topbar'>"
            "<div><p class='eyebrow'>Payment reminder board</p><h1>Unable to load plan</h1></div>"
            f"<div class='date-pill'>{escape(TODAY)}</div>"
            "</header>"
            "<section class='panel error-panel'>"
            f"<p class='error'>Could not read the invoice data: {escape(error_message)}</p>"
            "<p>Please check the data files and try again.</p>"
            "</section>"
            "</div>"
        )
    elif not plan or (not plan["actions"] and not plan["skipped"]):
        content = (
            "<div class='page-shell'>"
            "<header class='topbar'>"
            "<div><p class='eyebrow'>Payment reminder board</p><h1>Today’s actions</h1></div>"
            f"<div class='date-pill'>{escape(TODAY)}</div>"
            "</header>"
            "<section class='panel empty-panel'>"
            "<h2>Nothing to do today</h2>"
            "<p>No invoices require a reminder on this date.</p>"
            "</section>"
            "</div>"
        )
    else:
        action_rows = []
        approval_count = 0
        for action in plan["actions"]:
            invoice_id = action["invoice_id"]
            decision = DECISIONS.get(invoice_id)
            status = "<span class='status'>No decision yet</span>"
            if decision == "approved":
                status = "<span class='status approved'>Approved</span>"
            elif decision == "rejected":
                status = "<span class='status rejected'>Rejected</span>"
            if action["needs_approval"]:
                approval_count += 1

            form = (
                "<form method='post' action='/decision' class='decision-form'>"
                f"<input type='hidden' name='invoice_id' value='{escape(invoice_id, quote=True)}'>"
                f"<input type='hidden' name='step' value='{escape(action['step'], quote=True)}'>"
                "<button type='submit' name='decision' value='approved' class='approve'>Approve</button>"
                "<button type='submit' name='decision' value='rejected' class='reject'>Reject</button>"
                "</form>"
            )
            customer = action["message"].split(",")[0].replace("Dear ", "")
            amount = action["message"].split("amount due is ")[1].split(" and it is ")[0]
            action_rows.append(
                f"<article class='card action-card'>"
                f"<div class='card-head'><span class='tag {escape(action['step'])}'>{escape(action['step'].title())}</span><h2>{escape(action['invoice_id'])}</h2></div>"
                f"<div class='meta-grid'><div><strong>Customer</strong><span>{escape(customer)}</span></div>"
                f"<div><strong>Days overdue</strong><span>{action['days_overdue']}</span></div>"
                f"<div><strong>Amount</strong><span>{escape(amount)}</span></div>"
                f"<div><strong>Decision</strong><span>{status}</span></div></div>"
                f"<p class='message'><strong>Message</strong><br>{escape(action['message'].replace(chr(10), ' '))}</p>"
                f"{form}"
                "</article>"
            )

        skipped_rows = []
        for item in plan["skipped"]:
            skipped_rows.append(
                f"<li>{escape(item['invoice_id'])}: {escape(human_reason(item['reason']))}</li>"
            )

        summary = (
            "<div class='summary-grid'>"
            f"<div class='summary-box'><span>Open reminders</span><strong>{len(plan['actions'])}</strong></div>"
            f"<div class='summary-box warning'><span>Need approval</span><strong>{approval_count}</strong></div>"
            f"<div class='summary-box muted'><span>Skipped</span><strong>{len(plan['skipped'])}</strong></div>"
            "</div>"
        )

        content = (
            "<div class='page-shell'>"
            "<header class='topbar'>"
            "<div><p class='eyebrow'>Payment reminder board</p><h1>Today’s actions</h1></div>"
            f"<div class='date-pill'>{escape(TODAY)}</div>"
            "</header>"
            f"{summary}"
            f"<section class='panel'><h2>Actions</h2>{''.join(action_rows) if action_rows else '<p>Nothing to do today.</p>'}</section>"
            f"<section class='panel'><h2>Skipped invoices</h2><ul class='skipped-list'>{''.join(skipped_rows) if skipped_rows else '<li>None.</li>'}</ul></section>"
            "</div>"
        )

    page = f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Payment reminders</title>
  <style>
    :root {{
      --bg: #f3f6fb;
      --panel: #ffffff;
      --panel-alt: #eef4ff;
      --ink: #1b2430;
      --muted: #5d6b7a;
      --line: #dfe7f1;
      --primary: #1f6feb;
      --friendly: #2e7d32;
      --firm: #ef6c00;
      --final: #c62828;
      --approved: #dff5e4;
      --rejected: #f8d7da;
      --warning: #fff4de;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; font-family: Arial, sans-serif; background: linear-gradient(180deg, #eef4ff 0%, #f3f6fb 100%);
      color: var(--ink); padding: 1rem;
    }}
    .page-shell {{ max-width: 980px; margin: 0 auto; }}
    .topbar {{
      display: flex; justify-content: space-between; align-items: center; gap: 1rem;
      margin-bottom: 1rem; padding: .5rem 0 .25rem;
    }}
    .eyebrow {{ margin: 0; font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }}
    h1 {{ margin: .15rem 0 0; font-size: clamp(1.8rem, 3vw, 2.6rem); }}
    h2 {{ margin: 0 0 .75rem; font-size: 1.15rem; }}
    .date-pill {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 999px;
      padding: .6rem 1rem; font-weight: bold; white-space: nowrap; box-shadow: 0 4px 12px rgba(15,23,42,.04);
    }}
    .summary-grid {{
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .9rem; margin-bottom: 1.25rem;
    }}
    .summary-box {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: .9rem 1rem;
      box-shadow: 0 4px 12px rgba(15,23,42,.04);
    }}
    .summary-box.warning {{ background: var(--warning); }}
    .summary-box.muted {{ background: #f7f9fb; }}
    .summary-box span {{ display: block; color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .04em; }}
    .summary-box strong {{ display: block; margin-top: .25rem; font-size: 1.8rem; }}
    .panel {{ background: transparent; margin-bottom: 1.25rem; }}
    .card {{
      background: var(--panel); border: 1px solid var(--line); border-radius: 16px;
      padding: 1rem; margin-bottom: 1rem; box-shadow: 0 4px 16px rgba(15,23,42,.04);
    }}
    .card-head {{ display: flex; justify-content: space-between; align-items: center; gap: .75rem; margin-bottom: .75rem; }}
    .card-head h2 {{ margin: 0; font-size: 1.25rem; }}
    .tag {{
      display: inline-block; border-radius: 999px; padding: .3rem .7rem; font-size: .72rem; font-weight: bold;
      text-transform: uppercase; color: white;
    }}
    .tag.friendly {{ background: var(--friendly); }}
    .tag.firm {{ background: var(--firm); }}
    .tag.final {{ background: var(--final); }}
    .meta-grid {{
      display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .8rem; margin-bottom: .75rem;
    }}
    .meta-grid div {{ display: flex; flex-direction: column; gap: .2rem; }}
    .meta-grid strong {{ color: var(--muted); font-size: .76rem; text-transform: uppercase; letter-spacing: .04em; }}
    .message {{ margin: .5rem 0 1rem; padding: .85rem .9rem; background: var(--panel-alt); border-radius: 12px; line-height: 1.5; }}
    .status {{ display: inline-block; padding: .24rem .7rem; border-radius: 999px; background: #ecf0f4; color: var(--ink); font-weight: 700; }}
    .status.approved {{ background: var(--approved); color: #1d5e2d; }}
    .status.rejected {{ background: var(--rejected); color: #7d1f1f; }}
    .decision-form {{ display: flex; gap: .6rem; flex-wrap: wrap; margin-top: .25rem; }}
    button {{
      flex: 1 1 120px; background: var(--primary); color: white; border: none; border-radius: 10px;
      padding: .85rem 1rem; font-size: .96rem; font-weight: bold; cursor: pointer;
    }}
    button:hover {{ filter: brightness(0.97); }}
    button.reject {{ background: #6c757d; }}
    .skipped-list {{ padding-left: 1.2rem; margin: 0; line-height: 1.7; }}
    .error {{ color: #8b1e1e; font-weight: bold; }}
    .empty-panel, .error-panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 1.3rem; box-shadow: 0 4px 12px rgba(15,23,42,.04); }}
    @media (max-width: 390px) {{
      body {{ padding: .7rem; }}
      .summary-grid {{ grid-template-columns: 1fr; }}
      .meta-grid {{ grid-template-columns: 1fr; }}
      .topbar {{ align-items: flex-start; flex-direction: column; }}
      .date-pill {{ align-self: stretch; text-align: center; width: 100%; }}
      button {{ flex-basis: 100%; }}
      .decision-form {{ flex-direction: column; }}
    }}
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
