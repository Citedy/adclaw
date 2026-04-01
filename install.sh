#!/usr/bin/env bash
set -euo pipefail

# AdClaw — AI Marketing Assistant
# Quick install: curl -sSL https://raw.githubusercontent.com/nttylock/AdClaw/main/install.sh | bash

ADCLAW_IMAGE="nttylock/adclaw:latest"
ADCLAW_PORT="${ADCLAW_PORT:-8088}"

echo "============================================"
echo "  AdClaw — AI Marketing Assistant Installer"
echo "============================================"
echo ""

# Check Docker
if ! command -v docker &>/dev/null; then
  echo "Docker is not installed. Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  echo "Docker installed."
fi

# Check Docker running
if ! docker info &>/dev/null; then
  echo "ERROR: Docker daemon is not running. Please start Docker and retry."
  exit 1
fi

# Prompt for Citedy API key
echo ""
echo "Get your free Citedy API key at: https://www.citedy.com/developer"
read -rp "Citedy API key (or press Enter to skip): " CITEDY_API_KEY

# Prompt for Telegram bot token
echo ""
echo "Create a Telegram bot via @BotFather to chat with AdClaw from your phone."
read -rp "Telegram bot token (or press Enter to skip): " TELEGRAM_BOT_TOKEN

# Stop existing container if present
if docker ps -a --format '{{.Names}}' | grep -q '^adclaw$'; then
  echo ""
  echo "Stopping existing AdClaw container..."
  docker stop adclaw && docker rm adclaw || true
fi

# Pull latest image
echo ""
echo "Pulling $ADCLAW_IMAGE ..."
docker pull "$ADCLAW_IMAGE"

# Build run command
RUN_ARGS=(
  -d
  --name adclaw
  --restart unless-stopped
  -p "${ADCLAW_PORT}:8088"
  -v adclaw-data:/app/working
  -e "ADCLAW_ENABLED_CHANNELS=discord,dingtalk,feishu,qq,console,telegram"
  -e "LOG_LEVEL=INFO"
)

[ -n "${CITEDY_API_KEY:-}" ] && RUN_ARGS+=(-e "CITEDY_API_KEY=$CITEDY_API_KEY")
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] && RUN_ARGS+=(-e "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN")

echo ""
echo "Starting AdClaw..."
docker run "${RUN_ARGS[@]}" "$ADCLAW_IMAGE"

echo ""
echo "============================================"
echo "  AdClaw is running!"
echo ""
echo "  Web UI:   http://localhost:${ADCLAW_PORT}"
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
echo "  Telegram: Bot is active"
fi
echo ""
echo "  Manage:   docker logs -f adclaw"
echo "  Stop:     docker stop adclaw"
echo "  Update:   docker pull $ADCLAW_IMAGE && docker stop adclaw && docker rm adclaw"
echo "            Then re-run this script."
echo "============================================"
