# Getting Started with AdClaw

AdClaw is an AI marketing assistant powered by [Citedy](https://www.citedy.com). It comes with 96 built-in skills (SEO, ads, content, social media, analytics, and more), 52 MCP tools, and works out of the box via Telegram or web chat.

## Quick Install

```bash
curl -sSL https://raw.githubusercontent.com/nttylock/AdClaw/main/install.sh | bash
```

Or with Docker Compose:

```bash
git clone https://github.com/nttylock/AdClaw.git
cd AdClaw
cp .env.example .env
# Edit .env with your keys
docker compose up -d
```

## Manual Docker Run

```bash
docker run -d --name adclaw \
  --restart unless-stopped \
  -p 8088:8088 \
  -v adclaw-data:/app/working \
  -e CITEDY_API_KEY=your_citedy_agent_key \
  -e TELEGRAM_BOT_TOKEN=your_telegram_bot_token \
  nttylock/adclaw:latest
```

## First-Run Setup

1. Open `http://localhost:8088` in your browser
2. The welcome wizard will guide you through:
   - **Step 1:** Enter your Citedy API key (get one free at [citedy.com/developer](https://www.citedy.com/developer))
   - **Step 2:** Choose an LLM provider (OpenRouter recommended — one key for all models)
   - **Step 3:** Optionally connect a Telegram bot

## Get a Citedy API Key

1. Go to [citedy.com/developer](https://www.citedy.com/developer)
2. Sign up or log in
3. Copy your `citedy_agent_...` key
4. Paste it in the welcome wizard or set it as `CITEDY_API_KEY` env var

## Choose an LLM Provider

AdClaw needs a language model to generate responses. Supported providers:

| Provider | Best For | Get Key |
|----------|----------|---------|
| **OpenRouter** (recommended) | One key for Claude, GPT, Gemini, Llama | [openrouter.ai](https://openrouter.ai) |
| **OpenAI** | GPT-5, o3, GPT-4o | [platform.openai.com](https://platform.openai.com) |
| **Anthropic** | Claude Opus, Sonnet, Haiku | [console.anthropic.com](https://console.anthropic.com) |
| **Aliyun Intl** | Qwen3.5, GLM-5, Kimi (free trial) | [dashscope.aliyuncs.com](https://dashscope.aliyuncs.com) |
| **Ollama** | Local models, no API key | [ollama.com](https://ollama.com) |

Configure via the welcome wizard, web UI (`/models`), or ask the bot: "switch to GPT-5".

## Connect Telegram

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Create a new bot with `/newbot`
3. Copy the bot token
4. Set it as `TELEGRAM_BOT_TOKEN` env var or configure in the web UI (`/channels`)

## What's Included

### Pre-installed Skills
- **SEO Agent** — full-stack SEO: keyword research, content briefs, optimization
- **Content Writer** — blog autopilot with SEO optimization
- **Content Ingestion** — ingest URLs into structured content
- **Trend Scout** — scout X/Twitter and Reddit for trending topics
- **Lead Magnets** — generate ebooks, checklists, templates
- **Video Shorts** — create AI UGC short-form videos

### MCP Tools (52)
All Citedy MCP tools are available once you set your API key. The agent can use them automatically for keyword research, SERP analysis, content generation, and more.

## Next Steps

- [Configuration Guide](./configuration.md)
- [Skills Guide](./skills.md)
- [API Reference](./api-reference.md)
