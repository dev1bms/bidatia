# Claude Autonomous Growth Suite Plan — BidERP Tools

> Purpose: Give Claude Code a safe, self-managed roadmap to build the next six growth features for BidERP Tools with minimal interruption from the maintainer.
>
> Default target branch: `feature/growth-suite-six-phases`
>
> Important: Claude may work autonomously, make normal engineering decisions, commit after each milestone, and push to the feature branch. Claude must **not push directly to `main`** or deploy production unless the maintainer explicitly requests it.

---

## 0. Mission

Build the next six “outside-the-box” growth features for BidERP Tools, with high quality, tests, analytics events, i18n, admin visibility where useful, and safe privacy/security boundaries.

The six phases are:

1. **Odoo Instant Detector** — public micro-tool that detects whether a public website appears to run Odoo.
2. **System Map** — visual SVG map inside Studio X-Ray reports and demo report.
3. **Odoo Version End-of-Life Countdown Pages** — evergreen SEO pages for Odoo version support timelines.
4. **ERP Chaos Cost Calculator** — lightweight calculator showing estimated yearly cost of manual ERP chaos.
5. **Healthy System Badge** — optional embeddable/public verification badge for excellent results.
6. **Odoo Arabic Glossary** — SEO glossary for Odoo/ERP terms, starting with a strong MVP, not all 300 terms at once.

This is a growth suite, not a rewrite. Reuse existing BidERP patterns: tools, ToolRun, ToolEvent, EmailLog/unified email, translations, admin, Celery only when needed, rate limits, privacy copy, and existing design language.

---

## 1. Autonomy Rules

Claude should work like an autonomous senior engineer.

### Claude may decide without asking

- File organization inside existing app patterns.
- Naming of helper functions/classes.
- Small UX copy improvements.
- Whether a phase needs a new Django app or can live in an existing app.
- Whether a lightweight model/migration is justified.
- SVG/layout implementation details.
- Test structure and coverage strategy.
- Reasonable fallback behavior when data is incomplete.
- Minor refactors required to avoid duplication.

### Claude must stop and ask only if

- Credentials/secrets are required.
- A destructive migration or possible data loss is involved.
- A production action is required.
- The requested feature creates legal/privacy/security risk beyond normal public website fetching.
- A new heavy dependency is required.
- The current architecture conflicts with the requested behavior.
- A decision would change business positioning or pricing.
- Pushing to `main` or deploying production is required.

### Claude must not do

- Do not push directly to `main`.
- Do not deploy production.
- Do not perform port scanning, security scanning, brute force, credential testing, or aggressive crawling.
- Do not store sensitive data unnecessarily.
- Do not expose internal sales signals to users.
- Do not change existing scoring logic unless explicitly required.
- Do not build Migration Readiness Scanner or Data Risk Profiler in this plan.
- Do not add PDF generation or heavy rendering dependencies unless clearly justified and approved.
- Do not create exaggerated claims like “certified secure” or “guaranteed healthy.”

---

## 2. Initial Setup Procedure

Before editing anything:

```bash
git status
git fetch origin
git checkout main
git pull --ff-only origin main
git checkout -b feature/growth-suite-six-phases
```

Then read the relevant architecture:

- `README*` if present.
- Django settings and URLs.
- `tools_core/`
- `tool_studio_xray/`
- `tool_erp_rescue/`
- existing templates for tools hub, reports, result pages.
- existing services for analytics/events/email.
- existing tests.
- existing translation approach.
- existing static/OG image generation approach.

Create/update this state file:

```text
docs/growth_suite/AUTONOMOUS_STATE.md
```

It must contain:

- current branch
- phase status
- decisions made
- risks
- pending tasks
- commands run
- tests run
- next action

Also create:

```text
docs/growth_suite/DECISION_LOG.md
docs/growth_suite/MANUAL_TEST_PLAN.md
```

Commit these planning docs first only if they are useful and clean:

```bash
git add docs/growth_suite/
git commit -m "Add autonomous growth suite plan state"
git push -u origin feature/growth-suite-six-phases
```

If docs already exist, update them instead.

---

## 3. Work Loop Per Phase

For each phase, use this cycle:

1. Inspect existing code.
2. Write a small implementation plan in `AUTONOMOUS_STATE.md`.
3. Implement the feature.
4. Add/adjust tests.
5. Add i18n strings for EN/ES/AR where user-facing.
6. Add ToolEvent tracking where relevant.
7. Add admin visibility where useful.
8. Run targeted tests.
9. Run full relevant test suite.
10. Run Django checks.
11. Update `AUTONOMOUS_STATE.md`, `DECISION_LOG.md`, and `MANUAL_TEST_PLAN.md`.
12. Commit the phase.
13. Push the feature branch.
14. Continue to the next phase.

### Required command set after each phase

Use the actual project commands if different, but normally:

```bash
python manage.py check
python manage.py test
python manage.py compilemessages
```

If migrations were added:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
```

Before commit:

```bash
git status
git diff --check
```

Commit style:

```bash
git add <changed files>
git commit -m "Add <phase feature>"
git push origin feature/growth-suite-six-phases
```

---

## 4. Self-Healing Policy

If a test fails:

1. Identify whether the failure is caused by current changes.
2. Fix if related.
3. Re-run targeted tests.
4. Re-run full test suite.
5. Repeat up to 3 focused repair cycles.
6. If still failing, document clearly in `AUTONOMOUS_STATE.md`:
   - failing command
   - error
   - what was tried
   - likely cause
   - safest next step
7. Stop only if continuing risks corrupting architecture or data.

If unrelated existing tests fail, document them and continue only if safe.

If context window becomes large, update `AUTONOMOUS_STATE.md` before continuing. If the session becomes too long or unstable, stop after pushing the branch and provide a restart instruction:

```text
Read docs/growth_suite/AUTONOMOUS_STATE.md and continue from the next pending phase.
```

---

## 5. Global Quality Requirements

Every phase should preserve this standard:

- Works in EN/ES/AR.
- Mobile-friendly.
- No broken pages if optional data is missing.
- Safe failure paths.
- No heavy dependency without approval.
- No production secrets.
- No invasive scanning.
- ToolEvent analytics for major funnel actions.
- Admin visibility for useful operational signals.
- Clear CTAs to:
  - Studio X-Ray
  - ERP Rescue Check
  - Booking
  - Demo Report
- Tests for:
  - happy path
  - invalid input
  - rate/security edge case where relevant
  - template renders
  - events/logging where relevant
- Does not slow down existing tools noticeably.
- Does not change existing score formulas unless explicitly part of phase.

---

# Phase 1 — Odoo Instant Detector

## Goal

Build a public micro-tool where a visitor enters a public website URL and BidERP tells them whether the site **appears to be powered by Odoo**, with confidence and safe evidence.

This is a traffic-entry tool: fast, safe, curious, shareable.

## UX

Page route suggestion:

```text
/en/tools/odoo-detector/
```

Localized routes should follow the existing i18n pattern.

Page content:

- Short headline:
  - EN: “Is this website running on Odoo?”
  - AR: “هل هذا الموقع يعمل على Odoo؟”
  - ES: “¿Este sitio funciona con Odoo?”
- URL input.
- Button: Detect Odoo.
- Result block:
  - appears to use Odoo: yes/no/unknown
  - confidence: high/medium/low
  - possible version if safely detected
  - hosting guess: Odoo Online / Odoo.sh / self-hosted / unknown
  - safe evidence list
  - disclaimer: “This is a best-effort public signal check, not a security scan.”
- CTA:
  - If likely Odoo: Run Studio X-Ray / View demo report.
  - If not detected: Try ERP Rescue Check.

## Security Rules

- Only fetch public HTTP/HTTPS resources.
- No port scanning.
- No crawling beyond strict small limit.
- No login attempts.
- No private endpoints.
- Short timeout.
- Respect redirects reasonably.
- Normalize/sanitize URL input.
- Prevent SSRF:
  - block localhost/private IP ranges
  - block file:// and non-http schemes
  - block internal hostnames
- Rate limit.
- Do not store full response body.
- Store only normalized URL/domain and result metadata if needed.

## Detection Signals

Use existing discovery/version detection code if safe.

Possible safe signals:

- Odoo-specific assets in HTML.
- `web.assets_*`
- Odoo public paths if already used safely by existing code.
- generator/meta hints.
- public script/style names.
- safe version indicators if already available.
- hosting hints from headers/domains, without overclaiming.

Always phrase as “appears to be,” not certainty.

## Tracking Events

Add ToolEvent events:

- `odoo_detector_page_view`
- `odoo_detector_started`
- `odoo_detector_completed`
- `odoo_detector_xray_clicked`
- `odoo_detector_rescue_clicked`
- `odoo_detector_demo_clicked`

## Acceptance Criteria

- Tool page renders in EN/ES/AR.
- Invalid URLs fail politely.
- Private/internal URLs are blocked.
- Safe public URL returns a result.
- Odoo-like fixture/mocked response returns high confidence.
- Non-Odoo fixture/mocked response returns low/no confidence.
- Events are recorded.
- CTA paths work.
- Tests pass.

## Expected Result

BidERP gains a low-friction tool that brings cold visitors into the tools funnel without asking for credentials.

---

# Phase 2 — Studio X-Ray System Map

## Goal

Add a memorable visual “System Map” to Studio X-Ray report v3 and demo report.

This should make the report visually unforgettable and screenshot-worthy.

## Concept

Use existing X-Ray report data to produce an SVG/map:

- models = nodes
- custom fields = density/halo/rings
- automations/server actions = lines/threads
- risky/high-impact items = warm colors or warning markers
- high-usage models = larger nodes
- unused/empty models = faded nodes
- central/core models = positioned near center
- “spaghetti” effect should be controlled and elegant, not messy enough to hurt readability

## Implementation Rules

- Prefer server-side/template-generated SVG.
- No heavy graph dependency unless already present.
- No AI dependency.
- No score changes.
- Must work in demo report.
- Must have graceful fallback if data is insufficient.
- Must avoid displaying source code or sensitive details.
- Make it printable and screenshot-friendly.

## UX

Add a report section titled:

- EN: “Your Odoo Customization Map”
- AR: “خريطة تخصيصات Odoo لديك”
- ES: “Mapa de personalizaciones de Odoo”

Include:

- short explanation
- SVG map
- legend
- optional “Open full map” or “Download SVG” only if simple and safe
- CTA under demo map: “Run this on your own Odoo”

## Tracking Events

- `xray_system_map_viewed` if practical server-side or beacon-based
- `xray_system_map_opened`
- `xray_system_map_downloaded`

Do not overcomplicate if event capture would be fragile.

## Acceptance Criteria

- Demo report includes strong visual map.
- Real reports include map when enough data exists.
- Fallback works.
- No heavy dependency.
- Report tests updated.
- Visual works on mobile and desktop.
- Print/browser save still acceptable.

## Expected Result

Studio X-Ray gets a unique “wow” asset that can be used in LinkedIn screenshots and sales calls.

---

# Phase 3 — Odoo Version End-of-Life Countdown Pages

## Goal

Create evergreen SEO pages for Odoo version support/readiness, with countdowns and CTAs.

These pages should attract search traffic from people researching Odoo upgrades.

## Important Accuracy Rule

Do not hardcode uncertain claims in templates. Put version data in a clear config file or Python data structure:

```text
odoo_versions.yml / odoo_versions.py / data module
```

Each entry should include:

- version
- release date if known
- support/end date if known or estimated
- confidence/source_note field
- status label
- CTA
- page slug

If dates are uncertain, say “estimated” or “planning horizon,” not absolute.

## Pages

Suggested URLs:

```text
/en/odoo-version-support/odoo-15/
/en/odoo-version-support/odoo-16/
...
```

Support EN/ES/AR.

Content sections:

- Countdown/status hero.
- What this means.
- Risks of waiting.
- Upgrade readiness checklist.
- CTA to Studio X-Ray and ERP Rescue Check.
- FAQ schema if project already uses structured data.

## Tracking Events

- `odoo_eol_page_view`
- `odoo_eol_xray_clicked`
- `odoo_eol_rescue_clicked`

## Acceptance Criteria

- Pages generated for current useful versions.
- SEO title/meta per version.
- Sitemap integration if applicable.
- i18n.
- Countdown handles past dates gracefully.
- Tests for page render and data integrity.

## Expected Result

BidERP gains SEO landing pages targeting Odoo upgrade intent.

---

# Phase 4 — ERP Chaos Cost Calculator

## Goal

Build a lightweight calculator that estimates the yearly cost of manual ERP chaos.

This is a viral/top-of-funnel tool, not a financial guarantee.

## UX

Route suggestion:

```text
/en/tools/erp-chaos-cost-calculator/
```

Inputs:

- number of employees affected
- manual Excel/admin hours per employee per week OR total weekly manual hours
- average fully-loaded hourly cost
- optional currency
- optional “how many corrections/rework hours per month”

Output:

- estimated weekly/monthly/yearly cost
- plain-English explanation
- CTA: “Now find the root cause with ERP Rescue Check”
- CTA: “If you use Odoo, run Studio X-Ray”

## Accuracy/Legal Copy

Use careful wording:

- “Estimated”
- “Based on your inputs”
- “Not financial advice”
- “Use this as a conversation starter”

No exaggerated claims.

## Implementation

Can be mostly frontend or simple backend.
If stored, store only minimal anonymous event metadata.

Formula should be transparent and deterministic:

```text
weekly_cost = weekly_hours * hourly_cost
yearly_cost = weekly_cost * 52
```

If using employee count:

```text
weekly_hours = employees * hours_per_employee_per_week
```

## Tracking Events

- `chaos_calculator_page_view`
- `chaos_calculator_completed`
- `chaos_calculator_rescue_clicked`
- `chaos_calculator_xray_clicked`

## Acceptance Criteria

- Calculator works without login.
- Validates inputs.
- Mobile friendly.
- No backend complexity unless needed.
- Tests for formula and page render.
- i18n.

## Expected Result

BidERP gets a simple shareable tool that makes ERP pain financially visible and sends visitors into Rescue Check.

---

# Phase 5 — Healthy System Badge

## Goal

Create an optional badge for excellent results that users can share or embed, creating trust and backlinks.

This must be careful: the badge should not imply formal security certification.

## Eligibility

Only for results above a safe threshold, for example:

- ERP Rescue score/status excellent/stable
- Studio X-Ray low risk score/status

Use existing score/status semantics. Do not invent certification.

## Badge Language

Avoid:

- “Certified secure”
- “Guaranteed healthy”
- “Official audit”

Use:

- “BidERP ERP Health Snapshot”
- “Low-risk result”
- “Verified report link”
- “Snapshot date”

## UX

On eligible result pages:

- Show “Get your badge”
- Generate public badge page or embed snippet only after user confirms.
- Badge should link to a public verification page with limited information:
  - badge status
  - date
  - tool type
  - broad level
  - no sensitive details
  - no pain text
  - no full report unless already public

## Privacy

- Opt-in only.
- Never publish company name unless explicitly provided/confirmed.
- No sensitive report data.
- Allow disabling/revoking badge if feasible.

## Tracking Events

- `healthy_badge_offered`
- `healthy_badge_created`
- `healthy_badge_copied`
- `healthy_badge_viewed`

## Acceptance Criteria

- Badge only appears for eligible results.
- Public badge reveals minimal safe info.
- Embed snippet works.
- Tests cover privacy boundaries.
- Clear copy avoids overclaiming.

## Expected Result

BidERP gets a backlink and social-proof mechanism without making risky certification claims.

---

# Phase 6 — Odoo Arabic Glossary MVP

## Goal

Build an SEO-friendly Odoo glossary with Arabic-first value, plus EN/ES support where practical.

This is a long-term SEO asset. Start with MVP, not 300 terms.

## MVP Scope

Start with 30–50 high-value terms, not 300.

Categories:

- Odoo Studio
- ORM/models/fields
- server actions/automations
- views/XML
- accounting/invoicing
- CRM/sales
- inventory
- migration
- hosting/Odoo.sh
- security/access rights

Examples:

- Odoo Studio
- custom field
- computed field
- server action
- automated action
- ir.cron
- model
- view
- record rule
- access rights
- module
- migration
- Odoo.sh
- external ID
- XML-RPC
- ORM
- chatter
- mail alias
- sequence
- pricelist

## UX

Routes:

```text
/ar/odoo-glossary/
/ar/odoo-glossary/<term-slug>/
```

Also EN/ES if aligned with site structure.

Each term page:

- clear definition
- simple example
- why it matters
- common mistake
- related terms
- CTA to tools where relevant

Arabic should be strong and natural, not machine-like.

## Data Structure

Prefer data-driven glossary entries:

- JSON/YAML/Python dict/DB model depending on existing architecture
- slug
- title per language
- definition per language
- example
- category
- related terms
- CTA type

If no CMS model exists, use fixtures or structured data in code for MVP.

## SEO

- unique title/meta
- index page grouped by category
- internal links
- FAQ/definition structured data if existing schema approach supports it
- sitemap integration if applicable

## Tracking Events

- `glossary_index_view`
- `glossary_term_view`
- `glossary_tool_cta_clicked`

## Acceptance Criteria

- Glossary index renders.
- Term pages render.
- 30+ terms included.
- Arabic copy is useful and readable.
- Search/index navigation if easy.
- Tests cover routing/rendering/data integrity.
- No need to finish 300 terms now.

## Expected Result

BidERP begins building a defensible Arabic SEO moat around Odoo/ERP terms.

---

## 6. Final Completion Criteria

The autonomous project is complete when:

- All six phases are implemented or explicitly documented as deferred with a valid reason.
- All tests pass.
- Django check passes.
- Translations compile.
- Migrations are created and valid if needed.
- Manual test plan is updated.
- Feature branch is pushed.
- Final summary is written.

Final commands:

```bash
git status
python manage.py check
python manage.py test
python manage.py compilemessages
git push origin feature/growth-suite-six-phases
```

Final report must include:

- phase-by-phase summary
- files changed
- migrations
- env variables
- test results
- known risks
- manual test steps
- URLs to test
- screenshots to capture manually if relevant
- next recommended action
- whether it is safe to merge to `main`

---

## 7. Final Instruction To Claude

Work autonomously. Make good engineering decisions. Prefer safe, simple, polished implementation over overbuilt architecture. Commit and push each completed phase to the feature branch. Keep the state file updated so work can resume after context loss. Stop only for the defined stop conditions.
