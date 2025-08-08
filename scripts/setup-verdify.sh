#!/usr/bin/env bash
set -euo pipefail

### ====== CONFIG (edit before first run) ======
DOMAIN="your-domain.tld"                # Base domain, e.g. example.com
ADMIN_EMAIL="admin@your-domain.tld"     # Initial superuser email
EMAIL_FROM="noreply@your-domain.tld"    # From email
REPO_URL="https://github.com/jvallery/verdify.git"
REPO_DIR="/opt/verdify/repo"            # Clone location on swarm manager
ENV_FILE="/opt/verdify/.env"            # External .env stored outside repo
STACK_NAME="verdify"
BACKEND_IMAGE="ghcr.io/jvallery/verdify-backend"
FRONTEND_IMAGE="ghcr.io/jvallery/verdify-frontend"
TAG="latest"                            # Can pin to a commit SHA for rollback
GHCR_USER="jvallery"                    # For docker login if needed
GHCR_PAT="${GHCR_PAT:-}"                # export GHCR_PAT=... before running (optional)
### ===========================================

log() { printf '[%s] %s\n' "$(date +'%Y-%m-%dT%H:%M:%S')" "$*" >&2; }
need_bin() { command -v "$1" >/dev/null || { echo "Missing required binary: $1" >&2; exit 1; }; }

create_secret() {
  local name="$1"; local genlen="${2:-48}";
  if docker secret inspect "$name" >/dev/null 2>&1; then
    log "Secret $name already exists (skip)"
  else
    local val
    val="$(python3 - <<PY
import secrets; print(secrets.token_urlsafe($genlen))
PY
)"
    printf '%s' "$val" | docker secret create "$name" -
    log "Created secret $name"
  fi
}

ensure_overlay_net() {
  local net="$1";
  if docker network ls --format '{{.Name}}' | grep -qx "$net"; then
    log "Network $net exists"
  else
    docker network create --driver overlay --attachable "$net"
    log "Created overlay network $net"
  fi
}

write_env() {
  if [ -f "$ENV_FILE" ]; then
    log ".env already exists (skip)"
    return
  fi
  mkdir -p "$(dirname "$ENV_FILE")"
  cat > "$ENV_FILE" <<EOF
PROJECT_NAME=Verdify
STACK_NAME=$STACK_NAME
DOMAIN=$DOMAIN
FRONTEND_HOST=https://dashboard.$DOMAIN
ENVIRONMENT=production
BACKEND_CORS_ORIGINS=["https://dashboard.$DOMAIN"]
POSTGRES_SERVER=db
POSTGRES_PORT=5432
POSTGRES_USER=verdify
POSTGRES_DB=verdify
FIRST_SUPERUSER=$ADMIN_EMAIL
EMAILS_FROM_EMAIL=$EMAIL_FROM
DOCKER_IMAGE_BACKEND=$BACKEND_IMAGE
DOCKER_IMAGE_FRONTEND=$FRONTEND_IMAGE
TAG=$TAG
EOF
  chmod 600 "$ENV_FILE"
  log "Wrote $ENV_FILE"
}

clone_or_update_repo() {
  if [ -d "$REPO_DIR/.git" ]; then
    log "Updating repo..."
    git -C "$REPO_DIR" fetch --all --prune
    git -C "$REPO_DIR" checkout main
    git -C "$REPO_DIR" pull --ff-only
  else
    log "Cloning repo..."
    mkdir -p "$(dirname "$REPO_DIR")"
    git clone "$REPO_URL" "$REPO_DIR"
  fi
}

docker_login_ghcr() {
  if [ -n "$GHCR_PAT" ]; then
    echo "$GHCR_PAT" | docker login ghcr.io -u "$GHCR_USER" --password-stdin
    log "Logged in to GHCR"
  else
    log "GHCR_PAT not set; skipping GHCR login (ensure runner already authenticated)"
  fi
}

deploy_stack() {
  cp "$ENV_FILE" "$REPO_DIR/.env"
  (cd "$REPO_DIR" && docker stack deploy -c docker-compose.yml "$STACK_NAME")
  log "Stack deployed: $STACK_NAME"
  docker stack services "$STACK_NAME"
}

print_rollback_help() {
  cat <<EOT
Rollback examples:
  docker service update --image ${BACKEND_IMAGE}:<previous-sha> ${STACK_NAME}_backend
  docker service update --image ${FRONTEND_IMAGE}:<previous-sha> ${STACK_NAME}_frontend
Pin a specific release:
  sed -i 's/^TAG=.*/TAG=<commit-sha>/' $ENV_FILE && cp $ENV_FILE $REPO_DIR/.env && \
  (cd $REPO_DIR && docker stack deploy -c docker-compose.yml $STACK_NAME)
Secret rotation:
  printf '%s' "$(python3 - <<'PY';import secrets;print(secrets.token_urlsafe(48));PY)" | docker secret create verdify_secret_key_v2 -
  # Edit compose to use verdify_secret_key_v2, deploy, then:
  docker secret rm verdify_secret_key
EOT
}

main() {
  need_bin docker; need_bin python3; need_bin git

  log "Writing env file (if absent)"; write_env
  log "Creating / validating secrets";
  create_secret verdify_secret_key 64
  create_secret verdify_first_superuser_password 40
  create_secret verdify_postgres_password 40
  create_secret verdify_smtp_password 32

  log "Ensuring traefik-public overlay network"; ensure_overlay_net traefik-public
  log "Clone / update repository"; clone_or_update_repo
  log "GHCR login (optional)"; docker_login_ghcr
  log "Pre-pull images (optional)"; docker pull "${BACKEND_IMAGE}:${TAG}" || true; docker pull "${FRONTEND_IMAGE}:${TAG}" || true
  log "Deploy stack"; deploy_stack
  print_rollback_help
  log "Done. Check logs: docker service logs -f ${STACK_NAME}_backend"
}

main "$@"
