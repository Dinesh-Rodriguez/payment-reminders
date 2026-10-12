# Payment reminder assistant

This Python workflow reviews overdue invoices, creates reminder actions, and provides
an owner dashboard using the same rules engine.

## Run tests
`cd python` then `python -m unittest`

## Run the command
`cd python` then `python plan.py --invoices ../data/invoices.json --sent ../data/sent.json --today 2026-10-12 --out ../actions.json`

## Run the page
`cd python` then `python app.py`, then open `http://localhost:8000/`.

## Decisions made
- Keep the rules separate from the page and use the same engine in both places.
- Schedule only the highest overdue reminder not already sent.
- Require approval for `firm` and `final`; decisions remain in memory while the app runs.
- Show readable skip reasons and clear empty/error states on mobile and desktop.

## With more time
I would add persistent approval storage and more validation for malformed invoice files.

