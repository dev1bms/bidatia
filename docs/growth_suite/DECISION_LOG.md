# Autonomous Growth Suite — Decision Log

Format: date · decision · why.

## 2026-06-13 — Work directly on `main`

The plan file defaults to `feature/growth-suite-six-phases` and forbids direct
pushes to `main` *unless the maintainer explicitly requests it*. the maintainer's kickoff message
explicitly requested commit-per-phase **pushed to `main`**. The repo's entire
recent history is direct-to-main with a CI test gate before the production
deploy job, so this matches how the project already operates. Safety: never
push without local `check` + full test suite green.

## 2026-06-13 — Phase 1 ships as a new app `tool_odoo_detector`

Follows the established "one tool = one app, depends only on tools_core"
architecture (README). The detector reuses `validate_target()` (SSRF/https
gate) from `tools_core.connectors.xmlrpc_connector` instead of duplicating
security code.

## 2026-06-13 — Phase 1 detection is synchronous (no Celery)

The check is 1–3 short HTTP GETs with tight timeouts (~6s) against a public
site. A queue would add latency and infrastructure for no benefit. Rate
limited per IP (same cache limiter as the other tools).

## 2026-06-13 — Phase 1 stores no ToolRun rows

Results are computed and rendered in one request; only `ToolEvent` analytics
rows are written (domain + result metadata, no HTML bodies). This honors the
plan's "do not store full response body / store only normalized domain and
result metadata" rule with the least data retention.

## 2026-06-13 — Version probe uses `/web/webclient/version_info` only

It is the same public, unauthenticated JSON-RPC family as the existing
`/web/database/list` discovery probe. No port scanning, no login attempts, no
private endpoints. If it fails or is disabled, the tool reports
version "unknown" — never an error.

## 2026-06-13 — Phase 2 map is computed server-side, template stays logic-free

`system_map.py` precomputes every coordinate/color/size; the template only
paints attributes. No JS, no graph library, deterministic output (stable for
screenshots/tests). Map partial lives in `_system_map.html` (not `.svg`)
because `makemessages` only extracts from .html/.txt/.py — the standalone
endpoint sets `image/svg+xml` explicitly.

## 2026-06-13 — Map events are server-side only

`xray_system_map_viewed` fires on report render (with a demo flag),
`_opened`/`_downloaded` fire from the map.svg endpoint. No client beacons —
the plan asked not to overcomplicate fragile event capture.

## 2026-06-13 — Phase 3 EOL pages live in the `pages` app, data in code

No CMS model: the version table changes once a year, so a reviewed Python
data module (`pages/odoo_versions.py`) beats a DB model + admin + migration.
Every support-end date carries `support_end_estimated=True` and the shared
source note — templates must always say "estimated/planning horizon"
(enforced by a data-integrity test).

## 2026-06-13 — Translation catalogs: never trust fuzzy

`makemessages` fuzzy-matched 27 new msgids per language to unrelated old
translations (e.g. the EOL FAQ question got an old hub string). Fuzzy
entries are skipped by compilemessages, so pages silently fell back to
English. Rule for future phases: after filling translations, sweep all new
msgids for fuzzy flags and overwrite them.

## 2026-06-13 — Phase 4 calculator computes server-side only

One source of truth for the formula (testable pure Python in
`calculator.py`), events stay server-side, page works without JS. A live
JS mirror would duplicate the formula for marginal UX gain — skipped per
"no backend complexity unless needed" read in reverse: no frontend
complexity either. Inputs are capped so nonsense numbers can't produce
absurd screenshots under the BidERP name.

## 2026-06-13 — Phase 5 badge is a tools_core model, snapshotted at creation

Badges span two tools, so the model lives in shared infra (tools_core), not
a tool app. The badge row stores ONLY tool type + broad level code + opt-in
company name + date — snapshotted at the explicit opt-in POST — so it stays
verifiable after the 72h result wipe without retaining anything sensitive.
Revocation is an admin action (page → 410, SVG → 404); a self-service
revoke link was skipped because the result link itself expires in 72h.

## 2026-06-13 — Badge wording bans certification language

Public copy says "Health Snapshot", "point-in-time result", "not a security
certification, not an audit, not a guarantee". A test asserts the
verification page carries the disclaimer.

## 2026-06-13 — Phase 6 glossary content lives in code, not .po catalogs

The glossary is Arabic-FIRST editorial content, not a translation of UI
strings: each term carries authored 'ar' and 'en' fields in
glossary/data.py. Spanish falls back to English content (with translated
page chrome) — the same fallback pattern the site already uses for
DB-driven content. Going through gettext would have inverted the
authorship (English-first) and bloated the catalogs with ~300 long
editorial strings.

## 2026-06-13 — Glossary MVP ships 32 terms

Within the plan's 30–50 window. Every term has all five content fields in
both languages, enforced by a data-integrity test, so partial entries
cannot ship silently.

## 2026-06-13 — System Map v2: clarity pass + locale bug fix

User feedback: the map was unclear, especially on the demo. Changes:
(a) ROOT CAUSE found for "unclear" on AR/ES pages: Django locale number
formatting rewrote SVG coordinates (400.0 → "400٫0"/"400,0"), scrambling
the entire drawing on Arabic/Spanish reports. Fixed with {% localize off %}
around the SVG + a regression test that float-parses every numeric
attribute under en/es/ar. (b) Readability: bigger labels with white text
halos, a stat line under every node (records / custom fields / automations,
pluralized via ngettext incl. the 6 Arabic plural forms), captioned rings
(Core/Standard/Custom at staggered angles), automations fan out as one
thread per automation (capped at 4) instead of one ambiguous line, larger
canvas, and horizontal scroll on phones instead of shrinking the SVG.
No letter-spacing in SVG text — it cuts Arabic cursive joining.

## 2026-06-13 — Data Risk Profiler (new tool, by explicit request)

The original growth plan excluded this tool; the maintainer explicitly commissioned
it afterwards with a full spec. Key decisions: reuses the X-Ray async
pattern (ToolRun + Celery + progress polling) and the whitelisted read-only
connector; duplicate detection runs on bounded samples (read_group has no
limit parameter — unbounded group-bys on email cardinality are unsafe);
v1 ships with NO AI layer (deterministic board text instead — documented in
docs/data_risk_profiler/HEURISTICS.md); email is optional, consent required
only when an email is given; stored payload is analyzer output only
(counts + masked examples), never raw collected data.
