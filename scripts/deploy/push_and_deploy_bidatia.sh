#!/usr/bin/env bash
#
# push_and_deploy_bidatia.sh — run from your Mac.
#
# 1. Validates this is the Bidatia repo, on `main`, with the right remote.
# 2. Commits (with your confirmation) and pushes to origin/main.
# 3. Asks for SSH details, copies the server script up, and runs it over an
#    interactive SSH session (so the server-side prompts work normally).
#
# Nothing destructive happens without a confirmation. No secrets are stored
# or printed. Private keys are never embedded — SSH uses your agent/config or
# an identity file you point at.
# ----------------------------------------------------------------------------
set -uo pipefail

EXPECTED_REMOTE="git@github.com:dev1bms/bidatia.git"
DEFAULT_BRANCH="main"
DEFAULT_DEPLOY_PATH="/srv/bidatia/app"
DEFAULT_BIND="127.0.0.1:8020"
DEFAULT_COMMIT_MSG="Prepare Bidatia production deployment"

if [[ -t 1 ]]; then
    B=$'\033[1m'; R=$'\033[0m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; BLU=$'\033[34m'
else B=""; R=""; RED=""; GRN=""; YEL=""; BLU=""; fi
step() { printf '\n%s\n' "${B}${BLU}==> $*${R}"; }
info() { printf '    %s\n' "$*"; }
ok()   { printf '    %s%s%s\n' "$GRN" "✓ $*" "$R"; }
warn() { printf '    %s%s%s\n' "$YEL" "! $*" "$R"; }
die()  { printf '    %s%s%s\n' "$RED" "✗ $*" "$R" >&2; exit 1; }
confirm() { local a; read -rp "    $1 [y/N] " a; [[ "$a" =~ ^[Yy] ]]; }
ask() { local p="$1" def="${2:-}" v; read -rp "    ${p}${def:+ [${def}]}: " v; printf '%s' "${v:-$def}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SCRIPT="$SCRIPT_DIR/server_deploy_bidatia.sh"
[[ -f "$SERVER_SCRIPT" ]] || die "Cannot find server_deploy_bidatia.sh next to this script."

# ── 1. Validate the local repository ────────────────────────────────────────
step "Validating local repository"
command -v git >/dev/null || die "git is not installed."
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || die "Not inside a git repository."
cd "$REPO_ROOT"
[[ -f manage.py && -f bidatia/settings.py ]] || die "This does not look like the Bidatia repo (manage.py / bidatia/settings.py missing)."
ok "Repository root: $REPO_ROOT"

REMOTE_URL="$(git remote get-url origin 2>/dev/null || echo '')"
if [[ "$REMOTE_URL" == "$EXPECTED_REMOTE" ]]; then
    ok "origin = $REMOTE_URL"
else
    warn "origin is '$REMOTE_URL' (expected '$EXPECTED_REMOTE')."
    if confirm "Set origin to $EXPECTED_REMOTE?"; then
        if git remote >/dev/null 2>&1 && [[ -n "$REMOTE_URL" ]]; then git remote set-url origin "$EXPECTED_REMOTE";
        else git remote add origin "$EXPECTED_REMOTE"; fi
        ok "origin set."
    else
        die "Refusing to push to an unexpected remote."
    fi
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "$DEFAULT_BRANCH" ]]; then
    warn "Current branch is '$BRANCH', not '$DEFAULT_BRANCH'."
    confirm "Switch to $DEFAULT_BRANCH?" && { git checkout "$DEFAULT_BRANCH" || die "Could not switch branch."; BRANCH="$DEFAULT_BRANCH"; } \
        || die "Deploy expects the '$DEFAULT_BRANCH' branch."
fi
ok "On branch '$BRANCH'."

# ── 2. Commit (if needed) and push ──────────────────────────────────────────
step "Git status"
git status --short
if [[ -n "$(git status --porcelain)" ]]; then
    warn "You have uncommitted changes."
    if confirm "Commit them now?"; then
        MSG="$(ask 'Commit message' "$DEFAULT_COMMIT_MSG")"
        git add -A
        git commit -m "$MSG" || die "Commit failed."
        ok "Committed."
    else
        confirm "Push without committing the working changes (only existing commits go up)?" \
            || die "Aborted — commit or stash your changes first."
    fi
else
    ok "Working tree clean."
fi

step "Pushing to origin/$DEFAULT_BRANCH"
PUSH_STATUS="ok"
if git push -u origin "$DEFAULT_BRANCH"; then
    ok "Pushed."
else
    PUSH_STATUS="FAILED"
    warn "Push failed. This is usually a permissions issue on the new repo."
    info "Grant your SSH key push access to $EXPECTED_REMOTE, then re-run, OR continue to deploy"
    info "the revision already on the server's remote."
    confirm "Continue to the server deploy anyway?" || die "Stopped after push failure."
fi

# ── 3. SSH connection details ───────────────────────────────────────────────
step "Production server connection"
SSH_HOST="$(ask 'SSH host (IP or hostname)' '')";  [[ -n "$SSH_HOST" ]] || die "SSH host is required."
SSH_PORT="$(ask 'SSH port' '22')"
SSH_USER="$(ask 'SSH user (sudo-capable)' '')";    [[ -n "$SSH_USER" ]] || die "SSH user is required."
DEPLOY_PATH="$(ask 'Deploy path on server' "$DEFAULT_DEPLOY_PATH")"
SSH_KEY="$(ask 'SSH identity file (blank = use agent/ssh config)' '')"

SSH_OPTS=(-p "$SSH_PORT" -o ConnectTimeout=15)
SCP_OPTS=(-P "$SSH_PORT" -o ConnectTimeout=15)
if [[ -n "$SSH_KEY" ]]; then
    [[ -f "$SSH_KEY" ]] || die "Identity file not found: $SSH_KEY"
    SSH_OPTS+=(-i "$SSH_KEY"); SCP_OPTS+=(-i "$SSH_KEY")
fi
SSH_TARGET="${SSH_USER}@${SSH_HOST}"

info "About to: copy server_deploy_bidatia.sh to $SSH_TARGET and run it interactively."
info "  deploy path : $DEPLOY_PATH"
info "  bind addr   : $DEFAULT_BIND"
info "  remote repo : $EXPECTED_REMOTE ($DEFAULT_BRANCH)"
confirm "Proceed with the server deployment?" || die "Stopped before connecting."

# Quick connectivity probe (non-fatal hint).
if ! ssh "${SSH_OPTS[@]}" -o BatchMode=yes "$SSH_TARGET" 'true' 2>/dev/null; then
    warn "Non-interactive SSH probe failed — you may be prompted for a password/passphrase."
fi

# ── 4. Copy + run the server script over an interactive session ─────────────
step "Uploading and running the server deployment"
REMOTE_TMP="/tmp/bidatia_server_deploy_$(date +%s).sh"
scp "${SCP_OPTS[@]}" "$SERVER_SCRIPT" "$SSH_TARGET:$REMOTE_TMP" || die "scp of the server script failed."
ok "Server script uploaded to $REMOTE_TMP"

REMOTE_ENV="DEPLOY_PATH='$DEPLOY_PATH' REPO_URL='$EXPECTED_REMOTE' GIT_BRANCH='$DEFAULT_BRANCH' BIND_ADDR='$DEFAULT_BIND'"
# -t forces a TTY so the server-side prompts (sudo, choices) work.
ssh -t "${SSH_OPTS[@]}" "$SSH_TARGET" "$REMOTE_ENV bash '$REMOTE_TMP'"
DEPLOY_RC=$?

# Clean up the uploaded script (best effort).
ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "rm -f '$REMOTE_TMP'" 2>/dev/null || true

# ── 5. Local summary ────────────────────────────────────────────────────────
step "Local summary"
info "Git push          : $PUSH_STATUS"
info "Server            : $SSH_TARGET:$DEPLOY_PATH"
info "Remote deploy exit: $DEPLOY_RC  ($([[ $DEPLOY_RC -eq 0 ]] && echo success || echo 'see warnings above'))"
if [[ $DEPLOY_RC -eq 0 ]]; then
    printf '\n%s\n' "${GRN}${B}Done. Bidatia is deployed. Verify: https://bidatia.xyz/${R}"
else
    printf '\n%s\n' "${YEL}${B}Finished with warnings. Re-read the server output above for next steps.${R}"
fi
exit "$DEPLOY_RC"
