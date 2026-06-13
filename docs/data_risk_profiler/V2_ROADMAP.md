# Data Risk Profiler — V2 roadmap status

Shipped in v1.1 (branch feature/data-risk-profiler-v11-v2-foundation):
expiry reminders, send-to-manager, Health Snapshot badge eligibility
(low_data_risk), distinct External-ID coverage.

Shipped as v2 foundation: structured cleanup action list, sanitized AI
advisor card, opt-in aggregated re-scan snapshots with delta display,
stratified duplicate sampling with coverage reporting, Data Quality Map
radar SVG.

Deliberately NOT planned: CSV upload instead of a connection (breaks the
"we never touch your data" model), PDF generation (project rule), any
change to the deterministic scoring contract.

Candidate next steps (decide by demand, not speculation): fuzzy name
matching inside the sample, deeper inventory/accounting signals,
re-scan reminder email 30 days after a cleanup-heavy report.
