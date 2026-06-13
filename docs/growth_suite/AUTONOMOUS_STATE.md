# Autonomous Growth Suite — State

> Source plan: `CLAUDE_AUTONOMOUS_GROWTH_SUITE.md`
> Restart instruction: *Read this file and continue from the next pending phase.*

## Current branch

`main` — the maintainer explicitly instructed (chat, 2026-06-13) to commit after each
phase and **push to `main`**, overriding the plan's default feature branch.
Note: pushing to `main` triggers CI (tests gate) → automatic production deploy
with a post-deploy health check (`.github/workflows/django.yml`).

## Baseline (before any phase)

- `python manage.py check` — 0 issues.
- `CELERY_TASK_ALWAYS_EAGER=True python manage.py test --parallel` — 380 tests, OK (1 skipped).

## Phase status

| Phase | Feature | Status |
|---|---|---|
| 1 | Odoo Instant Detector | **done** |
| 2 | Studio X-Ray System Map | **done** |
| 3 | Odoo Version EOL Countdown Pages | **done** |
| 4 | ERP Chaos Cost Calculator | **done** |
| 5 | Healthy System Badge | **done** |
| 6 | Odoo Arabic Glossary MVP | **done** |

## Decisions made

See `DECISION_LOG.md`.

## Risks

- Each push to `main` deploys production (existing pipeline). Mitigation: full
  test suite + `manage.py check` must pass locally before every push; CI test
  job gates the deploy job.
- Phase 1 fetches third-party public websites server-side: SSRF guarded by the
  existing `validate_target()` gate; response size and request count capped.

## Pending tasks

- Phases 2–6.

## Commands run (per phase, summarized)

- Baseline: `manage.py check`, full test suite (see above).
- Phase 1: `manage.py check` (0 issues) · `manage.py test tool_odoo_detector`
  (19 tests OK) · full suite `manage.py test --parallel` (399 tests OK,
  1 skipped) · `makemessages -l es -l ar` + filled 40 strings per language ·
  `compilemessages -l es -l ar` · AR/ES smoke render verified (RTL OK).
- Phase 2: `manage.py test tool_studio_xray` (174 OK) · full suite (410 OK,
  1 skipped) · makemessages/fill/compile (13 strings, partial renamed to
  `_system_map.html` so makemessages extracts it) · demo SVG visually
  verified.

## Phase 1 implementation mini-plan

New app `tool_odoo_detector` (registered in settings + `bidatia/urls.py` under
`tools/odoo-detector/`):

- `detector.py` — pure logic. `detect(url)` → dict: `detected`
  (yes/no/unknown), `confidence` (high/medium/low), `version` ('' if unknown),
  `hosting` (odoo_online/odoo_sh/self_hosted/unknown), `evidence` (list of
  safe signal codes), `final_domain`. Fetches at most: homepage GET,
  `/web/login` GET (only if homepage inconclusive), `/web/webclient/version_info`
  POST (only if Odoo detected). All through `validate_target()`; 6s timeout,
  256 KB response cap, no body stored.
- Signals: `web.assets_*` bundles, `/web/assets/`, `odoo.define`/`var odoo`,
  `<meta name="generator" content="Odoo">`, `data-oe-`/`oe_structure` website
  markers, `frontend_lang`/`session_id` cookies, `.odoo.com`/`.odoo.sh` host.
- View: landing GET (form) + POST (rate-limited 10/IP/h, honeypot) renders the
  result block on the same page. CTA redirect endpoints `go/xray|rescue|demo`
  that `track()` then redirect.
- Events: `odoo_detector_page_view`, `_started`, `_completed`,
  `_xray_clicked`, `_rescue_clicked`, `_demo_clicked` (tool key
  `odoo_detector`).
- Hub: add card to `TOOLS` in `tools_core/views.py`. Sitemap: add landing to
  `StaticViewSitemap`.
- i18n: EN strings in code/templates; ES/AR translations added to the .po
  catalogues and compiled.
- Tests: detector unit tests (Odoo fixture → high, non-Odoo → none/low, SSRF
  blocked, bad URL), view tests (renders EN/ES/AR, invalid URL polite error,
  rate limit, events recorded, CTA redirects).

## Phase 6 outcome

- New app `glossary` at `/​<lang>/odoo-glossary/` (+ `<slug>/` term pages,
  `<slug>/go/` tracked CTA hand-off).
- 32 terms in `glossary/data.py`, 12 categories, every term fully authored
  in BOTH Arabic (primary) and English: definition, concrete example, why
  it matters, common mistake, related links, per-term CTA (xray/rescue).
  Spanish falls back to English content with translated page chrome
  (documented MVP decision, same pattern as DB-content fallback).
- SEO: unique title/meta per term, DefinedTerm + BreadcrumbList JSON-LD,
  category-grouped index, GlossarySitemap, footer links (glossary + EOL
  pages) for internal linking.
- Events: `glossary_index_view`, `glossary_term_view` (term in metadata),
  `glossary_tool_cta_clicked`. 14 tests incl. data-integrity (30+ terms,
  AR+EN completeness, related-slug validity).

## Phase 5 outcome

- `HealthBadge` model in tools_core (migration `0005_healthbadge`): UUID id,
  run FK, tool_slug, level_code, opt-in company_name, is_active. Snapshots
  only the broad level + date, so the badge survives the 72h result wipe
  while revealing nothing else.
- Eligibility (`tools_core/services/badges.py`) reuses EXISTING semantics:
  Rescue level 'stable', X-Ray score ≤ 24 (low band). Demo/expired never
  eligible. One badge per run.
- Flow: offer card on eligible result pages (opt-in POST with optional
  company name) → public verification page `/tools/badge/<id>/` + embeddable
  `badge.svg` (cached 1 day) + copy-embed snippet. Revoke via admin action →
  page 410s and SVG 404s.
- Language: "Health Snapshot", "point-in-time", "not a certification" —
  no certified/guaranteed wording anywhere.
- Events: `healthy_badge_offered/_created/_viewed/_copied` (copied via the
  whitelisted client beacon). 17 tests incl. privacy boundaries.

## Phase 4 outcome

- New app `tool_chaos_calc` at `/​<lang>/tools/erp-chaos-cost-calculator/`.
- `calculator.py`: transparent deterministic formula (weekly_hours x cost
  x 52 + rework x cost x 12), input caps, field-coded validation errors.
  Server-side POST is the single source of truth (no JS mirror); nothing
  persisted, anonymous numbers go to ToolEvent only.
- Careful copy: "estimate / based on your inputs / not financial advice /
  conversation starter"; the formula is printed on the page.
- Events: `chaos_calculator_page_view/_completed/_rescue_clicked/
  _xray_clicked`. Hub card + sitemap entry. 14 tests. AR/ES verified.

## Phase 3 outcome

- Data module `pages/odoo_versions.py`: Odoo 14–19 with release/support-end
  dates, ALL end dates flagged estimated + shared source note (accuracy
  rule); `annotate()` computes status/countdown, past dates flip to
  "ended N days ago".
- Pages: `/​<lang>/odoo-version-support/` (index) and `/odoo-<n>/` details
  with countdown hero, what-it-means, risks, 6-step readiness checklist,
  FAQ (+FAQPage JSON-LD + breadcrumbs), cross-links, X-Ray/Rescue CTAs via
  tracked redirects. Sitemap: new `OdooVersionSitemap` + index entry.
- Events: `odoo_eol_page_view` (with version), `odoo_eol_xray_clicked`,
  `odoo_eol_rescue_clicked` (tool `odoo_eol`).
- 12 tests in `pages/tests.py` (data integrity, statuses, render EN/ES/AR,
  past-date handling, 404, events, sitemap).
- Gotcha fixed: `makemessages` fuzzy-matched 27 new strings per language to
  wrong old translations; corrective pass overwrote fuzzy entries for all
  growth-suite strings (phases 1–3) and unfuzzied them.

## Phase 2 outcome

- `tool_studio_xray/system_map.py`: pure-Python radial layout from
  result_json (model_breakdown ∪ usage rows). Node size = records/custom
  load, halo = field density, warm colors = custom/risky, faded = dead,
  threads = automations. Deterministic, ≤14 nodes, None when <3 nodes
  (section hides gracefully).
- Inline SVG section in report.html (before AI notes) with legend +
  "Open full map" / "Download SVG" + demo-only "Run this on your own Odoo"
  CTA. Standalone endpoint `report/<id>/map.svg` (404 on expired/no data).
- Events: `xray_system_map_viewed` (report render), `_opened`, `_downloaded`.
- 11 new tests in `tool_studio_xray/tests/test_system_map.py`; visual check
  of the demo map rendered via qlmanage — layout is clean and readable.

## Phase 1 outcome

- New app `tool_odoo_detector` at `/​<lang>/tools/odoo-detector/`.
- Detector logic in `tool_odoo_detector/detector.py` (SSRF-gated, max 3
  requests, redirect hops re-validated, 256 KB cap, nothing stored).
- Events: `odoo_detector_page_view/_started/_completed/_xray_clicked/
  _rescue_clicked/_demo_clicked` (tool `odoo_detector`), visible in the
  existing ToolEvent admin.
- Hub card added; hub badge logic fixed (live non-featured tools showed
  "COMING SOON" — now show "LIVE"). Sitemap now includes detector + ERP
  Rescue landing pages.
- i18n: 40 new strings translated to ES + AR, compiled.

## Next action

All six phases complete. See the final report at the end of
`MANUAL_TEST_PLAN.md` and the session summary delivered to the maintainer.
Remaining manual follow-ups: spot-check production URLs after the final
deploy, and review the glossary Arabic copy editorially.
