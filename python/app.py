"""The owner's page for payment reminders."""

import os
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from plan import build_plan, parse_iso_date, read_json

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
        plan = build_plan(invoices, sent, TODAY)
        today_date = parse_iso_date(TODAY)
        plan["paid_invoices"] = sorted(
            [
                {
                    "invoice_id": invoice.get("id", ""),
                    "customer": invoice.get("customer", "Customer"),
                    "amount": invoice.get("amount", ""),
                    "currency": invoice.get("currency", ""),
                    "paid_date": invoice.get("paid_date"),
                }
                for invoice in invoices
                if isinstance(invoice, dict)
                and today_date is not None
                and parse_iso_date(invoice.get("paid_date")) is not None
                and parse_iso_date(invoice.get("paid_date")) <= today_date
            ],
            key=lambda item: item["invoice_id"],
        )
        return plan, None
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
    elif not plan or (not plan["actions"] and not plan["skipped"] and not plan.get("paid_invoices")):
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

            if action["needs_approval"]:
                form = (
                    "<form method='post' action='/decision' class='decision-form'>"
                    f"<input type='hidden' name='invoice_id' value='{escape(invoice_id, quote=True)}'>"
                    f"<input type='hidden' name='step' value='{escape(action['step'], quote=True)}'>"
                    "<button type='submit' name='decision' value='approved' class='approve'>Approve reminder</button>"
                    "<button type='submit' name='decision' value='rejected' class='reject'>Reject reminder</button>"
                    "</form>"
                )
            else:
                form = "<div class='auto-note'><span class='check-mark'>OK</span> Ready to send without approval</div>"
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

        paid_rows = []
        for item in plan.get("paid_invoices", []):
            amount = item["amount"]
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                amount_text = f"{item['currency']} {amount:,.2f}"
            else:
                amount_text = str(amount)
            paid_rows.append(
                f"<li class='paid-row'><div><strong>{escape(item['invoice_id'])}</strong><span>{escape(item['customer'])}</span></div>"
                f"<div><strong>{escape(amount_text)}</strong><span>Paid {escape(item['paid_date'])}</span></div></li>"
            )

        summary = (
            "<div class='summary-grid'>"
            f"<div class='summary-box'><span>Open reminders</span><strong>{len(plan['actions'])}</strong></div>"
            f"<div class='summary-box warning'><span>Need approval</span><strong>{approval_count}</strong></div>"
            f"<div class='summary-box muted'><span>Skipped</span><strong>{len(plan['skipped'])}</strong></div>"
            f"<div class='summary-box paid-summary'><span>Paid invoices</span><strong>{len(plan.get('paid_invoices', []))}</strong></div>"
            "</div>"
        )

        content = (
            "<div class='page-shell'>"
            "<header class='topbar'>"
            "<div><p class='eyebrow'>Payment reminder board</p><h1>Today’s actions</h1></div>"
            f"<div class='date-pill'>{escape(TODAY)}</div>"
            "</header>"
            "<div class='hero-strip'><div><span class='section-label'>Daily queue</span><p>Review the reminders that need your attention before they go out.</p></div><div class='sync-status'><span class='sync-dot'></span>Data loaded</div></div>"
            f"{summary}"
            f"<section class='panel'><div class='panel-heading'><h2>Reminder queue</h2><span>{len(plan['actions'])} item(s)</span></div>{''.join(action_rows) if action_rows else '<p>Nothing to do today.</p>'}</section>"
            f"<section class='panel'><div class='panel-heading'><h2>Data checks</h2><span>{len(plan['skipped'])} skipped</span></div><ul class='skipped-list'>{''.join(skipped_rows) if skipped_rows else '<li>All invoice records look good.</li>'}</ul></section>"
            f"<section class='panel'><div class='panel-heading'><h2>Paid invoices</h2><span>Completed records</span></div><ul class='paid-list'>{''.join(paid_rows) if paid_rows else '<li class=\'paid-empty\'>No paid invoices recorded.</li>'}</ul></section>"
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
            --bg: #edf1f4;
      --panel: #ffffff;
            --panel-alt: #f4f7f8;
            --ink: #162630;
            --muted: #687982;
            --line: #d7e0e2;
            --navy: #173642;
            --primary: #d95f48;
            --friendly: #2b806d;
            --firm: #c87828;
            --final: #c94a4a;
            --approved: #dcefe8;
            --rejected: #f5dddd;
            --warning: #fff0d9;
    }}
    * {{ box-sizing: border-box; }}
    body {{
            margin: 0; font-family: "Segoe UI", sans-serif; background-color: var(--bg);
            background-image: linear-gradient(rgba(23,54,66,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(23,54,66,.035) 1px, transparent 1px);
            background-size: 32px 32px; color: var(--ink); padding: 1.5rem;
    }}
        .page-shell {{ max-width: 1120px; margin: 0 auto; }}
    .topbar {{
            display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem;
            margin-bottom: 1.35rem; padding: .35rem 0 0;
    }}
        .eyebrow {{ margin: 0 0 .45rem; font-size: .68rem; letter-spacing: .16em; text-transform: uppercase; color: var(--primary); font-weight: 800; }}
        h1 {{ margin: 0; color: var(--navy); font-family: Georgia, serif; font-size: clamp(2.1rem, 4vw, 3.6rem); font-weight: 400; letter-spacing: 0; }}
        h2 {{ margin: 0 0 .75rem; color: var(--navy); font-size: 1.1rem; }}
        .date-label {{ display: block; color: var(--muted); font-size: .68rem; letter-spacing: .1em; text-transform: uppercase; margin-bottom: .25rem; }}
    .date-pill {{
            background: var(--navy); color: #fff; border-radius: 8px; padding: .75rem 1rem;
            font-weight: 700; white-space: nowrap; box-shadow: 0 8px 18px rgba(23,54,66,.16);
    }}
        .hero-strip {{ display: flex; justify-content: space-between; align-items: center; gap: 1rem; background: var(--navy); color: #fff; border-radius: 12px; padding: 1.2rem 1.35rem; margin-bottom: 1rem; box-shadow: 0 12px 24px rgba(23,54,66,.14); }}
        .hero-strip p {{ margin: .25rem 0 0; color: #c8d8da; font-size: .92rem; }}
        .section-label {{ color: #f4aa8f; font-size: .68rem; font-weight: 800; letter-spacing: .15em; text-transform: uppercase; }}
        .sync-status {{ display: flex; align-items: center; gap: .45rem; color: #d4e4e3; font-size: .78rem; white-space: nowrap; }}
        .sync-dot {{ width: .5rem; height: .5rem; border-radius: 50%; background: #73c5a9; box-shadow: 0 0 0 4px rgba(115,197,169,.16); }}
    .summary-grid {{
            display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .8rem; margin-bottom: 1.8rem;
    }}
    .summary-box {{
            background: rgba(255,255,255,.82); border: 1px solid var(--line); border-radius: 10px; padding: 1rem 1.1rem;
            box-shadow: 0 6px 16px rgba(23,54,66,.06);
    }}
    .summary-box.warning {{ background: var(--warning); }}
        .summary-box.muted {{ background: rgba(255,255,255,.62); }}
    .summary-box.paid-summary {{ background: var(--approved); }}
        .summary-box span {{ display: block; color: var(--muted); font-size: .68rem; text-transform: uppercase; letter-spacing: .1em; font-weight: 800; }}
        .summary-box strong {{ display: block; margin-top: .3rem; color: var(--navy); font-size: 2.1rem; font-weight: 500; }}
        .panel {{ background: transparent; margin-bottom: 1.7rem; }}
        .panel-heading {{ display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; border-bottom: 1px solid var(--line); padding-bottom: .65rem; margin-bottom: .8rem; }}
        .panel-heading h2 {{ margin: 0; }}
        .panel-heading span {{ color: var(--muted); font-size: .78rem; }}
    .card {{
            background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
            padding: 1.15rem; margin-bottom: .75rem; box-shadow: 0 7px 20px rgba(23,54,66,.055);
    }}
        .card-head {{ display: flex; justify-content: space-between; align-items: center; gap: .75rem; margin-bottom: .9rem; }}
        .card-head h2 {{ margin: 0; color: var(--navy); font-family: Georgia, serif; font-size: 1.35rem; font-weight: 400; }}
    .tag {{
            display: inline-block; border-radius: 5px; padding: .3rem .6rem; font-size: .66rem; font-weight: bold;
      text-transform: uppercase; color: white;
    }}
    .tag.friendly {{ background: var(--friendly); }}
    .tag.firm {{ background: var(--firm); }}
    .tag.final {{ background: var(--final); }}
    .meta-grid {{
            display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: .8rem; margin-bottom: .9rem;
    }}
    .meta-grid div {{ display: flex; flex-direction: column; gap: .2rem; }}
    .meta-grid strong {{ color: var(--muted); font-size: .76rem; text-transform: uppercase; letter-spacing: .04em; }}
    .message {{ margin: .5rem 0 1rem; padding: .85rem .9rem; background: var(--panel-alt); border-left: 3px solid var(--primary); line-height: 1.5; color: #30434b; }}
    .status {{ display: inline-block; padding: .24rem .65rem; border-radius: 5px; background: #ecf0f4; color: var(--ink); font-weight: 700; font-size: .82rem; }}
    .status.approved {{ background: var(--approved); color: #1d5e2d; }}
    .status.rejected {{ background: var(--rejected); color: #7d1f1f; }}
        .decision-form {{ display: flex; gap: .6rem; flex-wrap: wrap; margin-top: .25rem; }}
    button {{
            flex: 1 1 150px; background: var(--primary); color: white; border: none; border-radius: 6px;
      padding: .85rem 1rem; font-size: .96rem; font-weight: bold; cursor: pointer;
    }}
    button:hover {{ filter: brightness(0.97); }}
    button.reject {{ background: #6c757d; }}
        .auto-note {{ color: var(--friendly); font-size: .85rem; font-weight: 700; padding-top: .35rem; }}
        .check-mark {{ display: inline-grid; place-items: center; width: 1.35rem; height: 1.35rem; margin-right: .35rem; border-radius: 50%; background: var(--approved); font-size: .62rem; }}
        .skipped-list {{ padding-left: 1.2rem; margin: 0; line-height: 1.7; color: var(--muted); }}
        .paid-list {{ display: grid; gap: .55rem; padding: 0; margin: 0; list-style: none; }}
        .paid-row {{ display: flex; justify-content: space-between; align-items: center; gap: 1rem; background: rgba(255,255,255,.72); border: 1px solid var(--line); border-radius: 8px; padding: .8rem 1rem; }}
        .paid-row div {{ display: flex; flex-direction: column; gap: .15rem; }}
        .paid-row div:last-child {{ align-items: flex-end; }}
        .paid-row strong {{ color: var(--navy); font-size: .88rem; }}
        .paid-row span {{ color: var(--muted); font-size: .78rem; }}
        .paid-empty {{ color: var(--muted); list-style: none; }}
    .error {{ color: #8b1e1e; font-weight: bold; }}
        .empty-panel, .error-panel {{ background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 1.3rem; box-shadow: 0 7px 20px rgba(23,54,66,.055); }}
    @media (max-width: 390px) {{
            body {{ padding: .8rem; }}
      .summary-grid {{ grid-template-columns: 1fr; }}
      .meta-grid {{ grid-template-columns: 1fr; }}
      .topbar {{ align-items: flex-start; flex-direction: column; }}
      .date-pill {{ align-self: stretch; text-align: center; width: 100%; }}
            .hero-strip {{ align-items: flex-start; flex-direction: column; }}
            .paid-row {{ align-items: flex-start; flex-direction: column; }}
            .paid-row div:last-child {{ align-items: flex-start; }}
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
