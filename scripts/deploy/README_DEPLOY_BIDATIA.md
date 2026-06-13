# Deploying Bidatia Business Systems

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
| Django service (systemd) | `bidatia` → gunicorn on `127.0.0.1:8020` |
| Domain | `bidatia.xyz` |
| Repo | `git@github.com:dev1bms/bidatia.git` |

> The DB path is read from `DJANGO_DB_PATH` in the env file (e.g.
> `/srv/bidatia/data/db.sqlite3`) so deploys that reset the working tree never
> touch the live database.

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
7. Health check: `curl -fsS -H "Host: bidatia.xyz" -H "X-Forwarded-Proto: https" http://127.0.0.1:8020/healthz/`.

### Server prerequisites
- The `bidatia` user can `git clone`/`fetch` from GitHub (deploy key on the server).
- Passwordless restart for the service, e.g. `/etc/sudoers.d/bidatia-deploy`:
  ```
  bidatia ALL=(root) NOPASSWD: /usr/bin/systemctl restart bidatia, /usr/bin/systemctl status bidatia
  ```
- `/etc/bidatia/bidatia.env` exists with at least `DJANGO_DEBUG=False`,
  `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `SITE_BASE_URL`,
  `DJANGO_DB_PATH=/srv/bidatia/data/db.sqlite3` (see `.env.example`).

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
