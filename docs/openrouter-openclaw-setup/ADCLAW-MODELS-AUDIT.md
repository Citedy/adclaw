# AI Providers Connection & Model Technical Inventory

This document provides the technical details required to connect to each AI provider and a complete list of technical model IDs supported by the platform.

## 1. Connection Configurations

| Provider | Environment Variable | API Base URL / Endpoint | Auth Method |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `OPENAI_API_KEY` | `https://api.openai.com/v1/chat/completions` | Bearer Token |
| **Anthropic** | `ANTHROPIC_API_KEY` | `https://api.anthropic.com/v1/messages` | `x-api-key` header |
| **Gemini** | `GOOGLE_GENERATIVE_AI_API_KEY` | `https://generativelanguage.googleapis.com/v1beta/models` | Query Param `key` |
| **OpenRouter** | `OPENROUTER_API_KEY` | `https://openrouter.ai/api/v1/chat/completions` | Bearer Token |
| **Alibaba (DashScope)** | `DASHSCOPE_API_KEY` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions` | Bearer Token |
| **Cerebras** | `CEREBRAS_API_KEY` | `https://api.cerebras.ai/v1/chat/completions` | Bearer Token |
| **DeepSeek** | `DEEPSEEK_API_KEY` | `https://api.deepseek.com/v1/chat/completions` | Bearer Token |
| **Groq** | `GROQ_API_KEY` | `https://api.groq.com/openai/v1/chat/completions` | Bearer Token |
| **xAI (Grok)** | `XAI_API_KEY` | `https://api.x.ai/v1/chat/completions` | Bearer Token |
| **Together AI** | `TOGETHER_API_KEY` | `https://api.together.xyz/v1/chat/completions` | Bearer Token |
| **Mistral** | `MISTRAL_API_KEY` | `https://api.mistral.ai/v1/chat/completions` | Bearer Token |
| **Moonshot AI** | `MOONSHOT_API_KEY` | `https://api.moonshot.ai/v1/chat/completions` | Bearer Token |
| **Minimax AI** | `MINIMAX_API_KEY` | `https://api.minimaxi.chat/v1/text/chatcompletion_v2` | Bearer Token |
| **Baseten** | `BASETEN_API_KEY` | `https://inference.baseten.co/v1/chat/completions` | Bearer Token |
| **Inception Labs** | `INCEPTION_API_KEY` | `https://api.inceptionlabs.ai/v1/chat/completions` | Bearer Token |

---

## 2. Technical Model Names (per Provider)

These are the `id` values used in the `AI_MODELS` configuration in `lib/ai/config.ts`.

### OpenAI

- `gpt-5.4` (Flagship Reasoning & Coding)
- `gpt-5.3-codex` (Flagship Coding)
- `gpt-5` (Multimodal & Reasoning)
- `gpt-5-mini` (Fast & Cost-efficient)
- `gpt-4.1` (Long Context)
- `gpt-4o-mini` (Lightweight, production-ready)

### Anthropic

- `claude-opus-4-6` (Opus 4.6 — strongest, coding & reasoning, 1M context)
- `claude-sonnet-4-6` (Sonnet 4.6 — fast, coding & agents, 1M context)
- `claude-haiku-4-6` (Haiku 4.6 — ultra-fast, cost-efficient, everyday tasks)

### Gemini (Google)

- `gemini-3.1-pro-preview` (Pro 3.1 — flagship reasoning & multimodal)
- `gemini-3-flash-preview` (Flash 3 — frontier-class performance, cost-efficient)
- `gemini-3.1-flash-lite-preview` (Flash-Lite 3.1 — fastest, high-volume tasks)

### xAI (Grok)

- `grok-4-fast-non-reasoning` (Grok 4 — fast, non-reasoning mode)

### Groq

- `llama-3.3-70b-versatile`
- `llama-3.1-8b-instant`
- `moonshotai/Kimi-K2-Instruct-0905`
- `openai/gpt-oss-120b`

### DeepSeek

- `deepseek-chat` (DeepSeek-V3.2 — 128K context)
- `deepseek-reasoner` (DeepSeek-R1 — reasoning model)

### Cerebras

- `llama3.1-8b` (Production — fast, lightweight)
- `gpt-oss-120b` (Production — OpenAI OSS 120B)
- `qwen-3-235b-a22b-instruct-2507` (Preview — Qwen 3 235B)
- `zai-glm-4.7` (Preview — Z.ai GLM 4.7)

### Baseten

- `zai-org/GLM-4.6` (Zhipu AI)
- `deepseek-ai/DeepSeek-V3.2` (DeepSeek Optimized)
- `nvidia/Nemotron-120B-A12B`
- `moonshotai/Kimi-K2.5`
- `MiniMaxAI/MiniMax-M2.5`
- `zai-org/GLM-5`

### Moonshot AI

- `kimi-k2.5` (Kimi K2.5 — most intelligent, multimodal, agentic)

### Minimax AI

- `MiniMax-M2.5` (MiniMax-M2.5 — latest text generation)

### Inception Labs

- `mercury-2` (Mercury 2 — fastest reasoning LLM)

### Alibaba (DashScope)

- `qwen3.5-plus` — новейшая модель (февраль 2026), 1M контекст, thinking mode по умолчанию
- `qwen-plus-latest` (qwen3 серия) — до 1M токенов контекста, reasoning + обычный режим
- `qwq-plus` — reasoning-модель (замена qwen-qwq-32b-preview), 131K контекст
- `qwen-max-latest` — предыдущий флагман, 32K контекст
- `qwen3-omni-flash`
- `qwen3-coder-plus`
- `qwen-mt-plus`

### OpenRouter

- `google/gemini-2.5-flash-lite`
- `minimax/minimax-m2.5`
- `google/gemini-3-flash-preview`
- `moonshotai/kimi-k2.5`
- `anthropic/claude-opus-4.6`
- `deepseek/deepseek-v3.2`
- `qwen/qwen3-32b:nitro`
- `openai/gpt-5.3-codex`
- `openai/gpt-5.4`
- `openai/gpt-5.1`
- `openai/gpt-5.2`
- `anthropic/claude-sonnet-4.6`
- `openai/gpt-4o-mini`
- `openai/gpt-oss-120b`
- `openai/gpt-5-nano`

# Aliyun Coding Plan - no changes
# Z.AI - no changes

Aliyun Coding (Intl) and Aliyun Coding Plan and some Chinese stuff - need to organize. We only need Aliyun Coding Plan and Aliyun Coding (Intl)

What is the difference between DashScope and ModelScope?