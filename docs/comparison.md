# AdClaw vs Alternatives

> How AdClaw compares to other AI agent frameworks and the OpenClaw ecosystem.

AdClaw is a fully reworked fork of [CoPaw](https://github.com/agentscope-ai/CoPaw), rebuilt for marketing teams with multi-persona architecture, enterprise-grade memory, and 118 built-in security-scanned skills.

## Quick Comparison

| Capability | AdClaw | OpenClaw | Hermes Agent | CoPaw | CrewAI | Dify |
|---|---|---|---|---|---|---|
| **Focus** | AI Marketing Team | Personal Agent | Self-Learning Agent | Personal Agent | Multi-Agent Framework | LLM App Platform |
| **Multi-Agent** | Personas + coordinator | Single agent | Subagent dispatch | Single agent | Role-based crews | No |
| **Built-in Skills** | 118 (security-scanned) | 13,700+ (community) | 40+ | ~50 | Custom | Plugins |
| **Marketing Tools** | 52 via Citedy MCP | None | None | None | None | None |
| **Chat Channels** | 7 | 20+ | 5 (TG, Discord, Slack, WA, Signal) | 5 | API only | API + Web |
| **Web Dashboard** | Yes (personas, tabs, cron) | Basic | CLI/TUI | Basic | No | Yes |
| **Memory** | Dual: ReMe + AOM (vector+FTS) | Markdown files | 3-layer (episodic+semantic+procedural) | ReMe | Short-term | RAG |
| **Memory Optimization** | R1-R4 (4 layers) | None | LLM summarization | None | None | None |
| **Self-Learning** | Partial (skill-creator + auto-heal) | No | Yes (auto skill creation) | No | No | No |
| **Security Scanner** | 208 patterns + LLM audit | None (820+ malicious skills found) | Command approval + container isolation | None | None | None |
| **Self-Healing Skills** | Yes | No | Self-evolution (DSPy+GEPA) | No | No | No |
| **Cron Scheduling** | Per-persona | Plugin-based | Yes | Basic | No | No |
| **Distributed Tasks** | AgentHub (karma economy) | No | No | No | No | No |
| **Deployment** | pip / Docker (single container) | pip / Docker | 6 backends (local, Docker, SSH, serverless) | pip | pip | Docker |
| **Cold Start** | ~5s | ~3s | <200ms | ~3s | ~3s | ~10s |
| **License** | Apache 2.0 | MIT | MIT | Apache 2.0 | MIT | Various |

## The OpenClaw Ecosystem

OpenClaw (247K stars) created the "personal AI agent" paradigm. Several projects extend or compete with it:

| Project | Stars | What it does | AdClaw advantage |
|---|---|---|---|
| **OpenClaw** | 247K | Personal agent, 13,700+ community skills | Security: our 208-pattern scanner vs their 820+ malicious skills crisis |
| **nanobot** | 33.6K | Ultra-lightweight OpenClaw in 4,000 lines | We have a full Web UI, multi-persona, marketing tools |
| **NanoClaw** | 21K | Containerized agent on Claude SDK | We support 22 LLM providers, not just Claude |
| **Hermes Agent** | 7.4K | Self-learning agent with 3-layer memory | We have marketing-specific skills (118) and AgentHub |
| **ClawWork** | 6.7K | AI agents that earn real money | Our AgentHub karma economy is a lighter version of this |
| **OpenClaw MC** | 2.4K | Governance dashboard for agent fleets | We have built-in dashboard, not a separate tool |
| **ClawBands** | — | Security middleware (human-in-the-loop) | Our security is built-in, not middleware |
| **clawsec** | — | Security skills for OpenClaw | Our scanner runs automatically on every skill |

## What AdClaw Adds Over CoPaw

AdClaw started as a CoPaw fork but was reworked extensively (~80% rewritten):

- **+68 skills** (118 total) — SEO, ads, content, social media, growth hacking, analytics
- **Multi-agent personas** — each with own identity (SOUL.md), LLM, skills, MCP tools, and cron schedule
- **@tag routing** — `@researcher find AI trends` in Telegram or Web chat
- **Coordinator delegation** — one agent orchestrates the rest automatically
- **Dashboard page** — persona status cards with model, skills, cron preview
- **Per-persona chat tabs** — isolated sessions with shared memory
- **Always-On Memory (AOM)** — vector search, FTS5, consolidation engine, 4-layer optimization
- **Memory sanitizer** — 33 threat patterns across 7 categories
- **Skill security scanner** — 208 patterns, LLM audit, auto-heal
- **AgentHub integration** — distributed tasks with karma economy
- **here.now file publishing** — instant shareable links for any file
- **Citedy MCP server** — 52 marketing tools (SEO, trends, competitor analysis, lead magnets)
- **22 LLM providers, 100+ models** — OpenAI, Anthropic, Gemini, OpenRouter, DeepSeek, Groq, Cerebras, Together, Mistral, Baseten, MiniMax, Inception, Moonshot, xAI, Aliyun, DashScope, Ollama, llama.cpp, MLX, and more
- **LLM auto-fallback** — configurable chain with timeout; if primary model fails, auto-switch to backup
- **OpenRouter routing** — auto, nitro, free, floor modes for optimal cost/speed
- **English-only UI** — removed all Chinese text from console and runtime

## AdClaw vs Hermes Agent

Hermes Agent (by Nous Research, 7.4K stars) is the closest competitor in philosophy:

| Dimension | AdClaw | Hermes Agent |
|---|---|---|
| Self-learning | No (manual skills) | Yes (auto skill creation from experience) |
| Self-evolution | Skill auto-fix (patch_skill_script) | DSPy + GEPA prompt evolution |
| Memory | ReMe + AOM (vector + FTS5 + consolidation) | Episodic (FTS5) + Semantic (Honcho) + Procedural (skills) |
| Skills count | 118 built-in | 40+ bundled |
| Marketing tools | 52 via Citedy MCP | None |
| Channels | Telegram, Discord, DingTalk, Feishu, QQ, Console | Telegram, Discord, Slack, WhatsApp, Signal |
| Asian market channels | DingTalk, Feishu, QQ | None |
| Dashboard | Web UI with persona tabs | CLI/TUI only |
| Distributed tasks | AgentHub (karma economy) | No |
| RL training | No | Yes (Atropos integration) |
| Cold start | ~5s | <200ms |
| Migration from OpenClaw | N/A | Built-in (`hermes claw migrate`) |
| License | Apache 2.0 | MIT |

## When to Use What

| Use Case | Best Choice |
|----------|------------|
| AI marketing team with multiple specialists | **AdClaw** |
| Distributed task optimization with agent competition | **AdClaw + AgentHub** |
| Self-learning personal agent that grows with you | Hermes Agent |
| Maximum community skills (13,700+) | OpenClaw |
| Ultra-lightweight personal agent | nanobot |
| Personal AI assistant (single agent) | CoPaw |
| Custom multi-agent workflows (code-first) | CrewAI |
| No-code LLM app builder | Dify |
| Enterprise agent orchestration | Microsoft Agent Framework |
| Agent fleet governance with approvals | OpenClaw Mission Control |

---

*Last updated: 2026-03-24*
