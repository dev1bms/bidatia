# Bidatia Business Systems — ERP, Odoo & Data Platform

A Django-based commercial website and platform for **Bidatia Business Systems**, the
ERP and Business Systems division of **Bidatia** (Madrid, Spain) — the firm specializing
in data, artificial intelligence and data governance. The site presents Bidatia's Odoo /
ERP implementation, modernization, BI, automation, AI-agent and data-governance services,
and hosts a suite of free Odoo diagnostic tools used as lead magnets.

Spanish-first and trilingual (Español / English / العربية). Built to generate qualified
leads and consultations for the Business Systems division.

## Stack

- Django 6.0 (Python 3.14)
- SQLite (dev database)
- Django templates + Tailwind CSS (via CDN) + Alpine.js (via CDN) for light interactivity
- No Node build step required for v1

## Project structure

```
bidatia/         Project settings, root URLs, WSGI/ASGI
core/           Home & About pages, site-wide context processor, sitemap config
services/       Service, ServiceFeature, ServiceFAQ models + listing/detail pages + seed command
booking/        ConsultationRequest model, booking form & flow
leads/          Lead model, contact form & flow
blog/           BlogPost & CaseStudy models + listing/detail pages
pages/          Static legal pages (Privacy Policy, Terms)
templates/      All HTML templates (base, partials, per-app pages)
static/         Project static files
media/          User-uploaded files (e.g. blog cover images)
```

## Setup instructions

1. Activate the virtual environment (already created at `.venv`):
   ```bash
   source .venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run migrations:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

4. Create an admin user:
   ```bash
   python manage.py createsuperuser
   ```

5. Load sample content (7 services, case studies, blog posts):
   ```bash
   python manage.py seed_demo_data
   ```
   This command is idempotent — running it again updates existing records instead of duplicating them.

6. Run the development server:
   ```bash
   python manage.py runserver
   ```

7. Open the site:
   - Website: http://127.0.0.1:8000/
   - Admin: http://127.0.0.1:8000/admin/

## Managing content

Everything editorial is managed through the Django admin:

- **Services** — title, pricing, description, features and FAQs (inline editing)
- **Case studies** — challenge / approach / results narrative (one paragraph per line)
- **Blog posts** — articles with excerpt, content and optional cover image
- **Consultation requests** — incoming bookings, with status tracking and internal notes
- **Leads** — incoming contact form submissions

Long text fields (service descriptions, blog content, case study sections) render
**one paragraph per line** — write each paragraph on its own line in the admin textarea.

## Email notifications

Every contact and booking submission is **saved to the database first**, then a
notification email is sent (best-effort) by the reusable helpers in
`core/notifications.py`:

- **To:** `CONTACT_NOTIFICATION_EMAIL` (default `info@bidatia.xyz`)
- **Cc:** `CONTACT_NOTIFICATION_CC` (default `notificaciones@bidatia.xyz`)
- **Reply-To:** the customer's email (reply straight from your inbox)
- **Body:** name, company, email, phone/WhatsApp, country, preferred language,
  selected service, Odoo version, problem summary, submission time, and a direct
  admin link to the saved record.

If email sending fails (e.g. SMTP outage), the submission is **still saved** and
the visitor **still sees the success page** — the error is logged to stderr, never
shown publicly.

In development `EMAIL_BACKEND` auto-selects the **console** backend (emails print to
the terminal, no credentials needed). With `DJANGO_DEBUG=False` it auto-selects
**SMTP**, configured entirely via environment variables (see `.env.example`):
`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_SSL`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD` (env only — never committed), `DEFAULT_FROM_EMAIL`,
`SERVER_EMAIL`.

## Payments

No payment gateway is integrated yet. Consultation requests are saved to the
database, and the success page explains that payment instructions/confirmation
will be sent manually by email. Stripe, Revolut Pro, or simple payment links can
be wired into the `booking` app later without changing the booking form itself.

## Free Tools (lead-magnet diagnostics)

The `/tools/` section hosts free Odoo diagnostic tools used as lead magnets.
Architecture: `tools_core` is shared infrastructure (Lead/ToolRun models,
read-only XML-RPC connector, Celery tasks, report email); each tool is its own
app (`tool_studio_xray`) that may depend only on `tools_core` — never on
another tool app.

**Studio X-Ray** (`/tools/studio-xray/`): a visitor enters their Odoo URL,
database, login and API key, tests the connection, and starts a read-only scan.
A Celery worker collects Studio customizations over XML-RPC, analyzes findings,
computes a 0–100 complexity score, stores the report on the `ToolRun` row and
emails a tokenized report link. Reports auto-delete after 72 hours (beat task).

Security model: credentials are passed to the Celery task as in-memory
arguments and are never persisted or logged (no Celery result backend);
target URLs are HTTPS-only with private-range (SSRF) blocking; the connector
whitelists read-only ORM methods; endpoints are CSRF-protected and
rate-limited (10 test-connections/IP/hour, 3 runs/email/day); forms carry a
honeypot field; error messages are sanitized before storage.

Extra env vars: `REDIS_URL` (broker), optional `TOOLS_BOOKING_URL` (external
CTA link, defaults to the internal booking flow), and
`CELERY_TASK_ALWAYS_EAGER=True` for local development without Redis.

**Local AI insights (optional):** when `TOOLS_AI_MODEL` is set (production:
`qwen3.5:9b`) and Ollama runs on the server (`OLLAMA_URL`, default
loopback), the scan adds an "AI analyst notes" card: a LOCAL model
interprets the finished findings for business readers (detected business
domains, narrative, where to start). Strict boundaries: the model never
decides scores/severities, never receives credentials, its output is
schema-validated and length-capped, any failure ships the report without
the card, and nothing leaves the server. The prompt contract lives in
`tool_studio_xray/ai/xray_insights_skill.md`.
Redis/worker/beat setup and systemd units: see `deploy/CELERY.md` and
`deploy/systemd/`.

Test the flow manually (two options):

```bash
# Option A — real background processing (recommended):
brew install redis && brew services start redis
celery -A bidatia worker -l info        # separate terminal
python manage.py runserver
# open http://localhost:8000/en/tools/studio-xray/ and run a scan

# Option B — no Redis (synchronous, dev only):
CELERY_TASK_ALWAYS_EAGER=True python manage.py runserver
```

Run the opt-in live connector test against your own Odoo (uses a read-only
API key; nothing is written):

```bash
ODOO_TEST_URL=https://yourdb.odoo.com ODOO_TEST_DB=yourdb \
ODOO_TEST_LOGIN=you@company.com ODOO_TEST_KEY=xxxx \
python manage.py test tool_studio_xray  # plus tools_core for the suite
```

## Configuration (environment variables)

Local development runs with **zero configuration** — sensible dev defaults are
baked in. For staging/production, override these via environment variables
(see `.env.example`):

| Variable | Purpose | Production value |
|----------|---------|------------------|
| `DJANGO_SECRET_KEY` | Cryptographic signing key | A long random string |
| `DJANGO_DEBUG` | Debug mode | `False` |
| `DJANGO_ALLOWED_HOSTS` | Allowed hostnames (comma-separated) | `bidatia.xyz,www.bidatia.xyz` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Trusted HTTPS origins for POSTs | `https://bidatia.xyz,https://www.bidatia.xyz` |
| `SITE_BASE_URL` | Base URL for admin links in emails | `https://bidatia.xyz` |
| `CONTACT_EMAIL` / `CONTACT_WHATSAPP` | Public contact details shown on the site | `info@bidatia.xyz` / `+34 681 096 066` |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_USE_SSL` | SMTP server | `bidatia.xyz` / `465` / `True` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP auth (**password env-only**) | `info@bidatia.xyz` / *(secret)* |
| `DEFAULT_FROM_EMAIL` / `SERVER_EMAIL` | From addresses | `Bidatia <info@bidatia.xyz>` |
| `CONTACT_NOTIFICATION_EMAIL` / `CONTACT_NOTIFICATION_CC` | Where form notifications go | `info@bidatia.xyz` / `notificaciones@bidatia.xyz` |

When `DJANGO_DEBUG=False`, production security settings activate automatically
(HTTPS redirect, HSTS, secure session/CSRF cookies, content-type nosniff,
`X-Frame-Options: DENY`). These assume the app runs behind an HTTPS reverse
proxy such as Nginx or Cloudflare. Verify with:

```bash
DJANGO_DEBUG=False DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=bidatia.xyz \
  python manage.py check --deploy
```

## Deployment checklist (bidatia.xyz)

1. **Provision the environment** — copy `.env.example` to `.env` and fill in real
   values (generate a fresh `DJANGO_SECRET_KEY`, set the SMTP password, etc.).
   Load these into the environment (process manager / hosting platform).

2. **Install dependencies & system tools**
   ```bash
   pip install -r requirements.txt
   sudo apt-get install -y gettext   # needed for compilemessages
   ```

3. **Apply database migrations**
   ```bash
   python manage.py migrate
   ```

4. **Create an admin user** (first deploy only)
   ```bash
   python manage.py createsuperuser
   ```

5. **Compile translations** (English/Spanish/Arabic)
   ```bash
   python manage.py compilemessages -l es -l ar
   ```

6. **Collect static files**
   ```bash
   python manage.py collectstatic --noinput
   ```

7. **Run the production deploy check** (must report 0 issues)
   ```bash
   python manage.py check --deploy --fail-level WARNING
   ```

8. **Test SMTP** before going live (sends a real email via your configured server):
   ```bash
   python manage.py shell -c "from django.core.mail import send_mail; \
   send_mail('Bidatia SMTP test', 'It works.', None, ['info@bidatia.xyz'])"
   ```
   Or exercise the full notification path:
   ```bash
   python manage.py shell -c "from leads.models import Lead; from core.notifications import notify_lead; \
   notify_lead(Lead.objects.create(name='SMTP Test', email='you@example.com', message='test'))"
   ```

9. **Serve** behind Nginx/Cloudflare over HTTPS (gunicorn/uvicorn + a reverse proxy
   that terminates TLS and forwards `X-Forwarded-Proto`).

**After deployment, verify:**

- `https://bidatia.xyz/` redirects to `/en/` (or the visitor's browser language)
- `/en/`, `/es/`, `/ar/` all load; Arabic is right-to-left
- The language switcher changes language and stays changed
- Submit the contact and booking forms → record appears in the admin **and** an email
  arrives at `info@bidatia.xyz` (Cc `notificaciones@bidatia.xyz`)
- `https://bidatia.xyz/sitemap.xml` and `/robots.txt` load
- Footer/contact page show `info@bidatia.xyz` and `+34 681 096 066`
- `https://www.bidatia.xyz` works (or redirects to the apex) and HTTPS is enforced

## SEO

- Per-page titles and meta descriptions (set via view context and template blocks)
- Canonical URL, Open Graph and Twitter Card tags in `templates/base.html`
  (an `og_image` block is ready for a per-page social image)
- `robots.txt` at `/robots.txt`
- XML sitemap at `/sitemap.xml` (covers static pages, services, blog posts and case studies)
- Clean, semantic URLs and heading structure throughout

## Internationalization (English / Spanish / Arabic)

The site is **trilingual** with English as the default. Language-prefixed URLs are
generated by `i18n_patterns`:

- `/en/…` English (default) · `/es/…` Spanish · `/ar/…` Arabic (**RTL**)
- Visiting `/` redirects to the visitor's **browser language** (Accept-Language);
  Spanish browsers get `/es/`, Arabic browsers `/ar/`, everyone else `/en/`.
- A **language switcher** (navbar + mobile menu) lets users override the choice,
  which is then remembered (`django.middleware.locale.LocaleMiddleware`).
- Arabic renders right-to-left via `<html dir="rtl">`; code blocks, emails and phone
  numbers are kept LTR.

Translations live in `locale/<lang>/LC_MESSAGES/django.po`. The customer-facing
chrome (navbar, footer, CTAs), forms, success pages, hero and legal/contact headings
are fully translated. Long-form marketing body copy and DB-driven content (service
descriptions, blog posts) remain English for now — translating DB content is a
future step (e.g. `django-modeltranslation`).

**Translation workflow** (requires the `gettext` toolchain):

```bash
# 1. Extract/refresh strings after editing templates or Python source
python manage.py makemessages -l es -l ar --ignore=.venv --ignore=staticfiles

# 2. Edit the catalogues, filling in msgstr values
#    locale/es/LC_MESSAGES/django.po   locale/ar/LC_MESSAGES/django.po

# 3. Compile to .mo (required for translations to take effect; .mo is gitignored)
python manage.py compilemessages -l es -l ar
```

### Translating database content (services, FAQs, blog, case studies)

Page *chrome* lives in `.po` files, but the editable content stored in the
database (services, features, FAQs, blog posts, case studies) is translated with
**django-modeltranslation**. Each translated field has an English, Spanish and
Arabic version (`title`, `title_es`, `title_ar`, …); the bare field always mirrors
English, and missing Spanish/Arabic values fall back to English automatically.

**Editing translations in the admin:** open any Service, Blog post or Case study
in Django admin — each translatable field shows **language tabs (EN / ES / AR)**
so you can write the three versions side by side. Inline FAQs and features show
the same per-language inputs. Only customer-facing text is translated; `slug`,
`icon`, prices-as-numbers, booleans, timestamps and status fields are not.

If you register a new translated field (in `services/translation.py` or
`blog/translation.py`), run `makemigrations` + `migrate`, then
`python manage.py update_translation_fields` once to copy existing English values
into the new English column. Demo content for all three languages is created by
`python manage.py seed_demo_data`.

## Next steps

- Add real content: replace seed data with the actual services, case studies and articles
- Integrate a payment provider (Stripe / Revolut Pro / payment links) for paid consultations
- Translate DB-driven content (service descriptions, blog posts) — e.g. `django-modeltranslation`
- Finish translating long-form marketing body copy on the homepage into ES/AR
- Replace the Tailwind CDN with a compiled build for production performance
- Add `hreflang` alternate tags and a localized sitemap for stronger multilingual SEO
- Move to a production database (PostgreSQL) and static serving (WhiteNoise or a CDN)
