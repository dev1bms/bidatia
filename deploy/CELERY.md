# Celery + Redis — setup & operations

Background task infrastructure for the free diagnostic tools
(`tools_core`). Tool runs execute on a Celery worker; a daily beat task
wipes expired report payloads (the site promises auto-deletion after 72h).

## Security rules (do not relax these)

- **No result backend.** `CELERY_TASK_IGNORE_RESULT = True` — task args,
  kwargs and return values are never written to Redis. Tool-run tasks
  receive Odoo credentials as arguments; this guarantees they exist only
  in worker memory for the duration of a run.
- **Worker log level is INFO**, never DEBUG, in production. DEBUG-level
  celery logging can print task arguments.
- Tasks must never log their arguments (see `tools_core/tasks.py` docstring).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Broker connection for worker + beat |

## Local development (macOS)

```bash
brew install redis
brew services start redis        # or: redis-server  (foreground)

source .venv/bin/activate
celery -A bidatia worker -l info  # terminal 1 — worker
celery -A bidatia beat -l info    # terminal 2 — beat (only if testing the schedule)
```

Verify the pipeline end-to-end:

```bash
python manage.py shell -c "from tools_core.tasks import ping; ping.delay()"
# worker terminal should log: "tools_core ping task executed on a worker"
```

Run the cleanup logic directly (no worker needed):

```bash
python manage.py shell -c "from tools_core.tasks import wipe_expired_tool_results; print(wipe_expired_tool_results())"
```

## Production (Ubuntu/Debian, systemd)

### 1. Redis

```bash
sudo apt update && sudo apt install -y redis-server
# Bind to localhost only (default on Debian/Ubuntu — verify):
grep '^bind' /etc/redis/redis.conf        # expect: bind 127.0.0.1 ::1
sudo systemctl enable --now redis-server
redis-cli ping                            # expect: PONG
```

Optional password: set `requirepass <password>` in `/etc/redis/redis.conf`,
restart redis, and use `REDIS_URL=redis://:<password>@localhost:6379/0`.

### 2. Environment

Add to the production `.env` (same file gunicorn loads):

```
REDIS_URL=redis://localhost:6379/0
```

### 3. Worker + beat services

Templates live in `deploy/systemd/`. Edit `User`, `Group`,
`WorkingDirectory`, `EnvironmentFile` and the venv path to match the
server, then:

```bash
sudo cp deploy/systemd/bidatia-celery-worker.service /etc/systemd/system/
sudo cp deploy/systemd/bidatia-celery-beat.service  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bidatia-celery-worker bidatia-celery-beat
```

Run exactly **one** beat instance. Workers can scale horizontally later by
raising `--concurrency` or adding service instances.

### 4. Operations

```bash
systemctl status bidatia-celery-worker bidatia-celery-beat
journalctl -u bidatia-celery-worker -f          # live worker logs
sudo systemctl restart bidatia-celery-worker    # after each deploy/code change
```

The worker must be restarted on every deploy (it holds loaded code in
memory, like gunicorn).

## What runs on the schedule

| Task | Schedule | Effect |
|---|---|---|
| `tools_core.tasks.wipe_expired_tool_results` | daily 03:30 UTC | Sets `result_json = NULL` on `ToolRun` rows past `expires_at` (created_at + 72h). Rows and metadata are kept for analytics. |
