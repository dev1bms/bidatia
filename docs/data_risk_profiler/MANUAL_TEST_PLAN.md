# Data Risk Profiler — Manual Test Plan

URLs relative to https://bidatia.xyz (locally: http://127.0.0.1:8000 with
`CELERY_TASK_ALWAYS_EAGER=True` or a running worker). Check `/en/`, `/es/`,
`/ar/` (Arabic RTL).

## Landing & form

1. `/en/tools/data-risk-profiler/` renders: privacy promise ("signals and
   counts, not your business documents"), what-we-check / what-we-don't
   lists, connection form.
2. Submit empty form → field errors, no crash.
3. URL `http://localhost` / private address → polite connector error (SSRF
   gate), never a traceback.
4. Email left empty → scan still allowed (email optional); with email,
   consent checkbox required.

## Scan & report (against your own test Odoo)

5. Run with a read-only API key → progress page polls; statuses advance
   connecting → collecting → analyzing → done.
6. Report shows: score 0–100 with band label, top blockers, 8 category
   cards (or fewer with "skipped" notes), duplicate clusters with MASKED
   examples only (spot-check: no full email/VAT visible anywhere),
   cleanup plan in 3 stages, management questions, CTAs (booking,
   Studio X-Ray, Rescue Check), 72h deletion notice.
7. Wrong API key → failed run with friendly message on progress page.
8. Verify in Odoo logs/audit: only read calls (search_count/search_read/
   read_group/fields_get), zero writes.

## Demo

9. `/en/tools/data-risk-profiler/demo/` opens a DEMO-badged report with
   realistic synthetic numbers, no credentials, never expires.

## Events & email & admin

10. Admin → Tool events: `data_risk_page_view/_started/_completed/
    _report_opened/_demo_opened` and CTA click events.
11. With email provided: "report ready" email arrives, EmailLog row exists.
12. Admin → Tool runs: the run row shows status/result_json (masked only).
13. Score ≥ 70 on a real run → hot-lead email to the founder inbox.

## i18n

14. All three languages render; Arabic RTL; technical tokens (model names,
    URLs) stay LTR.

## v1.1 + v2 additions

15. Expiry reminder: create a done DRP run expiring within 24h (or wait) →
    one "expires tomorrow" email, EmailLog `report_expiry_reminder`,
    `data_risk_expiry_reminder_sent` event; a second beat run sends nothing.
16. Report → "Send this report to my manager": valid email → success note,
    EmailLog `report_to_manager`, event `data_risk_report_sent_to_manager`;
    the email shows level + blockers, never masked examples.
17. A scan with band `low` shows the Health Snapshot badge offer; the badge
    page reads "Low data migration risk" + "Data Risk Profiler".
18. Landing: tick "Save an anonymous aggregated snapshot…" → scan → admin
    has a DataRiskSnapshot row with scores/counts only. Re-scan the same
    URL/db → report shows "Progress since your last scan" with deltas.
19. Report shows the radar "Data Quality Map" (check /ar/ and /es/ — the
    shape must render identically; coordinates are locale-proof).
20. Cleanup plan items now carry priority/owner chips and why/impact lines.
21. With TOOLS_AI_MODEL set: the "AI advisor notes" card appears after the
    scan; kill Ollama and re-scan → report ships without the card and
    `data_risk_ai_advisor_failed` is tracked.
22. Categories note states duplicate sample coverage (% or "full coverage").
