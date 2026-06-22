# Deploying BidERP Business Systems

This project deploys to a single Linux server, fully isolated from the unrelated
**DevBMS** project on the same host. Two complementary paths exist:

1. **GitHub Actions CI/CD** — automatic on every push to `main` (`.github/workflows/django.yml`).
2. **Manual scripts** — `scripts/deploy/push_and_deploy_bidatia.sh` (run from your Mac),
   which uploads and runs `server_deploy_bidatia.sh` on the server interactively.

## Production layout (isolated)

| Thing | Path / value |
|-------|--------------|
| App user | `bidatia` (system user) |
| App code | `/srv/bidatia/app` |
| Data (SQLite DB, beat schedule) | `/srv/bidatia/data` |
| Environment file | `/etc/bidatia/bidatia.env` (root:bidatia, mode 640) |
| Logs | `/var/log/bidatia` |
| Django service (systemd) | `bidatia` → gunicorn on `127.0.0.1:8030` |
| Celery worker (systemd) | `bidatia-celery-worker` |
| Redis | local on `127.0.0.1:6379`, **BidERP DB `2`** (see below) |
| Domain | `bidatia.xyz` |
| Repo | `git@github.com:dev1bms/bidatia.git` |

> The DB path is read from `DJANGO_DB_PATH` in the env file (e.g.
> `/srv/bidatia/data/db.sqlite3`) so deploys that reset the working tree never
> touch the live database.

## Background workers & Redis isolation (REQUIRED in production)

The free tools (Studio X-Ray, ERP Rescue, Data Risk) run their scans in a
**Celery worker**. Without a running worker, a scan submits but never starts and
the progress page eventually fails with "the processing queue appears to be
offline" (it no longer spins forever). Production therefore needs **all** of:

1. `bidatia.service` (gunicorn) — running.
2. `bidatia-celery-worker.service` — running:
   `ExecStart=/srv/bidatia/app/.venv/bin/celery -A bidatia worker -l info --concurrency=2`
   (no `-Q` needed — the worker consumes BidERP's default queue, see below).
3. **Redis** running locally (`redis-cli ping` → `PONG`).
4. **An isolated Redis DB + queue for BidERP.** This Redis host is shared with
   the older DevBMS project, so the two MUST NOT share a broker DB or queue:
   - Redis DB: BidERP defaults to **db 2** in code (`redis://127.0.0.1:6379/2`).
     Keep `REDIS_URL` (and any `CELERY_BROKER_URL`) on a DB number DevBMS does
     not use. The code default is db 2 *precisely so an unreadable env file can
     never make the worker fall back to db 0 and pick up DevBMS tasks.*
   - Queue: settings pin `CELERY_TASK_DEFAULT_QUEUE = "bidatia"` (+ matching
     exchange/routing key), so even on a shared DB BidERP never consumes the
     generic `celery` queue.

Verify: `celery -A bidatia inspect ping` → `celery@host: OK`, and the worker
log should show `transport: redis://127.0.0.1:6379/2` and only BidERP tasks
(`tool_studio_xray.tasks.run_studio_xray`, `core.tasks.send_lead_notification`, …).

> The systemd unit files live on the server (created during bring-up), **not in
> this repo** — the CI/CD deploy does not manage them. After changing Celery
> settings, restart `bidatia-celery-worker` so the worker reloads broker/queue.

## GitHub Actions CI/CD

### Required repository secrets
- `SSH_HOST`, `SSH_PORT`, `SSH_USER` — connection to the server (over Tailscale).
- `SSH_PRIVATE_KEY` — private key the runner uses to SSH in (never printed).
- `TS_AUTHKEY` — Tailscale auth key so the runner can reach the server.

### `test` job (runs on every push and PR to `main`)
Checkout → Python 3.14 → install `gettext` → install `requirements.txt` →
`compilemessages -l es -l ar` → `check` → `makemigrations --check --dry-run` →
`test` → production `check --deploy` (with `bidatia.xyz` hosts/CSRF and a
throwaway secret key).

### `deploy` job (only on **push to `main`**, after `test` passes)
1. Joins Tailscale (`TS_AUTHKEY`), prepares the SSH key, SSHes to the server.
2. **First-deploy safe checkout** into `/srv/bidatia/app`:
   - If `$APP_DIR/.git` is missing **and** the directory exists with content, it is
     **moved to a timestamped backup** (`/srv/bidatia/app.backup.YYYYmmddHHMMSS`) —
     never deleted — and the repo is cloned fresh.
   - Otherwise it `git fetch origin main` + `git reset --hard origin/main`
     (after pinning `origin` to the repo URL).
3. Creates `.venv` if missing, upgrades pip, installs requirements.
4. **Loads `/etc/bidatia/bidatia.env`** (literally, no shell evaluation, no secrets
   printed) so `migrate` / `seed_demo_data` / `collectstatic` use the same DB and
   paths the systemd service uses.
5. `compilemessages` → `migrate --noinput` → `seed_demo_data` → `collectstatic --noinput`.
6. **Restarts the Django service only:** `sudo -n systemctl restart bidatia`.
   - **Celery is intentionally NOT restarted yet** — `bidatia-celery-worker` and
     `bidatia-celery-beat` are commented out in the workflow until the Redis broker
     and units are verified in production.
7. Health check: `curl -fsS -H "Host: bidatia.xyz" -H "X-Forwarded-Proto: https" http://127.0.0.1:8030/healthz/`.

### Server prerequisites
- The `bidatia` user can `git clone`/`fetch` from GitHub (deploy key on the server).
- Passwordless restart for the service, e.g. `/etc/sudoers.d/bidatia-deploy`:
  ```
  bidatia ALL=(root) NOPASSWD: /usr/bin/systemctl restart bidatia, /usr/bin/systemctl status bidatia
  ```
- `/etc/bidatia/bidatia.env` exists with at least `DJANGO_DEBUG=False`,
  `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `SITE_BASE_URL`,
  `DJANGO_DB_PATH=/srv/bidatia/data/db.sqlite3` (see `.env.example`).
- **Env-file readability + quoting.** The file must be readable by the `bidatia`
  user (`/etc/bidatia` mode `750` group `bidatia`, the env file mode `640`
  root:bidatia) — if the worker cannot read it, Celery silently falls back to
  default broker settings. Any value with **spaces or special chars** must be
  **double-quoted** (e.g. `SITE_NAME="BidERP Business Systems"`); an unquoted
  value breaks `source <file>` in bash. systemd's `EnvironmentFile` and the
  deploy parser strip the quotes.

## Manual deploy (alternative)
```bash
./scripts/deploy/push_and_deploy_bidatia.sh
```
Validates the repo/branch/remote, commits+pushes (with confirmation), then SSHes in
and runs `server_deploy_bidatia.sh`, which performs the same server-side steps
interactively (and can create the env file, systemd units and sudoers entry, and
inspect a Cloudflare tunnel for `bidatia.xyz`).

## Safety
The CI workflow and scripts **never** touch `/srv/devbms`, DevBMS services, the
devbms.com Cloudflare tunnel, or delete `/srv/bidatia/app` without a backup. No
secrets are printed. `.env`, databases, `.venv`, logs, media and secret keys are
git-ignored and never committed.
