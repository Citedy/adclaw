# -*- coding: utf-8 -*-
"""Coordinator Synthesis Engine — reads AOM, builds context, produces strategy updates."""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .models import TaskStrategy

logger = logging.getLogger(__name__)

# Forbidden phrases in coordinator output — forces specificity
FORBIDDEN_PHRASES = [
    "based on results",
    "as appropriate",
    "optimize further",
    "continue as needed",
    "if applicable",
    "when possible",
]

SYNTHESIS_SYSTEM_PROMPT = """\
You are the Coordinator for a team of specialist personas.
Your job is SYNTHESIS — not execution.

## Rules
1. NEVER say "based on results" or "optimize further" — be SPECIFIC.
   BAD: "Based on SEO results, optimize the content."
   GOOD: "The SEO audit found 3 pages with missing H1 tags (/, /pricing, /blog).
          @content-writer: rewrite the H1 for each page targeting these keywords: [list]."

2. For each persona outcome, state:
   - What specifically succeeded or failed
   - Why it matters for the overall goal
   - What EXACT next action to take (persona, task, expected output)

3. If a persona is stuck (same error twice), PIVOT:
   - Try a different persona for the same subtask
   - Or break the subtask into smaller pieces
   - Or abandon and explain why

4. Output valid JSON matching the TaskStrategy schema.

## Team
{team_summary}

## Current Strategy
{current_strategy}

## Recent Activity (from AOM)
{recent_activity}

## Your Task
Analyze the above and produce an updated TaskStrategy JSON with:
- Updated synthesis (your analysis)
- Updated outcomes (mark completed/failed)
- New next_steps (specific tasks for specific personas)
"""


def validate_synthesis(synthesis: str) -> list[str]:
    """Check coordinator output for forbidden vague phrases."""
    violations = []
    lower = synthesis.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lower:
            violations.append(f"Forbidden phrase: '{phrase}'")
    return violations


async def run_synthesis_cycle(
    aom_manager,
    persona_manager,
    chat_model,
    active_strategy: Optional[TaskStrategy] = None,
) -> TaskStrategy:
    """Run one coordinator synthesis cycle.

    1. Query AOM for recent persona activity
    2. Build synthesis prompt
    3. Call LLM for analysis
    4. Parse strategy from response
    5. Validate synthesis quality

    NOTE: Does NOT persist to AOM — caller is responsible for persistence.

    Args:
        aom_manager: AOM manager with query_agent and ingest_agent
        persona_manager: PersonaManager with team info
        chat_model: LLM model for synthesis
        active_strategy: Current strategy to update, or None to create new

    Returns:
        Updated or new TaskStrategy
    """
    # 1. Query AOM for recent persona activity
    # skip_synthesis=True: we do our own synthesis, no need for AOM's LLM pass
    query_result = await aom_manager.query_agent.query(
        "Recent persona execution results, tool outputs, and task completions "
        "from the last 2 hours",
        skip_synthesis=True,
    )

    activity_parts = []
    for citation in query_result.citations:
        mem = citation.memory
        activity_parts.append(
            f"[{mem.source_type}:{mem.source_id}] "
            f"({mem.created_at})\n{mem.content}"
        )
    recent_activity = (
        "\n\n".join(activity_parts) if activity_parts
        else "(No recent persona activity found in AOM)"
    )

    # 2. Build synthesis prompt
    team_summary = persona_manager.get_team_summary()
    strategy_json = (
        active_strategy.model_dump_json(indent=2)
        if active_strategy
        else '{"status": "new", "goal": "Determine goal from recent activity"}'
    )

    prompt = SYNTHESIS_SYSTEM_PROMPT.format(
        team_summary=team_summary,
        current_strategy=strategy_json,
        recent_activity=recent_activity,
    )

    # 3. Call LLM
    # Use dicts instead of Msg objects (AgentScope OpenAIChatModel expects list[dict])
    # Await because model.__call__ is async
    import inspect

    raw_response = chat_model(
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Analyze the recent activity and produce an updated TaskStrategy."},
        ]
    )
    # Handle both sync and async models
    if inspect.isawaitable(raw_response):
        response = await raw_response
    else:
        response = raw_response

    # Extract text from response (handle ChatResponse.content list format)
    if hasattr(response, "content"):
        content = response.content
        if isinstance(content, list):
            response_text = "".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            )
        else:
            response_text = str(content)
    else:
        response_text = str(response)

    # 4. Parse strategy from response
    strategy = _parse_strategy_from_response(response_text, active_strategy)

    # Preserve pivot_count from active strategy (LLM doesn't track this)
    if active_strategy and strategy.pivot_count == 0:
        strategy.pivot_count = active_strategy.pivot_count

    # 5. Validate synthesis quality
    violations = validate_synthesis(strategy.synthesis)
    if violations:
        logger.warning(
            "Coordinator synthesis has %d quality violations: %s",
            len(violations),
            violations,
        )

    # NOTE: Strategy is NOT persisted here — the caller (cron_handler)
    # persists after delegations are executed, avoiding duplicate entries.

    return strategy


_STATUS_MAP = {"in_progress": "active", "completed": "completed", "done": "completed"}
_OUTCOME_STATUS_MAP = {
    "completed": "success", "done": "success", "needs_revision": "partial",
    "in_progress": "pending", "blocked": "stuck",
}


def _normalize_strategy_json(data: dict) -> dict:
    """Normalize common LLM deviations from our Pydantic schema."""
    # Status aliases
    if data.get("status") in _STATUS_MAP:
        data["status"] = _STATUS_MAP[data["status"]]

    # synthesis: LLM sometimes returns dict instead of string
    if isinstance(data.get("synthesis"), dict):
        data["synthesis"] = json.dumps(data["synthesis"])

    # Normalize outcomes
    for outcome in data.get("outcomes", []):
        # "persona" → "persona_id"
        if "persona" in outcome and "persona_id" not in outcome:
            outcome["persona_id"] = str(outcome.pop("persona") or "").lstrip("@")
        # "task" → "task_given"
        if "task" in outcome and "task_given" not in outcome:
            outcome["task_given"] = outcome.pop("task")
        # Status aliases
        if outcome.get("status") in _OUTCOME_STATUS_MAP:
            outcome["status"] = _OUTCOME_STATUS_MAP[outcome["status"]]
        # "findings" → "key_findings"
        if "findings" in outcome and "key_findings" not in outcome:
            outcome["key_findings"] = outcome.pop("findings")
            if isinstance(outcome["key_findings"], str):
                outcome["key_findings"] = [outcome["key_findings"]]

    # Normalize next_steps
    for step in data.get("next_steps", []):
        # "persona" → "persona_id"
        if "persona" in step and "persona_id" not in step:
            step["persona_id"] = str(step.pop("persona") or "").lstrip("@")
        # "reason" → "rationale"
        if "reason" in step and "rationale" not in step:
            step["rationale"] = step.pop("reason")
        # Missing rationale
        if "rationale" not in step:
            step["rationale"] = step.get("task", "No rationale provided")
        # priority: "high"/"medium"/"low" → int
        p = step.get("priority")
        if isinstance(p, str):
            step["priority"] = {"high": 1, "medium": 2, "low": 3}.get(p.lower(), 2)

    return data


def _parse_strategy_from_response(
    response_text: str,
    fallback: Optional[TaskStrategy] = None,
) -> TaskStrategy:
    """Extract TaskStrategy JSON from LLM response text."""
    # Try to find JSON block in response
    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    if json_match:
        raw = json_match.group(1)
    else:
        # Try raw JSON parse
        raw = response_text.strip()

    try:
        data = json.loads(raw)
        # Normalize common LLM schema deviations
        data = _normalize_strategy_json(data)
        return TaskStrategy(**data)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Failed to parse strategy JSON: %s", exc)
        if fallback:
            # Don't mutate the original fallback — create a copy with error info
            error_strategy = fallback.model_copy(
                update={
                    "synthesis": f"[Parse error — raw LLM output]\n{response_text[:2000]}"
                }
            )
            return error_strategy
        return TaskStrategy(
            goal="Unable to determine",
            synthesis=f"[Parse error]\n{response_text[:2000]}",
        )
