# Data Risk Profiler — Privacy Model

Promise shown to the user: **"We analyze signals and counts, not your
business documents."**

## What we read (read-only, via the whitelisted XML-RPC connector)

- `search_count` totals with explicit domains (most metrics).
- `read_group` aggregates (attachment count/size per model).
- Bounded `search_read` samples (≤2000 rows) of: partner
  name/email/vat/phone/country flag, product name/default_code/barcode —
  used in memory to find duplicate clusters, then discarded.
- `ir.model.data` counts (External-ID coverage).
- `ir.model` list of manual models + their record counts.

## What we never do

- No writes of any kind: create/write/unlink/action execution are not in
  the connector whitelist — they cannot be called even by mistake.
- No SQL against the customer database.
- No reading of invoice lines, amounts, chatter messages, attachments or
  their content. Attachment metrics are count + byte size only.
- No storing or displaying of full raw names, emails, phones or VAT
  numbers. Raw sample values exist only inside the Celery task's memory
  during clustering.
- AI (optional advisor card): the local model receives ONLY the stored
  analyzer output — category scores, counts, percentages, issue codes and
  ALREADY-MASKED examples (`insights.build_payload`). Never raw records,
  never credentials, never attachment/chatter/invoice content. It cannot
  change any score. Its output is schema-validated before storage.
- Credentials: passed as Celery task arguments, used, gone — never stored,
  never logged (project-wide: no Celery result backend).

## Masking rules (tool_data_risk/masking.py)

Applied BEFORE anything is stored in `result_json`:

- email → first character + `***@` + first domain character + `***` + TLD
  (`alex@acme.com` → `b***@a***.com`)
- name  → first 2 characters + `***` (`Acme Trading SL` → `Ac***`)
- vat   → first 2 + `***` + last 2 (`ESB12345678` → `ES***78`)
- phone → `***` + last 2 digits
- product code/barcode → first 2 + `***` + last 2

At most 3 masked examples per issue are stored.

## Stored payload (`ToolRun.result_json`)

Counts, percentages, category scores, severity codes, issue codes, masked
examples, section error/skip markers, and scan metadata (server version,
db name — same as Studio X-Ray). Nothing else.

## Opt-in aggregated snapshots (re-scan deltas)

Only when the visitor ticks the explicit checkbox, a `DataRiskSnapshot`
row is stored OUTSIDE the 72h lifecycle containing exactly: a one-way
hashed database identity (sha256 of host|db, no reverse lookup stored),
the scan date, the overall score and band, per-category scores, and three
headline counts (partners / products / attachments totals). No names, no
emails, no VAT numbers, no examples — not even masked ones. Without the
opt-in nothing persists beyond the normal report lifecycle, and reading a
PREVIOUS snapshot to show progress requires no new data. The visitor-facing
copy states this verbatim on the form.

## Lifecycle

- Same 72-hour expiry as every tool: the nightly
  `wipe_expired_tool_results` task clears `result_json`; the row survives
  for analytics only.
- The report page shows the standard deletion notice.
- Email is optional; when given, the report link email goes through the
  unified `core.email_service` and is archived in EmailLog like all tool
  emails.

## Admin exposure

Admins see the ToolRun (status, score inside result_json, errors) — the
same masked payload the visitor sees. No raw scanned values exist anywhere
to expose.
