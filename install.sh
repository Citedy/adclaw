#!/usr/bin/env bash
set -euo pipefail

# AdClaw — AI Marketing Assistant
# Install: curl -fsSL https://get.adclaw.app/install.sh | bash
#    or:   curl -fsSL https://raw.githubusercontent.com/Citedy/adclaw/main/install.sh | bash
#
# Options (env vars or flags):
#   --port 8088              Web UI port (default: 8088)
#   --telegram-token TOKEN   Telegram bot token (@BotFather)
#   --citedy-key KEY         Citedy API key (https://www.citedy.com/developer)
#   --channels "a,b,c"       Enabled channels (default: all)
#   --uninstall              Remove AdClaw container and optionally data
#   --update                 Pull latest image and restart

ADCLAW_IMAGE="nttylock/adclaw:latest"
ADCLAW_CONTAINER="adclaw"

# Defaults
PORT="${ADCLAW_PORT:-8088}"
TELEGRAM_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
CITEDY_KEY="${CITEDY_API_KEY:-}"
GITHUB_TOKEN_VAL="${GITHUB_TOKEN:-}"
TAVILY_KEY="${TAVILY_API_KEY:-}"
CHANNELS="${ADCLAW_ENABLED_CHANNELS:-discord,dingtalk,feishu,qq,console,telegram}"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
ACTION="install"

# ── Colors ───────────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    BOLD="\033[1m" GREEN="\033[32m" YELLOW="\033[33m" RED="\033[31m"
    CYAN="\033[36m" DIM="\033[2m" RESET="\033[0m"
else
    BOLD="" GREEN="" YELLOW="" RED="" CYAN="" DIM="" RESET=""
fi

info()  { printf "${GREEN}[adclaw]${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}[adclaw]${RESET} %s\n" "$*"; }
error() { printf "${RED}[adclaw]${RESET} %s\n" "$*" >&2; }
die()   { error "$@"; exit 1; }

# ── Parse flags ──────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)             PORT="$2"; shift 2 ;;
        --telegram-token)   TELEGRAM_TOKEN="$2"; shift 2 ;;
        --citedy-key)       CITEDY_KEY="$2"; shift 2 ;;
        --channels)         CHANNELS="$2"; shift 2 ;;
        --uninstall)        ACTION="uninstall"; shift ;;
        --update)           ACTION="update"; shift ;;
        -h|--help)
            cat <<'EOF'
AdClaw Installer — AI Marketing Assistant

Usage:
  curl -fsSL https://get.adclaw.app/install.sh | bash
  bash install.sh [OPTIONS]

Options:
  --port PORT              Web UI port (default: 8088)
  --telegram-token TOKEN   Telegram bot token (from @BotFather)
  --citedy-key KEY         Citedy API key
  --channels "a,b,c"       Enabled channels
  --update                 Pull latest image and restart
  --uninstall              Remove container (asks about data)
  -h, --help               Show this help

Environment variables:
  ADCLAW_PORT, TELEGRAM_BOT_TOKEN, CITEDY_API_KEY,
  ADCLAW_ENABLED_CHANNELS, GITHUB_TOKEN, TAVILY_API_KEY, LOG_LEVEL

Examples:
  # Basic install
  curl -fsSL https://get.adclaw.app/install.sh | bash

  # With Telegram bot
  curl -fsSL https://get.adclaw.app/install.sh | bash -s -- --telegram-token "123:ABC"

  # Update to latest
  curl -fsSL https://get.adclaw.app/install.sh | bash -s -- --update
EOF
            exit 0 ;;
        *) die "Unknown option: $1 (try --help)" ;;
    esac
done

# ── Banner ───────────────────────────────────────────────────────────────────
printf "\n${BOLD}${CYAN}"
cat <<'BANNER'
     _       _  ____ _
    / \   __| |/ ___| | __ ___      __
   / _ \ / _` | |   | |/ _` \ \ /\ / /
  / ___ \ (_| | |___| | (_| |\ V  V /
 /_/   \_\__,_|\____|_|\__,_| \_/\_/

BANNER
printf "${RESET}${DIM}  AI Marketing Assistant${RESET}\n\n"

# ── Docker check ─────────────────────────────────────────────────────────────
ensure_docker() {
    if ! command -v docker &>/dev/null; then
        info "Docker not found. Installing..."
        if command -v curl &>/dev/null; then
            curl -fsSL https://get.docker.com | sh
        elif command -v wget &>/dev/null; then
            wget -qO- https://get.docker.com | sh
        else
            die "Neither curl nor wget found. Install Docker manually: https://docs.docker.com/get-docker/"
        fi
        info "Docker installed."
    fi

    if ! docker info &>/dev/null 2>&1; then
        # Try starting Docker daemon
        if command -v systemctl &>/dev/null; then
            warn "Docker daemon not running. Starting..."
            sudo systemctl start docker 2>/dev/null || true
            sleep 2
        fi
        docker info &>/dev/null 2>&1 || die "Docker daemon is not running. Start Docker and retry."
    fi
}

# ── Uninstall ────────────────────────────────────────────────────────────────
do_uninstall() {
    info "Uninstalling AdClaw..."

    if docker ps -a --format '{{.Names}}' | grep -q "^${ADCLAW_CONTAINER}$"; then
        docker rm -f "$ADCLAW_CONTAINER" >/dev/null 2>&1
        info "Container removed."
    else
        info "No container found."
    fi

    # Ask about volumes only if interactive
    if [ -t 0 ]; then
        printf "\n${YELLOW}Delete all data (config, sessions, API keys)?${RESET} [y/N] "
        read -r answer
        if [[ "$answer" =~ ^[Yy]$ ]]; then
            docker volume rm adclaw-data adclaw-secret 2>/dev/null || true
            info "Data volumes removed."
        else
            info "Data volumes preserved."
        fi
    else
        info "Data volumes preserved (run with --uninstall interactively to delete data)."
    fi

    printf "\n${GREEN}${BOLD}AdClaw uninstalled.${RESET}\n\n"
    exit 0
}

# ── Update ───────────────────────────────────────────────────────────────────
do_update() {
    ensure_docker
    info "Updating AdClaw..."

    info "Pulling ${ADCLAW_IMAGE}..."
    docker pull "$ADCLAW_IMAGE"

    if docker ps -a --format '{{.Names}}' | grep -q "^${ADCLAW_CONTAINER}$"; then
        # Capture current port mapping
        CURRENT_PORT=$(docker port "$ADCLAW_CONTAINER" 8088/tcp 2>/dev/null | head -1 | cut -d: -f2 || echo "$PORT")

        docker rm -f "$ADCLAW_CONTAINER" >/dev/null 2>&1
        info "Old container removed."

        # Re-run with same config from inspect
        # Simplified: just restart with known volumes
        docker run -d \
            --name "$ADCLAW_CONTAINER" \
            --restart unless-stopped \
            -p "${CURRENT_PORT:-$PORT}:8088" \
            -v adclaw-data:/app/working \
            -v adclaw-secret:/app/working.secret \
            -e "ADCLAW_ENABLED_CHANNELS=$CHANNELS" \
            -e "LOG_LEVEL=$LOG_LEVEL" \
            "$ADCLAW_IMAGE" >/dev/null

        info "Container restarted."
    else
        warn "No running container found. Run install first."
        exit 1
    fi

    printf "\n${GREEN}${BOLD}AdClaw updated!${RESET}\n"
    printf "  Web UI: ${BOLD}http://localhost:${CURRENT_PORT:-$PORT}${RESET}\n\n"
    exit 0
}

# ── Route action ─────────────────────────────────────────────────────────────
case "$ACTION" in
    uninstall) do_uninstall ;;
    update)    do_update ;;
esac

# ── Install ──────────────────────────────────────────────────────────────────
ensure_docker

# Check port availability
if command -v ss &>/dev/null; then
    if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
        EXISTING=$(docker ps --format '{{.Names}}' --filter "publish=${PORT}" 2>/dev/null | head -1)
        if [ "$EXISTING" = "$ADCLAW_CONTAINER" ]; then
            warn "AdClaw is already running on port ${PORT}."
            printf "\n  Update:    ${BOLD}curl -fsSL https://get.adclaw.app/install.sh | bash -s -- --update${RESET}\n"
            printf "  Uninstall: ${BOLD}curl -fsSL https://get.adclaw.app/install.sh | bash -s -- --uninstall${RESET}\n"
            printf "  Web UI:    ${BOLD}http://localhost:${PORT}${RESET}\n\n"
            exit 0
        else
            die "Port ${PORT} is already in use. Use --port to pick another: bash install.sh --port 9090"
        fi
    fi
elif command -v lsof &>/dev/null; then
    if lsof -iTCP:"${PORT}" -sTCP:LISTEN &>/dev/null 2>&1; then
        EXISTING=$(docker ps --format '{{.Names}}' --filter "publish=${PORT}" 2>/dev/null | head -1)
        if [ "$EXISTING" = "$ADCLAW_CONTAINER" ]; then
            warn "AdClaw is already running on port ${PORT}."
            exit 0
        else
            die "Port ${PORT} is already in use. Use --port to pick another."
        fi
    fi
fi

# Stop existing container if present
if docker ps -a --format '{{.Names}}' | grep -q "^${ADCLAW_CONTAINER}$"; then
    info "Removing existing container..."
    docker rm -f "$ADCLAW_CONTAINER" >/dev/null 2>&1
fi

# Pull image
info "Pulling ${ADCLAW_IMAGE}..."
docker pull "$ADCLAW_IMAGE"

# Build run command
RUN_ARGS=(
    -d
    --name "$ADCLAW_CONTAINER"
    --restart unless-stopped
    -p "${PORT}:8088"
    -v adclaw-data:/app/working
    -v adclaw-secret:/app/working.secret
    -e "ADCLAW_ENABLED_CHANNELS=${CHANNELS}"
    -e "LOG_LEVEL=${LOG_LEVEL}"
)

[ -n "$CITEDY_KEY" ]       && RUN_ARGS+=(-e "CITEDY_API_KEY=${CITEDY_KEY}")
[ -n "$TELEGRAM_TOKEN" ]   && RUN_ARGS+=(-e "TELEGRAM_BOT_TOKEN=${TELEGRAM_TOKEN}")
[ -n "$GITHUB_TOKEN_VAL" ] && RUN_ARGS+=(-e "GITHUB_TOKEN=${GITHUB_TOKEN_VAL}")
[ -n "$TAVILY_KEY" ]       && RUN_ARGS+=(-e "TAVILY_API_KEY=${TAVILY_KEY}")

# Launch
info "Starting AdClaw..."
docker run "${RUN_ARGS[@]}" "$ADCLAW_IMAGE" >/dev/null

# Wait for container to be healthy
info "Waiting for startup..."
for i in $(seq 1 15); do
    if docker ps --format '{{.Names}}' | grep -q "^${ADCLAW_CONTAINER}$"; then
        # Check if the web server is responding
        if command -v curl &>/dev/null && curl -sf "http://localhost:${PORT}/" >/dev/null 2>&1; then
            break
        fi
    fi
    sleep 1
done

# Verify running
if ! docker ps --format '{{.Names}}' | grep -q "^${ADCLAW_CONTAINER}$"; then
    error "Container failed to start. Logs:"
    docker logs "$ADCLAW_CONTAINER" 2>&1 | tail -20
    die "Installation failed."
fi

# ── Success ──────────────────────────────────────────────────────────────────
# Detect external IP for remote servers
EXTERNAL_IP=""
if [ ! -t 0 ] || [ -f /.dockerenv ] || [ "${SSH_CONNECTION:-}" != "" ]; then
    EXTERNAL_IP=$(curl -sf --max-time 3 https://ifconfig.me 2>/dev/null || curl -sf --max-time 3 https://api.ipify.org 2>/dev/null || true)
fi

printf "\n${GREEN}${BOLD}AdClaw is running!${RESET}\n\n"
printf "  ${BOLD}Web UI:${RESET}    http://localhost:${PORT}\n"
if [ -n "$EXTERNAL_IP" ]; then
    printf "  ${BOLD}Remote:${RESET}    http://${EXTERNAL_IP}:${PORT}\n"
fi
if [ -n "$TELEGRAM_TOKEN" ]; then
    printf "  ${BOLD}Telegram:${RESET}  Bot is active\n"
fi
printf "\n"
printf "  ${DIM}Logs:${RESET}      docker logs -f adclaw\n"
printf "  ${DIM}Stop:${RESET}      docker stop adclaw\n"
printf "  ${DIM}Update:${RESET}    curl -fsSL https://get.adclaw.app/install.sh | bash -s -- --update\n"
printf "  ${DIM}Uninstall:${RESET} curl -fsSL https://get.adclaw.app/install.sh | bash -s -- --uninstall\n"
printf "\n"
printf "  ${CYAN}Next step:${RESET} Open the Web UI and configure your LLM provider.\n"
printf "  ${CYAN}Docs:${RESET}      https://github.com/Citedy/adclaw#readme\n\n"
