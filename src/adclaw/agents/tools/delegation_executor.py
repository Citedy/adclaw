import logging
from ...config.config import PersonaConfig
from ..persona_manager import PersonaManager

logger = logging.getLogger(__name__)

DELEGATION_FAILED_PREFIX = "Delegation failed:"


def execute_delegation(persona: PersonaConfig, task: str, persona_manager: PersonaManager) -> str:
    """Execute a delegated task by creating a sub-agent with persona config.

    For MVP, uses a simple one-shot LLM call with the persona's system prompt.
    """
    try:
        from ..prompt import PromptBuilder
        from pathlib import Path
        from ...constant import WORKING_DIR

        builder = PromptBuilder(
            working_dir=Path(WORKING_DIR),
            persona=persona,
            team_summary=persona_manager.get_team_summary(),
        )
        sys_prompt = builder.build()

        from ..model_factory import create_model_and_formatter
        if persona.model_provider and persona.model_name:
            chat_model, formatter = create_model_and_formatter(
                provider=persona.model_provider,
                model=persona.model_name,
            )
        else:
            chat_model, formatter = create_model_and_formatter()

        from agentscope.message import Msg
        user_msg = Msg(name="user", content=task, role="user")
        sys_msg = Msg(name="system", content=sys_prompt, role="system")

        response = chat_model([sys_msg, user_msg])
        return response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        logger.exception(f"Delegation execution failed: {e}")
        return f"{DELEGATION_FAILED_PREFIX} {e}"
