# -----------------------------------------------------------------------------
# Stage 1: build console frontend (dist not committed in repo).
# -----------------------------------------------------------------------------
FROM agentscope-registry.ap-southeast-1.cr.aliyuncs.com/agentscope/node:slim AS console-builder
WORKDIR /app
COPY console /app/console
RUN mkdir -p /app/src/adclaw/console
RUN cd /app/console && npm ci --include=dev && NODE_OPTIONS="--max-old-space-size=3072" npm run build

# -----------------------------------------------------------------------------
# Stage 2: runtime image with Python, Chromium, and app.
# -----------------------------------------------------------------------------
FROM agentscope-registry.ap-southeast-1.cr.aliyuncs.com/agentscope/node:slim

# ENV variables
ENV NODE_ENV=production
ENV WORKSPACE_DIR=/app
ENV ADCLAW_WORKING_DIR=/app/working

# Available channels for this image (imessage & discord excluded).
# Override at runtime with -e ADCLAW_ENABLED_CHANNELS=... if needed.
ARG ADCLAW_ENABLED_CHANNELS="discord,dingtalk,feishu,qq,console,telegram"
ENV ADCLAW_ENABLED_CHANNELS=${ADCLAW_ENABLED_CHANNELS}

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --fix-missing \
    curl  \
    python3  \
    python3-pip  \
    python3-venv \
    build-essential  \
    libssl-dev  \
    git  \
    supervisor  \
    vim  \
    gettext-base \
    xfce4 \
    xfce4-terminal \
    xvfb \
    dbus-x11 \
    fonts-wqy-zenhei \
    fonts-wqy-microhei \
  && rm -rf /var/lib/apt/lists/* \
  && apt-get clean


RUN apt-get update && apt-get install -y --fix-missing \
    chromium \
    chromium-sandbox \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxtst6 \
    libnss3 \
    libglib2.0-0 \
    libdrm2 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    libu2f-udev \
  && rm -rf /var/lib/apt/lists/* \
  && apt-get clean


RUN sed -i 's/^CHROMIUM_FLAGS=""/CHROMIUM_FLAGS="--no-sandbox"/' /usr/bin/chromium

# PinchTab: token-efficient browser control for AI agents (12MB Go binary).
# Install as root, then copy binary to /usr/local/bin so the adclaw user can run it.
RUN curl -fsSL https://pinchtab.com/install.sh | bash \
  && cp /root/.pinchtab/bin/*/pinchtab-linux-* /usr/local/bin/pinchtab-bin \
  && chmod 755 /usr/local/bin/pinchtab-bin
ENV PINCHTAB_PORT=9867

# agent-browser: install CLI globally, use system Chromium (skip download).
ENV AGENT_BROWSER_EXECUTABLE_PATH=/usr/bin/chromium
RUN npm install -g agent-browser sitefetch

# Playwright: use system Chromium (already installed above).
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium
# Avoid Playwright downloading its own browser when executable_path is used.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
# Indicate running in container (used e.g. for Chromium --no-sandbox).
ENV ADCLAW_RUNNING_IN_CONTAINER=1

WORKDIR ${WORKSPACE_DIR}

RUN python3 -m venv venv
ENV PATH="/app/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY src ./src
# Inject console dist from build stage (vite outputs to ../src/adclaw/console/).
COPY --from=console-builder /app/src/adclaw/console/ ./src/adclaw/console/
# Install CPU-only PyTorch first (avoids downloading 2GB CUDA build),
# then install app with [local] extras (sentence-transformers for AOM embeddings).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
  && pip install --no-cache-dir ".[local]"

# Non-root user for running the app (supervisord stays root for system services).
RUN groupadd -r adclaw && useradd -r -g adclaw -m -s /bin/bash adclaw \
  && mkdir -p /app/working /app/working.secret /app/logs /home/adclaw/.config/pinchtab \
  && chown -R adclaw:adclaw /app/working /app/working.secret /app/logs /home/adclaw/.config

# Config.json is generated at runtime by entrypoint.sh (only if missing),
# so it persists user settings across container restarts.

# AdClaw app port (default 8088). Override at runtime with -e ADCLAW_PORT=3000.
ENV ADCLAW_PORT=8088

COPY deploy/config/supervisord.conf.template /etc/supervisor/conf.d/supervisord.conf.template
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod 755 /entrypoint.sh

EXPOSE 8088

CMD ["/entrypoint.sh"]
