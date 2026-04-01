# We Built a Multi-Agent System Where AI Agents Actually Work as a Team

Most "multi-agent" setups are just one LLM calling itself in a loop. We wanted something different — agents with persistent identity, memory, skills, and a coordinator that actually delegates.

Here's what we shipped in AdClaw this week.

## The Problem

Single-agent setups hit a wall fast. You either get a bloated system prompt trying to do everything, or you manually switch between specialized prompts. Neither scales. Neither remembers context across tasks.

We needed agents that:
- Have distinct roles and personalities
- Remember what they've done
- Share information without stepping on each other
- Can be created, configured, and swapped without touching code

## What We Built

### Personas with SOUL.md

Every agent gets a SOUL.md — a markdown file that defines who they are. Not just "you are a helpful assistant." Real identity: role, tone, boundaries, domain expertise.

```
@coordinator — routes tasks, delegates to specialists
@researcher — digs into data, writes briefs
@mira (content-writer) — produces articles, social posts, copy
```

You create them from the web UI or API. Pick a name, write the soul, assign a model — done.

### @Tag Routing

Talk to any agent by name. Type `@mira write a blog post about X` and the message routes to the content-writer persona with her full context. The system matches by ID or name, case-insensitive.

Untagged messages? They go to the coordinator. The coordinator decides who handles it — or handles it directly.

### Sticky Sessions

Once you start talking to an agent, follow-up messages stay with them. No need to tag every message. The session remembers which persona you were talking to. Switch agents anytime with a new @tag.

### Three-Layer Team Memory

Most multi-agent systems have no memory — or one shared blob that turns into noise. We built three layers that work together:

**Layer 1 — ReMe (Session Memory).** Each conversation gets compacted and summarized automatically. Long dialogues don't overflow the context window — ReMe compresses them while preserving key facts. Semantic search lets agents pull relevant context from past sessions.

**Layer 2 — AOM (Always-On Memory).** A persistent long-term memory that captures tool results automatically. When the researcher calls a search API, that knowledge lands in AOM. When Mira asks "what did we learn about competitors?" — she gets answers synthesized from the researcher's findings. No manual handoff needed.

The key design decision: AOM is **shared across the entire team**. Every agent contributes to and queries from the same knowledge base. The researcher's discoveries become the content writer's source material — automatically.

**Layer 3 — Shared Files.** Explicit file exchange between agents. The researcher writes `shared/researcher/competitor-brief.md`, the content writer reads it. Simple, intentional, auditable.

```
Layer 1: ReMe     — session context, auto-compaction, semantic search
Layer 2: AOM      — long-term team knowledge, auto-captured from tools
Layer 3: Shared   — explicit file exchange between agents
```

Three layers, one team brain. Implicit knowledge flows up through AOM, explicit handoffs go through shared files, and sessions stay manageable through ReMe. Path traversal protection built in — agents can't escape their sandbox.

### Coordinator Delegation

The coordinator agent sees the full team roster and can delegate tasks. It knows each agent's role from their SOUL.md first line. Only one coordinator allowed — enforced at the config level.

### Model & Skill Assignment

Each persona can run on a different LLM. Put your researcher on a reasoning model, your content writer on a creative one. 12 providers supported out of the box.

Skills are assignable per-agent from a library of 108 built-in skills — SEO, ads, social media, browser automation, analytics. Pick what each agent needs, skip what they don't.

### MCP Clients

Same story for MCP (Model Context Protocol) servers. 25 available — Playwright, Firecrawl, Google Ads, HubSpot, Twitter, and more. Assign the right tools to the right agent.

### Templates

Don't want to configure from scratch? We ship preset templates — Growth Hacker, Social Media Strategist, Analytics Reporter, and more. One click to create, then customize.

### Cron Scheduling

Agents can run on a schedule. Set a cron expression, a prompt, and an output target. Your researcher can deliver a morning briefing every day at 9am without you lifting a finger.

## The Stack

- **Backend**: Python, FastAPI, Pydantic v2
- **Frontend**: React 18, TypeScript, Ant Design
- **Runtime**: Docker, with persistent volumes for config and secrets
- **LLM**: Provider-agnostic — OpenAI, Anthropic, Qwen, Gemini, xAI, local models via Ollama

Everything is configurable through the web console or REST API. No YAML files to hand-edit. No restarts needed.

## What's Next

This is the foundation. Next up: agent-to-agent chat (not just shared files), evaluation loops where agents review each other's work, and a visual workflow builder.

The goal isn't more agents. It's agents that actually get things done without you babysitting every step.

---

*AdClaw is an open-source AI agent platform for marketing teams. Try it at [github.com/nttylock/AdClaw](https://github.com/nttylock/AdClaw).*
