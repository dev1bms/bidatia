# Autonomous Growth Suite — Manual Test Plan

Quick human checks per phase after deploy. All URLs relative to
https://bidatia.xyz (or http://127.0.0.1:8000 locally). Check each in
`/en/`, `/es/` and `/ar/` (Arabic must render RTL).

## Phase 1 — Odoo Instant Detector

1. Open `/en/tools/odoo-detector/` — headline, URL input, "Detect Odoo" button.
2. Submit an empty / invalid URL (`not a url`) → polite inline error, no crash.
3. Submit `http://127.0.0.1` or `http://localhost` → blocked with a friendly
   message (SSRF gate), never a server error.
4. Submit a real Odoo site (e.g. `https://www.odoo.com`) → "appears to use
   Odoo", confidence shown, evidence list, hosting guess, disclaimer visible.
5. Submit a clearly non-Odoo site (e.g. `https://www.wikipedia.org`) →
   "no Odoo signals found" + ERP Rescue Check CTA.
6. Click each CTA (X-Ray / Rescue / demo report) → lands on the right page.
7. Admin → Tool events: `odoo_detector_*` rows exist with domain metadata.
8. `/tools/` hub shows the new card and it links to the tool.

## Phase 2 — Studio X-Ray System Map

0. Re-check the map on /ar/ and /es/ demo reports — coordinates must render (locale bug fixed); node stat lines and ring captions translated.
1. Open the demo report (`/en/tools/studio-xray/demo/`) → "Your Odoo
   Customization Map" section shows a radial SVG: dark "Odoo 16.0" core,
   amber core models, rose custom models (record counts under the heavy
   ones), faded empty models, an orange automation thread, legend below.
2. "Open full map" opens the bare SVG in a new tab; "Download SVG" saves
   `bidatia-odoo-system-map.svg`.
3. Demo map shows the "Run this on your own Odoo" CTA (real reports don't).
4. Print preview of the report → map prints, open/download buttons hidden.
5. Mobile width → SVG scales down without horizontal scroll.
6. Admin → Tool events: `xray_system_map_viewed/_opened/_downloaded` rows.
7. ES/AR report pages show translated section title/legend.

## Phase 3 — Odoo Version EOL Pages

1. `/en/odoo-version-support/` lists Odoo 14–19 with status badges
   (MAINTAINED / ENDING SOON / WINDOW CLOSED) and day counts.
2. `/en/odoo-version-support/odoo-17/` shows a countdown hero; every date
   is phrased "estimated" / "planning horizon".
3. `/en/odoo-version-support/odoo-14/` (past EOL) shows "days since the
   estimated end of support" — no negative numbers, no errors.
4. `/en/odoo-version-support/odoo-99/` → 404.
5. CTA buttons land on Studio X-Ray / Rescue Check; admin shows
   `odoo_eol_*` events with the version in metadata.
6. View-source: FAQPage + BreadcrumbList JSON-LD present; sitemap.xml
   contains the index + six version URLs.
7. AR pages render RTL with Arabic countdown labels.

## Phase 4 — ERP Chaos Cost Calculator

1. `/en/tools/erp-chaos-cost-calculator/`: enter 10 employees x 4h x 35 →
   weekly 1,400 / yearly 72,800 with the chosen currency symbol.
2. Enter a total weekly hours value → it overrides the per-employee pair.
3. Bad input ("banana" as cost) → polite field-specific error, no crash.
4. Result block shows the formula verbatim and the "estimate, not
   financial advice" line.
5. CTAs land on Rescue Check / Studio X-Ray; `chaos_calculator_*` events
   in admin carry yearly_cost + currency only (no personal data).
6. AR page renders RTL; numbers stay LTR.

## Phase 5 — Healthy System Badge

1. Complete an ERP Rescue Check with healthy answers (level "Stable") →
   result page shows the green "Health Snapshot badge" offer card.
2. Submit with a company name → lands on the public badge page with the
   level, tool, date, company and "not a security certification" line.
3. The embed code copies; pasting it elsewhere shows the SVG badge that
   links back to the verification page.
4. A risky result (high score) shows NO badge offer; the demo X-Ray report
   shows NO offer.
5. Admin → Health badges → revoke → public page shows "disabled" (no
   details), badge.svg returns 404.
6. Events `healthy_badge_offered/created/viewed/copied` appear in admin.

## Phase 6 — Odoo Arabic Glossary

1. `/ar/odoo-glossary/` shows 32 term cards grouped in categories, RTL,
   with natural Arabic (not machine-like) — editorial spot-check welcome.
2. `/ar/odoo-glossary/odoo-studio/` shows definition/example/why/mistake
   in Arabic + related-term chips + X-Ray CTA.
3. `/en/...` shows the English content; `/es/...` shows English content
   with Spanish page chrome (documented fallback).
4. Unknown slug → 404. CTA `…/go/` lands on the right tool per term.
5. View-source on a term page: DefinedTerm + BreadcrumbList JSON-LD.
6. sitemap.xml contains the glossary index + 32 term URLs; footer links
   to the glossary and the version-support pages.
7. Admin shows `glossary_*` events with the term slug in metadata.

## Founder reports (daily / weekly / monthly)

Shell test (console email backend in dev — emails print to the terminal):

```python
from tools_core.tasks import (send_founder_daily_report,
                              send_founder_monthly_report,
                              send_founder_weekly_summary)
send_founder_daily_report()      # → 'sent'
send_founder_daily_report()      # → 'skipped'  (dedup, same day)
send_founder_daily_report(force=True)   # → 'sent' (manual re-send)
send_founder_monthly_report()    # → 'sent' (previous calendar month)
send_founder_weekly_summary()    # unchanged behavior
```

Then verify:
1. The email arrives (production) / prints (dev) with summary rows,
   latest runs, highest-risk results, failed-run reasons and admin links.
2. Admin → Email logs: categories `founder_daily` / `founder_monthly`
   with `metadata.period` keys (`founder_daily_summary:YYYY-MM-DD`,
   `founder_monthly_summary:YYYY-MM`).
3. Running the task twice for the same period sends nothing new.
4. After deploy: `systemctl restart bidatia-celery-beat` picks up the two
   new schedules (06:30 UTC daily; 07:00 UTC on the 1st monthly).
