# Data Risk Profiler — Research Notes

Research performed 2026-06-13 (web search). Each source: title, URL, type
(official / community / vendor / opinion), summary, and design impact.

## 1. Export and import data — Odoo official documentation

- URL: https://www.odoo.com/documentation/19.0/applications/essentials/export_import_data.html
  (same content lineage: /14.0/ and /13.0/ versions)
- Type: **official**
- Summary: External IDs (XML IDs, stored in `ir.model.data`) are the
  mechanism that makes imports idempotent: with an External ID the import
  row becomes an UPDATE, without one it becomes an INSERT. Odoo
  auto-generates External IDs during import and during
  "import-compatible export".
- Design impact: the **Import identifier risk** category measures External
  ID coverage per master-data model via `ir.model.data` counts. Crucially,
  the docs confirm missing XIDs are NORMAL for UI-created records — so we
  phrase this as "repeat-import/update mapping risk", never as a defect.

## 2. What is an external id, and what is its uses? — Odoo forum

- URL: https://www.odoo.com/forum/help-1/what-is-an-external-id-and-what-is-its-uses-95070
- Type: community
- Summary: `ir.model.data` is the central registry mapping external string
  identifiers to record ids; re-imports without them create duplicates.
- Design impact: justifies counting `ir.model.data` rows per model as a
  cheap, read-only, privacy-free coverage metric.

## 3. Unique identifiers for Contact imports/updates — Odoo forum

- URL: https://www.odoo.com/forum/help-1/unique-identifiers-for-contact-importsupdates-261986
- Type: community
- Summary: practitioners struggle to pick stable keys for partner
  update-imports; name-matching is fragile and duplicate-prone.
- Design impact: duplicate detection must normalize before comparing
  (case, punctuation, legal suffixes) — exact-name matching undercounts.

## 4. Merge contacts — Odoo official documentation

- URL: https://www.odoo.com/documentation/18.0/applications/essentials/contacts/merge.html
- Type: **official**
- Summary: Odoo ships partner merge + deduplication search by selected
  criteria (email, name, VAT…); merging is irreversible and manual review
  is recommended.
- Design impact: our cleanup plan can point to a concrete built-in remedy
  ("review duplicate clusters with the built-in merge tool before
  migration") instead of vague advice. We report *clusters to review*,
  never "guaranteed duplicates" — matching Odoo's own careful wording.

## 5. How can I clean up duplicated Partner records (same email)? — Odoo forum

- URL: https://www.odoo.com/forum/help-1/how-can-i-clean-up-duplicated-partner-records-with-the-same-email-address-176139
- Type: community
- Summary: duplicate partners with shared emails are a recurring real-world
  issue (ecommerce guests, repeated imports, multiple creators).
- Design impact: duplicate-email clusters are a primary signal; we also
  treat "many contacts sharing one email across companies" as review-worthy
  rather than automatically wrong (families/generic info@ addresses exist).

## 6. How to prevent duplicate contact records from repeat ecommerce customers — Odoo forum

- URL: https://www.odoo.com/forum/help-1/how-to-prevent-duplicate-contact-records-from-repeat-ecommerce-customers-281117
- Type: community
- Summary: confirms duplicates accumulate from normal operation (website
  checkouts), not only bad imports.
- Design impact: tone — duplicates are framed as normal accumulation that
  matters *before migration*, not as negligence.

## 7. Odoo migration checklists (partner/vendor articles)

- URLs:
  - https://silentinfotech.com/blog/odoo-1/odoo-migration-checklist-463
  - https://www.codetrade.io/blog/odoo-erp-migration-checklist/
  - https://www.technaureus.com/blog-detail/odoo-migration-checklist
  - https://legionssoft.com/best-practices-for-data-cleanup-odoo-19-migration/
- Type: vendor (multiple independent partners — convergent advice)
- Summary: consistent pre-migration steps across partners: dedupe contacts,
  fix master data (names, tax IDs, contact details), standardize UoM,
  archive dead records, clean junk/test entries, reconcile AR/AP, test
  small import batches first; data problems found during migration are far
  more expensive than during an audit.
- Design impact: shaped the category list (duplicates, completeness,
  archived-but-referenced, configuration) and the three-stage cleanup plan
  (before migration / during rehearsal / after first test import).

## 8. Import relation-field problems — Odoo forum (multiple threads)

- URLs:
  - https://www.odoo.com/forum/help-1/how-to-import-data-in-two-many2one-related-fields-with-duplicate-name-24674
  - https://www.odoo.com/forum/help-1/import-csv-file-with-related-field-other-than-id-external-id-name-119667
- Type: community
- Summary: many2one columns are matched by name/External ID/DB id; matching
  by *name* breaks when names are ambiguous (duplicates) and blocks when the
  target does not exist.
- Design impact: duplicates are not only a reporting problem — they are an
  **import-mapping hazard** (ambiguous m2o resolution). This links the
  duplicate category to the migration story, and motivates the "functional
  orphan" checks (rows pointing at archived/ambiguous targets).

## 9. ir.attachment / filestore bloat — Odoo forum + GitHub

- URLs:
  - https://www.odoo.com/forum/help-1/database-size-growing-due-to-attachments-247217
  - https://www.odoo.com/forum/help-1/reduce-database-size-274883
  - https://github.com/odoo/odoo/issues/23892
- Type: community / official tracker
- Summary: attachment volume is the dominant driver of database/backup
  size; oversized databases slow upgrades, rehearsals and restores.
- Design impact: the **Attachment/bloat** category reports count, total
  size and top models by attachment count — counts and sizes only, content
  never read.

## 10. Archived records still referenced (sale-order archive modules, OCA)

- URLs:
  - https://www.odoo.com/forum/help-1/sales-order-what-field-marks-a-sale-order-record-as-archived-204363
  - https://pypi.org/project/odoo-addon-sale-order-archive (OCA)
- Type: community / OCA
- Summary: archiving semantics differ per model; archived partners/products
  remain referenced by open documents, which surprises users during
  upgrades and re-imports.
- Design impact: defines our **functional orphan** checks: open sales /
  purchases referencing archived partners or products, and ownership by
  inactive users. We deliberately do NOT claim database-level orphans —
  the ORM + FK constraints make true orphans rare (see HEURISTICS.md).

## Conclusions carried into the heuristics

1. Count, don't read: every official mechanism we rely on (ir.model.data,
   read_group aggregates, search_count with dotted domains) works without
   touching document content.
2. Phrase duplicates as "potential clusters to review" (Odoo's merge UI
   itself requires human confirmation).
3. External-ID coverage is a *workflow* risk (re-imports/update-imports),
   not a defect — score it gently and explain it.
4. Functional orphan ≠ technical orphan; we only report what we can verify
   with read-only domains.
5. Attachment bloat is a migration-effort signal, reported in counts/bytes.
