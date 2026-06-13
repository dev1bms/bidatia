#!/usr/bin/env bash
#
# server_deploy_bidatia.sh — Bidatia Business Systems server-side deployment.
#
# Runs ON THE PRODUCTION SERVER, as a sudo-capable admin user. It deploys the
# Django app into an isolated layout owned by the `bidatia` system user and
# never touches DevBMS (/srv/devbms, devbms services, or the devbms tunnel).
#
# It is INTERACTIVE and SAFE: it inspects the environment, asks before
# installing packages, writing the env file, creating systemd units, editing
# sudoers or scaffolding a Cloudflare tunnel, and never prints secrets.
#
# Usually launched by scripts/deploy/push_and_deploy_bidatia.sh, but can be run
# directly:   sudo-capable-user$ bash server_deploy_bidatia.sh
#
# Tunable via environment (the push script passes these; otherwise prompted):
#   DEPLOY_PATH   default /srv/bidatia/app
#   REPO_URL      default git@github.com:dev1bms/bidatia.git
#   GIT_BRANCH    default main
#   BIND_ADDR     default 127.0.0.1:8020
#   APP_USER      default bidatia
# ----------------------------------------------------------------------------
set -uo pipefail

# ── Fixed, non-secret configuration ─────────────────────────────────────────
APP_USER="${APP_USER:-bidatia}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
BIDATIA_BASE="/srv/bidatia"
DEPLOY_PATH="${DEPLOY_PATH:-$BIDATIA_BASE/app}"
DATA_DIR="$BIDATIA_BASE/data"
LOG_DIR="/var/log/bidatia"
ETC_DIR="/etc/bidatia"
ENV_FILE="$ETC_DIR/bidatia.env"
REPO_URL="${REPO_URL:-git@github.com:dev1bms/bidatia.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"
BIND_ADDR="${BIND_ADDR:-127.0.0.1:8020}"
SERVICES=(bidatia bidatia-celery-worker bidatia-celery-beat)
FORBIDDEN_PATH="/srv/devbms"   # must never be touched

# ── Pretty output (degrades gracefully without a TTY) ───────────────────────
if [[ -t 1 ]]; then
    B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0m'
    RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLU=$'\033[34m'; CYN=$'\033[36m'
else
    B=""; DIM=""; R=""; RED=""; GRN=""; YEL=""; BLU=""; CYN=""
fi
step()  { printf '\n%s\n' "${B}${BLU}==> $*${R}"; }
info()  { printf '    %s\n' "$*"; }
ok()    { printf '    %s%s%s\n' "$GRN" "✓ $*" "$R"; }
warn()  { printf '    %s%s%s\n' "$YEL" "! $*" "$R"; }
err()   { printf '    %s%s%s\n' "$RED" "✗ $*" "$R" >&2; }
die()   { err "$*"; exit 1; }
have()  { command -v "$1" >/dev/null 2>&1; }

confirm() { # confirm "question" [default-no] -> returns 0 on yes
    local q="$1" ans
    read -rp "    ${q} [y/N] " ans </dev/tty || true
    [[ "$ans" =~ ^[Yy] ]]
}
ask() { # ask "prompt" "default" -> echoes answer (or default)
    local p="$1" def="${2:-}" v
    read -rp "    ${p}${def:+ [${def}]}: " v </dev/tty || true
    printf '%s' "${v:-$def}"
}
ask_secret() { # ask_secret "prompt" -> echoes secret (read silently)
    local p="$1" v
    read -rsp "    ${p}: " v </dev/tty || true
    printf '\n' >&2
    printf '%s' "$v"
}

# Run a shell snippet as the bidatia user, inside the app dir (no Django env).
bidatia_run() {
    sudo -u "$APP_USER" -H env APP_DIR="$DEPLOY_PATH" bash -c 'set -euo pipefail; cd "$APP_DIR"; '"$1"
}
# Run a manage.py subcommand as the bidatia user WITH the env file loaded.
# Secrets are read from the file by the child (never passed via argv/ps).
manage() {
    sudo -u "$APP_USER" -H env APP_DIR="$DEPLOY_PATH" ENV_FILE="$ENV_FILE" bash -c '
        set -euo pipefail
        cd "$APP_DIR"
        if [[ -r "$ENV_FILE" ]]; then
            set -a
            while IFS="=" read -r k v; do
                [[ -z "$k" || "$k" == \#* ]] && continue
                v="${v%\"}"; v="${v#\"}"; v="${v%\'"'"'}"; v="${v#\'"'"'}"
                export "$k=$v"
            done < "$ENV_FILE"
            set +a
        fi
        exec .venv/bin/python manage.py "$@"
    ' _ "$@"
}

# Result accumulators for the final summary.
SUM_GITREV="?"; SUM_PY="?"; SUM_CHECK="not run"; SUM_MIGRATE="not run"
SUM_STATIC="not run"; SUM_HEALTH="not run"; SUM_CELERY="n/a"; SUM_CF="not checked"

trap 'echo; err "Deployment interrupted."; exit 130' INT

# ── 0. Sanity / safety preflight ────────────────────────────────────────────
step "Preflight & safety checks"
[[ "$(uname -s)" == "Linux" ]] || die "This script must run on the Linux server, not your Mac."
[[ "$DEPLOY_PATH" == "$BIDATIA_BASE"/* ]] || die "DEPLOY_PATH must live under $BIDATIA_BASE (got: $DEPLOY_PATH)."
case "$DEPLOY_PATH" in
    "$FORBIDDEN_PATH"|"$FORBIDDEN_PATH"/*) die "Refusing to operate inside $FORBIDDEN_PATH (DevBMS).";;
esac
if ! sudo -n true 2>/dev/null; then
    info "This script needs sudo for package installs, systemd and the env file."
    info "You may be prompted for your sudo password."
    sudo -v || die "sudo is required."
fi
ok "Running on Linux; sudo available; target is isolated under $BIDATIA_BASE."

# user bidatia present?
if id "$APP_USER" >/dev/null 2>&1; then ok "System user '$APP_USER' exists."
else die "System user '$APP_USER' not found. Create it before deploying."; fi

# expected directories
for d in "$DEPLOY_PATH" "$DATA_DIR" "$LOG_DIR" "$ETC_DIR"; do
    if [[ -d "$d" ]]; then ok "Directory present: $d"
    else
        warn "Directory missing: $d"
        if confirm "Create $d now (owned by $APP_USER where appropriate)?"; then
            sudo mkdir -p "$d"
            case "$d" in
                "$ETC_DIR") sudo chown root:"$APP_GROUP" "$d"; sudo chmod 750 "$d";;
                *)          sudo chown "$APP_USER":"$APP_GROUP" "$d";;
            esac
            ok "Created $d"
        else
            die "Required directory $d missing; aborting."
        fi
    fi
done

# ── 1. System packages ──────────────────────────────────────────────────────
step "System packages"
declare -A PKG=( [git]=git [python3]=python3 [curl]=curl [msgfmt]=gettext )
MISSING_PKGS=()
for bin in "${!PKG[@]}"; do
    if have "$bin"; then ok "$bin present"; else warn "$bin missing"; MISSING_PKGS+=("${PKG[$bin]}"); fi
done
# python venv + pip (module checks, not separate binaries)
if python3 -c 'import venv' 2>/dev/null; then ok "python3-venv present"; else warn "python3-venv missing"; MISSING_PKGS+=(python3-venv); fi
if python3 -m pip --version >/dev/null 2>&1; then ok "pip present"; else warn "pip missing"; MISSING_PKGS+=(python3-pip); fi

if ((${#MISSING_PKGS[@]})); then
    # de-duplicate
    readarray -t MISSING_PKGS < <(printf '%s\n' "${MISSING_PKGS[@]}" | sort -u)
    warn "Missing packages: ${MISSING_PKGS[*]}"
    if have apt-get; then
        if confirm "Run 'apt-get install ${MISSING_PKGS[*]}' now?"; then
            sudo apt-get update -qq
            sudo apt-get install -y "${MISSING_PKGS[@]}" || die "Package install failed."
            ok "Packages installed."
        else
            die "Required packages missing; aborting."
        fi
    else
        die "apt-get not found. Install these manually: ${MISSING_PKGS[*]}"
    fi
fi
SUM_PY="$(python3 --version 2>&1)"

# ── 2. Repository (clone or fast-forward), as the bidatia user ──────────────
step "Repository at $DEPLOY_PATH"
GIT_DIR_PRESENT=false
[[ -d "$DEPLOY_PATH/.git" ]] && GIT_DIR_PRESENT=true
APP_EMPTY=true
if sudo test -n "$(sudo ls -A "$DEPLOY_PATH" 2>/dev/null)"; then APP_EMPTY=false; fi

if $GIT_DIR_PRESENT; then
    CUR_REMOTE="$(bidatia_run 'git remote get-url origin 2>/dev/null || true')"
    info "Existing checkout. origin = ${CUR_REMOTE:-<none>}"
    if [[ "$CUR_REMOTE" != "$REPO_URL" ]]; then
        warn "origin ($CUR_REMOTE) != expected ($REPO_URL)."
        if confirm "Set origin to $REPO_URL?"; then
            bidatia_run "git remote set-url origin '$REPO_URL'"
        else
            die "Remote mismatch; aborting to stay safe."
        fi
    fi
    info "Fetching and hard-resetting to origin/$GIT_BRANCH ..."
    bidatia_run "git fetch origin '$GIT_BRANCH' && git reset --hard 'origin/$GIT_BRANCH'" || die "git update failed."
    ok "Updated to origin/$GIT_BRANCH."
elif $APP_EMPTY; then
    info "Directory empty — cloning $REPO_URL ..."
    bidatia_run "git clone --branch '$GIT_BRANCH' '$REPO_URL' ." || \
        die "Clone failed. Ensure the '$APP_USER' user's SSH key can read the repo."
    ok "Cloned."
else
    err "$DEPLOY_PATH is not empty and not a git repo."
    confirm "List its contents?" && sudo ls -la "$DEPLOY_PATH"
    die "Refusing to overwrite non-empty, non-git directory. Resolve manually."
fi
SUM_GITREV="$(bidatia_run 'git rev-parse --short HEAD 2>/dev/null || echo unknown')"
info "Deployed revision: $SUM_GITREV"

# Detect the WSGI module (e.g. bidatia/wsgi.py -> bidatia.wsgi:application).
WSGI_FILE="$(bidatia_run "ls */wsgi.py 2>/dev/null | head -n1 || true")"
[[ -n "$WSGI_FILE" ]] || die "Could not find a wsgi.py under $DEPLOY_PATH."
WSGI_PKG="${WSGI_FILE%/wsgi.py}"
WSGI_MODULE="${WSGI_PKG}.wsgi:application"
ok "WSGI module: $WSGI_MODULE"

# ── 3. Python virtualenv + dependencies ─────────────────────────────────────
step "Python virtualenv & dependencies"
if bidatia_run 'test -x .venv/bin/python'; then ok ".venv present"; else
    info "Creating .venv ..."
    bidatia_run 'python3 -m venv .venv' || die "venv creation failed."
    ok ".venv created"
fi
info "Installing/updating requirements (this can take a minute) ..."
bidatia_run '.venv/bin/python -m pip install --upgrade pip -q' || die "pip upgrade failed."
bidatia_run '.venv/bin/python -m pip install -r requirements.txt -q' || die "requirements install failed."
# gunicorn is in requirements.txt, but guarantee it exists for the web service.
bidatia_run '.venv/bin/python -c "import gunicorn" 2>/dev/null || .venv/bin/python -m pip install -q gunicorn' \
    || die "gunicorn install failed."
ok "Dependencies installed (incl. gunicorn)."

# ── 4. Environment file (/etc/bidatia/bidatia.env) ──────────────────────────
step "Environment file ($ENV_FILE)"
if sudo test -f "$ENV_FILE"; then
    ok "Env file already exists — leaving it untouched."
    # Validate required keys WITHOUT printing any values.
    for key in DJANGO_SECRET_KEY DJANGO_ALLOWED_HOSTS SITE_BASE_URL; do
        if sudo grep -q "^${key}=" "$ENV_FILE"; then ok "$key set"; else warn "$key NOT set in $ENV_FILE"; fi
    done
    if ! sudo grep -q '^DJANGO_DB_PATH=' "$ENV_FILE"; then
        warn "DJANGO_DB_PATH not set — DB would default to inside the code checkout."
        if confirm "Append DJANGO_DB_PATH=$DATA_DIR/db.sqlite3 to the env file?"; then
            echo "DJANGO_DB_PATH=$DATA_DIR/db.sqlite3" | sudo tee -a "$ENV_FILE" >/dev/null
            ok "Added DJANGO_DB_PATH."
        fi
    else
        ok "DJANGO_DB_PATH set"
    fi
else
    warn "Env file not found."
    if ! confirm "Create $ENV_FILE interactively now (recommended)?"; then
        die "Cannot continue without an environment file."
    fi
    info "Generating a strong DJANGO_SECRET_KEY automatically..."
    SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
    HOSTS="$(ask 'DJANGO_ALLOWED_HOSTS (comma-separated)' 'bidatia.xyz,www.bidatia.xyz')"
    CSRF="$(ask 'DJANGO_CSRF_TRUSTED_ORIGINS' 'https://bidatia.xyz,https://www.bidatia.xyz')"
    BASEURL="$(ask 'SITE_BASE_URL' 'https://bidatia.xyz')"
    CEMAIL="$(ask 'CONTACT_EMAIL' 'info@bidatia.xyz')"
    CWHATS="$(ask 'CONTACT_WHATSAPP (public phone/WhatsApp)' '+34 911 23 45 67')"

    SMTP_BLOCK=""
    if confirm "Configure outgoing SMTP now?"; then
        EHOST="$(ask 'EMAIL_HOST' 'smtp.your-mail-host.example')"
        EPORT="$(ask 'EMAIL_PORT' '465')"
        EUSER="$(ask 'EMAIL_HOST_USER' 'info@bidatia.xyz')"
        EPASS="$(ask_secret 'EMAIL_HOST_PASSWORD (hidden)')"
        SMTP_BLOCK=$(cat <<EOF
EMAIL_HOST=${EHOST}
EMAIL_PORT=${EPORT}
EMAIL_USE_SSL=True
EMAIL_HOST_USER=${EUSER}
EMAIL_HOST_PASSWORD="${EPASS}"
DEFAULT_FROM_EMAIL="Bidatia Business Systems <${EUSER}>"
SERVER_EMAIL=${EUSER}
CONTACT_NOTIFICATION_EMAIL=${EUSER}
EOF
)
    fi
    GA_BLOCK=""
    if confirm "Add Google Analytics / Search Console values?"; then
        GAID="$(ask 'GA_MEASUREMENT_ID (e.g. G-XXXXXXXXXX)' '')"
        GVER="$(ask 'GOOGLE_SITE_VERIFICATION token' '')"
        GA_BLOCK=$(printf 'GA_MEASUREMENT_ID=%s\nGOOGLE_SITE_VERIFICATION=%s\n' "$GAID" "$GVER")
    fi

    TMP_ENV="$(mktemp)"; chmod 600 "$TMP_ENV"
    cat > "$TMP_ENV" <<EOF
# Bidatia Business Systems — production environment (systemd EnvironmentFile).
# Generated $(date -u +%Y-%m-%dT%H:%M:%SZ). Owner root:${APP_GROUP}, mode 640.
# NEVER commit this file or print its contents.
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=${SECRET}
DJANGO_ALLOWED_HOSTS=${HOSTS}
DJANGO_CSRF_TRUSTED_ORIGINS=${CSRF}
SITE_BASE_URL=${BASEURL}
DJANGO_DB_PATH=${DATA_DIR}/db.sqlite3
CONTACT_EMAIL=${CEMAIL}
CONTACT_WHATSAPP="${CWHATS}"
${SMTP_BLOCK}
${GA_BLOCK}
EOF
    sudo install -m 640 -o root -g "$APP_GROUP" "$TMP_ENV" "$ENV_FILE"
    shred -u "$TMP_ENV" 2>/dev/null || rm -f "$TMP_ENV"
    unset SECRET EPASS
    ok "Env file created (640 root:${APP_GROUP}); secrets not echoed."
fi
# Ensure the env file is readable by the app user (group) and not world-readable.
sudo chmod 640 "$ENV_FILE"; sudo chown root:"$APP_GROUP" "$ENV_FILE"

# Make sure the DB directory exists and is writable by the app user.
sudo mkdir -p "$DATA_DIR"
sudo chown "$APP_USER":"$APP_GROUP" "$DATA_DIR"
ok "Data dir ready & owned by $APP_USER: $DATA_DIR"

# ── 5. Django management commands (as bidatia, env loaded) ───────────────────
step "Django: check / compilemessages / migrate / seed / collectstatic"
if manage check; then SUM_CHECK="OK"; ok "manage.py check passed"; else SUM_CHECK="FAILED"; die "Django check failed — fix before continuing."; fi
manage compilemessages -l es -l ar && ok "Translations compiled" || warn "compilemessages reported issues (continuing)"
if manage migrate --noinput; then SUM_MIGRATE="OK"; ok "Migrations applied"; else SUM_MIGRATE="FAILED"; die "migrate failed."; fi
manage seed_demo_data >/dev/null && ok "Demo content seeded (idempotent)" || warn "seed_demo_data reported issues"
if manage collectstatic --noinput >/dev/null; then SUM_STATIC="OK"; ok "Static files collected"; else SUM_STATIC="FAILED"; warn "collectstatic failed"; fi

# ── 6. Celery / Redis detection ─────────────────────────────────────────────
step "Celery / Redis"
ENABLE_CELERY=false
if bidatia_run 'test -f */celery.py' >/dev/null 2>&1 || bidatia_run "test -f ${WSGI_PKG}/celery.py"; then
    info "Celery IS configured in this project ($WSGI_PKG/celery.py)."
    REDIS_OK=false
    if have redis-cli && redis-cli ping >/dev/null 2>&1; then REDIS_OK=true; fi
    if ! $REDIS_OK && python3 -c 'import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(("127.0.0.1",6379))==0 else 1)'; then REDIS_OK=true; fi
    if $REDIS_OK; then
        ok "Redis reachable on 127.0.0.1:6379 — Celery services will be enabled."
        ENABLE_CELERY=true; SUM_CELERY="enabled (Redis up)"
    else
        warn "Celery is configured but NO Redis broker is reachable on 127.0.0.1:6379."
        info "Options:"
        info "  [1] Skip Celery — deploy the web service only (recommended if you don't use the tools' background scans)"
        info "  [2] Install & start redis-server now (apt), then enable Celery"
        info "  [3] Create Celery units anyway but leave them DISABLED (enable later once Redis is up)"
        choice="$(ask 'Choose 1/2/3' '1')"
        case "$choice" in
            2)  if have apt-get && confirm "Install and start redis-server?"; then
                    sudo apt-get update -qq && sudo apt-get install -y redis-server
                    sudo systemctl enable --now redis-server
                    if redis-cli ping >/dev/null 2>&1; then ENABLE_CELERY=true; SUM_CELERY="enabled (Redis installed)"; ok "Redis up.";
                    else warn "Redis still not responding; skipping Celery."; SUM_CELERY="skipped (Redis failed)"; fi
                else SUM_CELERY="skipped"; fi ;;
            3)  ENABLE_CELERY=true; CELERY_DISABLED=1; SUM_CELERY="units created, left disabled" ;;
            *)  SUM_CELERY="skipped (web only)"; info "Skipping Celery; the site & tools degrade gracefully without it." ;;
        esac
    fi
else
    info "No celery.py found — this project does not use Celery. Skipping."
    SUM_CELERY="n/a (not configured)"
fi

# ── 7. systemd units ────────────────────────────────────────────────────────
step "systemd services"
SYSTEMCTL="$(command -v systemctl || echo /usr/bin/systemctl)"
write_unit() { # write_unit <name> <content>; returns 0 if changed
    local name="$1" content="$2" path="/etc/systemd/system/$1.service" tmp
    tmp="$(mktemp)"; printf '%s\n' "$content" > "$tmp"
    if sudo test -f "$path" && sudo cmp -s "$tmp" "$path"; then
        rm -f "$tmp"; info "$name.service unchanged"; return 1
    fi
    sudo install -m 644 -o root -g root "$tmp" "$path"; rm -f "$tmp"
    ok "Wrote $path"; return 0
}

WEB_UNIT="[Unit]
Description=Bidatia Business Systems — Gunicorn (Django WSGI)
After=network.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$DEPLOY_PATH
EnvironmentFile=$ENV_FILE
ExecStart=$DEPLOY_PATH/.venv/bin/gunicorn $WSGI_MODULE --workers 3 --bind $BIND_ADDR --access-logfile - --error-logfile -
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target"
write_unit bidatia "$WEB_UNIT" || true

if $ENABLE_CELERY; then
    WORKER_UNIT="[Unit]
Description=Bidatia — Celery worker
After=network.target
Wants=redis-server.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$DEPLOY_PATH
EnvironmentFile=$ENV_FILE
ExecStart=$DEPLOY_PATH/.venv/bin/celery -A $WSGI_PKG worker -l info
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target"
    BEAT_UNIT="[Unit]
Description=Bidatia — Celery beat scheduler
After=network.target
Wants=redis-server.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$DEPLOY_PATH
EnvironmentFile=$ENV_FILE
ExecStart=$DEPLOY_PATH/.venv/bin/celery -A $WSGI_PKG beat -l info --schedule=$DATA_DIR/celerybeat-schedule
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target"
    write_unit bidatia-celery-worker "$WORKER_UNIT" || true
    write_unit bidatia-celery-beat "$BEAT_UNIT" || true
fi

sudo "$SYSTEMCTL" daemon-reload
ok "systemd reloaded"

# Enable + (re)start. Web always; celery per detection.
ENABLE_LIST=(bidatia)
$ENABLE_CELERY && ENABLE_LIST+=(bidatia-celery-worker bidatia-celery-beat)
for svc in "${ENABLE_LIST[@]}"; do
    if [[ "${CELERY_DISABLED:-0}" == "1" && "$svc" == bidatia-celery-* ]]; then
        info "$svc created but left disabled (enable once Redis is configured)."
        continue
    fi
    sudo "$SYSTEMCTL" enable "$svc" >/dev/null 2>&1 || true
    info "Restarting $svc ..."
    sudo "$SYSTEMCTL" restart "$svc" || warn "Failed to restart $svc (check: journalctl -u $svc)"
done

# ── 8. sudoers (least-privilege restart for the bidatia user / CI) ──────────
step "Passwordless restart permission for '$APP_USER'"
SUDOERS_FILE="/etc/sudoers.d/bidatia-deploy"
SUDOERS_CONTENT="# Allow the '$APP_USER' user (and CI deploys) to restart Bidatia services only.
$APP_USER ALL=(root) NOPASSWD: $SYSTEMCTL restart bidatia, $SYSTEMCTL status bidatia, $SYSTEMCTL restart bidatia-celery-worker, $SYSTEMCTL status bidatia-celery-worker, $SYSTEMCTL restart bidatia-celery-beat, $SYSTEMCTL status bidatia-celery-beat"
if sudo -l -U "$APP_USER" 2>/dev/null | grep -q "restart bidatia"; then
    ok "'$APP_USER' already has the needed NOPASSWD systemctl rights."
else
    warn "'$APP_USER' cannot restart the services without a password."
    printf '%s\n' "${DIM}--- proposed $SUDOERS_FILE ---${R}"
    printf '%s\n' "$SUDOERS_CONTENT"
    printf '%s\n' "${DIM}------------------------------${R}"
    if confirm "Install this sudoers file now (validated with visudo)?"; then
        TMP_SUDO="$(mktemp)"; printf '%s\n' "$SUDOERS_CONTENT" > "$TMP_SUDO"
        if sudo visudo -cf "$TMP_SUDO" >/dev/null 2>&1; then
            sudo install -m 440 -o root -g root "$TMP_SUDO" "$SUDOERS_FILE"
            ok "Installed $SUDOERS_FILE"
        else
            err "visudo validation failed — NOT installing."
        fi
        rm -f "$TMP_SUDO"
    else
        info "Skipped. To add it later:  sudo visudo -f $SUDOERS_FILE   (paste the block above)"
    fi
fi

# ── 9. Local health check ───────────────────────────────────────────────────
step "Local health check (http://$BIND_ADDR/healthz/)"
HEALTH_URL="http://$BIND_ADDR/healthz/"
SUM_HEALTH="FAILED"
for attempt in 1 2 3 4 5; do
    if out="$(curl -fsS --max-time 5 -H "Host: bidatia.xyz" -H "X-Forwarded-Proto: https" "$HEALTH_URL" 2>/dev/null)"; then
        ok "Health OK: $out"; SUM_HEALTH="OK ($out)"; break
    fi
    info "Not ready yet (attempt $attempt/5) — waiting 2s ..."; sleep 2
done
[[ "$SUM_HEALTH" == OK* ]] || warn "Health check failed. Inspect:  journalctl -u bidatia -n 50 --no-pager"

# ── 10. Cloudflare Tunnel (inspect, never touch DevBMS) ─────────────────────
step "Cloudflare Tunnel for bidatia.xyz"
if ! have cloudflared; then
    info "cloudflared not installed on this host — skipping tunnel setup."
    SUM_CF="cloudflared not installed"
else
    CF_DIR="/etc/cloudflared"
    BIDATIA_CF_YML="$CF_DIR/bidatia.yml"
    BIDATIA_CF_SVC="cloudflared-bidatia"
    # Inspect existing configs by NAME only (never read devbms secrets).
    info "Existing cloudflared configs:"; sudo ls -1 "$CF_DIR" 2>/dev/null | sed 's/^/      /' || info "      (none)"
    if sudo ls "$CF_DIR" 2>/dev/null | grep -qi devbms; then
        warn "A DevBMS cloudflared config is present — it will NOT be touched."
    fi
    if sudo test -f "$BIDATIA_CF_YML" || systemctl list-unit-files 2>/dev/null | grep -q "^$BIDATIA_CF_SVC"; then
        ok "A Bidatia tunnel config/service already exists."
        SUM_CF="$(systemctl is-active "$BIDATIA_CF_SVC" 2>/dev/null || echo 'present (inactive)')"
    else
        warn "No Bidatia tunnel found. A tunnel needs Cloudflare auth (cannot be fully automated here)."
        info "Manual one-time steps (run as a user logged into Cloudflare):"
        info "  cloudflared tunnel login"
        info "  cloudflared tunnel create bidatia          # note the Tunnel UUID + credentials json"
        info "  cloudflared tunnel route dns bidatia bidatia.xyz"
        info "  cloudflared tunnel route dns bidatia www.bidatia.xyz"
        if confirm "Scaffold $BIDATIA_CF_YML + $BIDATIA_CF_SVC.service now (you supply the tunnel id)?"; then
            TID="$(ask 'Tunnel UUID' '')"
            CREDS="$(ask 'Credentials file path' "$CF_DIR/${TID}.json")"
            if [[ -z "$TID" ]]; then
                warn "No tunnel id given — skipping scaffold."
            else
                TMP_YML="$(mktemp)"
                cat > "$TMP_YML" <<EOF
tunnel: ${TID}
credentials-file: ${CREDS}
ingress:
  - hostname: bidatia.xyz
    service: http://$BIND_ADDR
  - hostname: www.bidatia.xyz
    service: http://$BIND_ADDR
  - service: http_status:404
EOF
                sudo install -m 640 -o root -g root "$TMP_YML" "$BIDATIA_CF_YML"; rm -f "$TMP_YML"
                CF_BIN="$(command -v cloudflared)"
                TMP_SVC="$(mktemp)"
                cat > "$TMP_SVC" <<EOF
[Unit]
Description=Cloudflare Tunnel for Bidatia (bidatia.xyz)
After=network.target

[Service]
Type=simple
ExecStart=$CF_BIN tunnel --no-autoupdate --config $BIDATIA_CF_YML run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
                sudo install -m 644 -o root -g root "$TMP_SVC" "/etc/systemd/system/$BIDATIA_CF_SVC.service"; rm -f "$TMP_SVC"
                sudo "$SYSTEMCTL" daemon-reload
                if confirm "Enable & start $BIDATIA_CF_SVC now?"; then
                    sudo "$SYSTEMCTL" enable --now "$BIDATIA_CF_SVC"
                    SUM_CF="$(systemctl is-active "$BIDATIA_CF_SVC" 2>/dev/null || echo unknown)"
                    ok "Tunnel service started."
                else
                    SUM_CF="scaffolded (not started)"
                    info "Start later:  sudo systemctl enable --now $BIDATIA_CF_SVC"
                fi
            fi
        else
            SUM_CF="not configured (manual)"
        fi
    fi
fi

# ── 11. Summary ─────────────────────────────────────────────────────────────
step "Deployment summary"
svc_state() { systemctl is-active "$1" 2>/dev/null || echo "n/a"; }
cat <<EOF
    ${B}Server path${R}        : $DEPLOY_PATH  (user $APP_USER)
    ${B}Git revision${R}       : $SUM_GITREV  (branch $GIT_BRANCH)
    ${B}Python${R}             : $SUM_PY
    ${B}WSGI module${R}        : $WSGI_MODULE  →  $BIND_ADDR
    ${B}Django check${R}       : $SUM_CHECK
    ${B}Migrations${R}         : $SUM_MIGRATE
    ${B}Collectstatic${R}      : $SUM_STATIC
    ${B}Service: bidatia${R}   : $(svc_state bidatia)
    ${B}Celery worker${R}      : $(svc_state bidatia-celery-worker)  ($SUM_CELERY)
    ${B}Celery beat${R}        : $(svc_state bidatia-celery-beat)
    ${B}Health (local)${R}     : $SUM_HEALTH
    ${B}Cloudflare tunnel${R}  : $SUM_CF
EOF
# Best-effort public check (won't fail the script).
if curl -fsS --max-time 6 -o /dev/null "https://bidatia.xyz/healthz/" 2>/dev/null; then
    ok "Public check: https://bidatia.xyz/healthz/ responded 2xx."
else
    info "Public https://bidatia.xyz not reachable from the server yet (DNS/tunnel may be pending)."
fi

if [[ "$SUM_HEALTH" == OK* ]]; then
    printf '\n%s\n' "${GRN}${B}Bidatia deployment finished. The app is live on $BIND_ADDR.${R}"
    exit 0
else
    printf '\n%s\n' "${YEL}${B}Deployment finished with warnings — review the health check above.${R}"
    exit 1
fi
