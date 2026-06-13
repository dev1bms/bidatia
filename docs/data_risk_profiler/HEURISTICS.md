# Data Risk Profiler — Heuristics & Scoring

Deterministic by contract: **code decides every score, severity and
category; no AI participates in scoring**. The optional v2 advisor card
only EXPLAINS the stored metrics (see "v2 additions"). Sources behind
each heuristic: RESEARCH_NOTES.md.

## Collection strategy

- Same read-only XML-RPC connector as Studio X-Ray (whitelisted methods:
  `search_count`, `search_read`, `read_group`, `fields_get`; hard record
  cap 2000/call; ≤200 calls per run).
- Counts first: most metrics are `search_count` with explicit domains,
  including dotted domains for functional-orphan checks
  (e.g. `partner_id.active = False`).
- Duplicate detection runs on a **bounded stratified sample** (≤2000
  active partners / product variants drawn from THREE id ranges — oldest,
  middle, newest — within the same call budget), because `read_group` over
  high-cardinality fields (email) is unbounded. Tables that fit inside the
  cap are covered fully and the report says "full coverage"; otherwise the
  report states the exact coverage percentage. (v2: replaces the v1
  newest-only sample, which under-represented legacy duplicates.)
- A model that is missing or unreadable marks its section
  `skipped`/`error` and the scan continues — partial report over failed run.

## Normalization for duplicate clustering (in-memory only)

- email: lowercase, strip whitespace.
- name: lowercase, strip punctuation, collapse spaces, drop trailing legal
  suffixes (sl, sa, slu, ltd, llc, gmbh, srl, bv, inc, co).
- vat: uppercase, alphanumerics only.
- phone: digits only, compare on the last 9 digits.
- product code/barcode: trimmed, case-sensitive (codes are case-meaningful).

A "cluster" is ≥2 sample records sharing one normalized key. We store the
number of clusters, affected record count, and ≤3 **masked** examples.

## Categories, signals and category scores (0–100 risk)

Every category score is clamped to [0, 100]. `pct(x, total)` is 0 when
total is 0.

### 1. duplicates — Duplicate risk
- signals: email/name/vat/phone clusters (partners, sampled),
  default_code/barcode clusters (products, sampled).
- score = min(100, affected_sample_pct * 4) averaged across available
  signal groups, +10 if VAT clusters exist (tax identity duplicated).

### 2. missing_data — Missing required-looking data
- signals: partners missing email+phone, companies missing VAT, partners
  missing country, products missing internal reference, zero-priced active
  products, placeholder-looking names (count of `test%`/`unknown`/`n/a`).
- score = weighted mean of the percentages (capped); placeholder names add
  min(15, count).

### 3. orphans — Relationship / functional-orphan risk
- signals: open sales orders with archived partner; open SO lines with
  archived product; open purchase orders with archived vendor;
  opportunities without partner and without email; quotations stuck in
  draft/sent > 12 months.
- score = min(100, sum of affected-document percentages * 3).
- We report **functional orphans only** (live row → archived/missing
  business object). True DB orphans are not claimed: the ORM and FK
  constraints make them rare and unverifiable over RPC.

### 4. import_ids — Import identifier coverage
- signal: External-ID coverage per master model (res.partner,
  product.template, product.product, product.category, account.tax):
  DISTINCT `res_id` count via a `read_group` `count_distinct` aggregate on
  `ir.model.data` vs record totals — a record with several XML IDs counts
  once (v1.1). When the aggregate is unavailable (older versions or
  permission quirks) the metric falls back to the v1 row count and is
  flagged `approximate`; the metric can never sink the section.
- score = (1 - mean_coverage) * 45 → deliberately capped under 50:
  missing XIDs are NORMAL for UI-created data (official docs); this is a
  re-import/update-mapping workflow risk, not a defect.

### 5. config — Configuration / reference data
- signals: counts only — companies, active currencies (>3 with one company
  = review), product categories (0 or 1 with many products = review),
  fiscal positions existence, old draft account.move (>6 months).
- score = 15 per triggered review signal.

### 6. attachments — Attachment / bloat
- signals: total attachments, total bytes, top model by count.
- score = 0 below 5k attachments and 2 GB; then +20 per doubling
  (capped 80). Pure migration-effort signal.

### 7. ownership — Inactive-user ownership
- signals: open sales orders, active leads, partners whose salesperson is
  an inactive user; inactive internal users count.
- score = min(100, affected_pct * 5).

### 8. custom_data — Custom/Studio master data
- signals: manual (`x_`) models with >1000 records; their External-ID
  coverage; count of custom models.
- score = 20 per heavy custom model without identifiers (capped 80).

## Overall score (risk, higher = worse — same direction as ERP Rescue)

```
overall = Σ(category_score × weight) / Σ(weight)   over collected categories
weights: duplicates .20, missing .15, orphans .20, import_ids .10,
         config .10, attachments .05, ownership .10, custom_data .10
```

Bands (spec):
- 0–39   low — Low data migration risk
- 40–69  moderate — Moderate risk
- 70–84  high — High risk
- 85–100 critical — Critical cleanup needed

Severity per category: ok <20, info 20–39, warning 40–69, critical ≥70.

Top blockers: the 5 highest-severity issues ranked by
(severity, affected count).

## Cleanup plan

Deterministic mapping issue→action, grouped into:
1. before migration (merge clusters, complete master data, archive junk),
2. during migration rehearsal (test-import small batches, verify m2o
   mapping, keep External IDs from the rehearsal),
3. after first test import (reconcile counts, re-run this profiler,
   compare duplicates before/after).

## Known limitations

- Sampled duplicate detection (≤2000 records per model, stratified across
  oldest/middle/newest id ranges): a fair signal, not a census. The report
  states the exact coverage percentage.
- Dotted-domain counts depend on the scanning user's record rules; rows the
  user cannot read are invisible (we under-report, never over-report).
- External-ID coverage counts distinct records where the count_distinct
  aggregate is available; otherwise it falls back to row counts flagged
  `approximate` in the stored metrics.
- Accounting signals are counts only and explicitly "not accounting advice".
- No SQL, no writes, no attachment/chatter content — by design.

## v2 additions (same deterministic contract)

- **Cleanup action list**: every triggered issue code maps to a structured
  action (priority, suggested owner, stage, why-it-matters, migration
  impact) — pure rules in `views.ACTION_META`/`CATEGORY_WHY`/`CATEGORY_IMPACT`.
- **AI advisor card** (optional): the local model from the X-Ray insights
  pattern explains the SANITIZED stored metrics (scores, counts, codes,
  masked examples) in `tool_data_risk/insights.py`. It never scores; its
  output is schema-validated and length-capped; any failure ships the
  report without the card (`data_risk_ai_advisor_completed/_failed`).
- **Re-scan delta**: when an earlier OPT-IN aggregated snapshot of the same
  hashed database identity exists, the report shows previous → current
  score and per-category deltas (threshold ±3 = "no change"). See
  PRIVACY_MODEL.md for the snapshot contract.
- **Data Quality Map**: a server-side radar SVG of the category scores
  (`quality_map.py`), wrapped in `{% localize off %}` — coordinates are
  never locale-formatted.
- **Expiry reminder + manager share + Health Snapshot badge** (v1.1):
  reuse the platform mechanisms; DRP 'low' band maps to badge level
  `low_data_risk`.
