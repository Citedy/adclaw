# -*- coding: utf-8 -*-
"""Built-in provider definitions and registry."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Optional, Type

from agentscope.model import ChatModelBase

from .models import CustomProviderData, ModelInfo, ProviderDefinition
from .openai_chat_model_compat import OpenAIChatModelCompat

if TYPE_CHECKING:
    from .models import ProvidersData

MODELSCOPE_MODELS: List[ModelInfo] = [
    ModelInfo(
        id="Qwen/Qwen3-235B-A22B-Instruct-2507",
        name="Qwen3-235B-A22B-Instruct-2507",
    ),
    ModelInfo(id="deepseek-ai/DeepSeek-V3.2", name="DeepSeek-V3.2"),
]

DASHSCOPE_MODELS: List[ModelInfo] = [
    ModelInfo(id="qwen3.5-plus", name="Qwen3.5 Plus"),
    ModelInfo(id="qwq-plus", name="QwQ Plus"),
    ModelInfo(id="qwen-max-latest", name="Qwen Max Latest"),
    ModelInfo(id="qwen3-omni-flash", name="Qwen3 Omni Flash"),
    ModelInfo(id="qwen3-coder-plus", name="Qwen3 Coder Plus"),
]

ALIYUN_CODINGPLAN_MODELS: List[ModelInfo] = [
    ModelInfo(id="qwen3.5-plus", name="Qwen3.5 Plus"),
    ModelInfo(id="glm-5", name="GLM-5"),
    ModelInfo(id="glm-4.7", name="GLM-4.7"),
    ModelInfo(id="MiniMax-M2.5", name="MiniMax M2.5"),
    ModelInfo(id="kimi-k2.5", name="Kimi K2.5"),
    ModelInfo(id="qwen3-max-2026-01-23", name="Qwen3 Max 2026-01-23"),
    ModelInfo(id="qwen3-coder-next", name="Qwen3 Coder Next"),
    ModelInfo(id="qwen3-coder-plus", name="Qwen3 Coder Plus"),
]

OPENAI_MODELS: List[ModelInfo] = [
    ModelInfo(id="gpt-5.4", name="GPT-5.4"),
    ModelInfo(id="gpt-5.3-codex", name="GPT-5.3 Codex"),
    ModelInfo(id="gpt-5", name="GPT-5"),
    ModelInfo(id="gpt-5-mini", name="GPT-5 Mini"),
    ModelInfo(id="gpt-4.1", name="GPT-4.1"),
    ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini"),
]

AZURE_OPENAI_MODELS: List[ModelInfo] = [
    ModelInfo(id="gpt-5-chat", name="GPT-5 Chat"),
    ModelInfo(id="gpt-5-mini", name="GPT-5 Mini"),
    ModelInfo(id="gpt-5-nano", name="GPT-5 Nano"),
    ModelInfo(id="gpt-4.1", name="GPT-4.1"),
    ModelInfo(id="gpt-4.1-mini", name="GPT-4.1 Mini"),
    ModelInfo(id="gpt-4.1-nano", name="GPT-4.1 Nano"),
    ModelInfo(id="gpt-4o", name="GPT-4o"),
    ModelInfo(id="gpt-4o-mini", name="GPT-4o Mini"),
]

ALIYUN_INTL_MODELS: List[ModelInfo] = [
    ModelInfo(id="qwen3.5-plus", name="Qwen3.5 Plus"),
    ModelInfo(id="qwen3-max-2026-01-23", name="Qwen3 Max"),
    ModelInfo(id="qwen3-coder-plus", name="Qwen3 Coder Plus"),
    ModelInfo(id="qwen3-omni-flash", name="Qwen3 Omni Flash"),
    ModelInfo(id="qwen-mt-plus", name="Qwen MT Plus"),
    ModelInfo(id="glm-5", name="GLM-5"),
    ModelInfo(id="kimi-k2.5", name="Kimi K2.5"),
    ModelInfo(id="MiniMax-M2.5", name="MiniMax M2.5"),
]

OPENROUTER_MODELS: List[ModelInfo] = [
    ModelInfo(id="openrouter/auto", name="Auto (OpenRouter picks)"),
    ModelInfo(id="google/gemini-2.5-flash-lite", name="Gemini 2.5 Flash Lite"),
    ModelInfo(id="minimax/minimax-m2.5", name="MiniMax M2.5"),
    ModelInfo(id="google/gemini-3-flash-preview", name="Gemini 3 Flash Preview"),
    ModelInfo(id="moonshotai/kimi-k2.5", name="Kimi K2.5"),
    ModelInfo(id="anthropic/claude-opus-4.6", name="Claude Opus 4.6"),
    ModelInfo(id="anthropic/claude-sonnet-4.6", name="Claude Sonnet 4.6"),
    ModelInfo(id="deepseek/deepseek-v3.2", name="DeepSeek V3.2"),
    ModelInfo(id="qwen/qwen3-32b", name="Qwen3 32B"),
    ModelInfo(id="openai/gpt-5.3-codex", name="GPT-5.3 Codex"),
    ModelInfo(id="openai/gpt-5.4", name="GPT-5.4"),
    ModelInfo(id="openai/gpt-5.1", name="GPT-5.1"),
    ModelInfo(id="openai/gpt-5.2", name="GPT-5.2"),
    ModelInfo(id="openai/gpt-4o-mini", name="GPT-4o Mini"),
    ModelInfo(id="openai/gpt-oss-120b", name="GPT-OSS 120B"),
    ModelInfo(id="openai/gpt-5-nano", name="GPT-5 Nano"),
]

ANTHROPIC_MODELS: List[ModelInfo] = [
    ModelInfo(id="claude-opus-4-6", name="Claude Opus 4.6"),
    ModelInfo(id="claude-sonnet-4-6", name="Claude Sonnet 4.6"),
    ModelInfo(id="claude-haiku-4-6", name="Claude Haiku 4.6"),
]

XAI_MODELS: List[ModelInfo] = [
    ModelInfo(
        id="grok-4-fast-non-reasoning",
        name="Grok 4 Fast (non-reasoning)",
    ),
]

GEMINI_MODELS: List[ModelInfo] = [
    ModelInfo(id="gemini-3.1-pro-preview", name="Gemini 3.1 Pro Preview"),
    ModelInfo(id="gemini-3-flash-preview", name="Gemini 3 Flash Preview"),
    ModelInfo(
        id="gemini-3.1-flash-lite-preview", name="Gemini 3.1 Flash Lite Preview"
    ),
]

GROQ_MODELS: List[ModelInfo] = [
    ModelInfo(id="llama-3.3-70b-versatile", name="Llama 3.3 70B Versatile"),
    ModelInfo(id="llama-3.1-8b-instant", name="Llama 3.1 8B Instant"),
    ModelInfo(
        id="moonshotai/Kimi-K2-Instruct-0905", name="Kimi K2 Instruct"
    ),
    ModelInfo(id="openai/gpt-oss-120b", name="GPT-OSS 120B"),
]

DEEPSEEK_MODELS: List[ModelInfo] = [
    ModelInfo(id="deepseek-chat", name="DeepSeek Chat (V3.2)"),
    ModelInfo(id="deepseek-reasoner", name="DeepSeek Reasoner (R1)"),
]

CEREBRAS_MODELS: List[ModelInfo] = [
    ModelInfo(id="llama3.1-8b", name="Llama 3.1 8B"),
    ModelInfo(id="gpt-oss-120b", name="GPT-OSS 120B"),
    ModelInfo(
        id="qwen-3-235b-a22b-instruct-2507", name="Qwen 3 235B A22B"
    ),
    ModelInfo(id="zai-glm-4.7", name="Z.AI GLM 4.7"),
]

TOGETHER_MODELS: List[ModelInfo] = [
    ModelInfo(id="meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", name="Llama 3.1 70B Turbo"),
    ModelInfo(id="deepseek-ai/DeepSeek-V3", name="DeepSeek V3"),
]

MISTRAL_MODELS: List[ModelInfo] = [
    ModelInfo(id="mistral-large-latest", name="Mistral Large"),
    ModelInfo(id="mistral-small-latest", name="Mistral Small"),
]

BASETEN_MODELS: List[ModelInfo] = [
    ModelInfo(id="zai-org/GLM-5", name="GLM 5"),
    ModelInfo(id="zai-org/GLM-4.7", name="GLM 4.7"),
    ModelInfo(id="zai-org/GLM-4.6", name="GLM 4.6"),
    ModelInfo(id="deepseek-ai/DeepSeek-V3.1", name="DeepSeek V3.1"),
    ModelInfo(id="deepseek-ai/DeepSeek-V3-0324", name="DeepSeek V3 0324"),
    ModelInfo(id="openai/gpt-oss-120b", name="OpenAI GPT 120B"),
    ModelInfo(id="nvidia/Nemotron-120B-A12B", name="Nemotron Super"),
    ModelInfo(id="moonshotai/Kimi-K2.5", name="Kimi K2.5"),
    ModelInfo(id="MiniMaxAI/MiniMax-M2.5", name="MiniMax M2.5"),
]

MINIMAX_MODELS: List[ModelInfo] = [
    ModelInfo(id="MiniMax-M2.5", name="MiniMax M2.5"),
]

INCEPTION_MODELS: List[ModelInfo] = [
    ModelInfo(id="mercury-2", name="Mercury 2"),
]

MOONSHOT_MODELS: List[ModelInfo] = [
    ModelInfo(id="kimi-k2.5", name="Kimi K2.5"),
]

PROVIDER_MODELSCOPE = ProviderDefinition(
    id="modelscope",
    name="ModelScope",
    default_base_url="https://api-inference.modelscope.cn/v1",
    api_key_prefix="ms",
    models=MODELSCOPE_MODELS,
)

PROVIDER_DASHSCOPE = ProviderDefinition(
    id="dashscope",
    name="DashScope (International)",
    default_base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    api_key_prefix="sk",
    models=DASHSCOPE_MODELS,
)

PROVIDER_ALIYUN_CODINGPLAN = ProviderDefinition(
    id="aliyun-codingplan",
    name="Aliyun Coding Plan",
    default_base_url="https://coding.dashscope.aliyuncs.com/v1",
    api_key_prefix="sk-sp",
    models=ALIYUN_CODINGPLAN_MODELS,
)

PROVIDER_LLAMACPP = ProviderDefinition(
    id="llamacpp",
    name="llama.cpp (Local)",
    default_base_url="",
    api_key_prefix="",
    models=[],
    is_local=True,
)

PROVIDER_MLX = ProviderDefinition(
    id="mlx",
    name="MLX (Local, Apple Silicon)",
    default_base_url="",
    api_key_prefix="",
    models=[],
    is_local=True,
)

PROVIDER_OPENAI = ProviderDefinition(
    id="openai",
    name="OpenAI",
    default_base_url="https://api.openai.com/v1",
    api_key_prefix="sk-",
    models=OPENAI_MODELS,
)

PROVIDER_AZURE_OPENAI = ProviderDefinition(
    id="azure-openai",
    name="Azure OpenAI",
    default_base_url="",
    api_key_prefix="",
    models=AZURE_OPENAI_MODELS,
)

PROVIDER_ALIYUN_INTL = ProviderDefinition(
    id="aliyun-intl",
    name="Aliyun Coding (International)",
    default_base_url="https://coding-intl.dashscope.aliyuncs.com/v1",
    api_key_prefix="sk-sp",
    models=ALIYUN_INTL_MODELS,
)

PROVIDER_OPENROUTER = ProviderDefinition(
    id="openrouter",
    name="OpenRouter",
    default_base_url="https://openrouter.ai/api/v1",
    api_key_prefix="sk-or-",
    models=OPENROUTER_MODELS,
)

PROVIDER_ANTHROPIC = ProviderDefinition(
    id="anthropic",
    name="Anthropic",
    default_base_url="https://api.anthropic.com/v1",
    api_key_prefix="sk-ant-",
    models=ANTHROPIC_MODELS,
)

PROVIDER_XAI = ProviderDefinition(
    id="xai",
    name="xAI (Grok)",
    default_base_url="https://api.x.ai/v1",
    api_key_prefix="xai-",
    models=XAI_MODELS,
)

PROVIDER_OLLAMA = ProviderDefinition(
    id="ollama",
    name="Ollama",
    # Ollama uses `OLLAMA_HOST` env var as its BASE URL
    # TODO: auto detect ollama base url and display in UI
    # TODO: override `OLLAMA_HOST` with the detected/configured URL
    default_base_url="http://localhost:11434/v1",
    api_key_prefix="",
    models=[],
)

PROVIDER_GEMINI = ProviderDefinition(
    id="gemini",
    name="Gemini (Google)",
    default_base_url="https://generativelanguage.googleapis.com/v1beta",
    api_key_prefix="AIza",
    models=GEMINI_MODELS,
)

PROVIDER_GROQ = ProviderDefinition(
    id="groq",
    name="Groq",
    default_base_url="https://api.groq.com/openai/v1",
    api_key_prefix="gsk_",
    models=GROQ_MODELS,
)

PROVIDER_DEEPSEEK = ProviderDefinition(
    id="deepseek",
    name="DeepSeek",
    default_base_url="https://api.deepseek.com/v1",
    api_key_prefix="sk-",
    models=DEEPSEEK_MODELS,
)

PROVIDER_CEREBRAS = ProviderDefinition(
    id="cerebras",
    name="Cerebras",
    default_base_url="https://api.cerebras.ai/v1",
    api_key_prefix="csk-",
    models=CEREBRAS_MODELS,
)

PROVIDER_TOGETHER = ProviderDefinition(
    id="together",
    name="Together AI",
    default_base_url="https://api.together.xyz/v1",
    api_key_prefix="",
    models=TOGETHER_MODELS,
)

PROVIDER_MISTRAL = ProviderDefinition(
    id="mistral",
    name="Mistral",
    default_base_url="https://api.mistral.ai/v1",
    api_key_prefix="",
    models=MISTRAL_MODELS,
)

PROVIDER_BASETEN = ProviderDefinition(
    id="baseten",
    name="Baseten",
    default_base_url="https://inference.baseten.co/v1",
    api_key_prefix="",
    models=BASETEN_MODELS,
)

PROVIDER_MINIMAX = ProviderDefinition(
    id="minimax",
    name="Minimax AI",
    default_base_url="https://api.minimaxi.chat/v1/text/chatcompletion_v2",
    api_key_prefix="",
    models=MINIMAX_MODELS,
)

PROVIDER_INCEPTION = ProviderDefinition(
    id="inception",
    name="Inception Labs",
    default_base_url="https://api.inceptionlabs.ai/v1",
    api_key_prefix="",
    models=INCEPTION_MODELS,
)

PROVIDER_MOONSHOT = ProviderDefinition(
    id="moonshot",
    name="Moonshot AI",
    default_base_url="https://api.moonshot.ai/v1",
    api_key_prefix="",
    models=MOONSHOT_MODELS,
)

_BUILTIN_IDS: frozenset[str] = frozenset(
    [
        "modelscope",
        "dashscope",
        "aliyun-codingplan",
        "aliyun-intl",
        "openai",
        "openrouter",
        "anthropic",
        "azure-openai",
        "xai",
        "ollama",
        "llamacpp",
        "mlx",
        "gemini",
        "groq",
        "deepseek",
        "cerebras",
        "together",
        "mistral",
        "baseten",
        "minimax",
        "inception",
        "moonshot",
    ],
)

PROVIDERS: dict[str, ProviderDefinition] = {
    PROVIDER_OPENROUTER.id: PROVIDER_OPENROUTER,
    PROVIDER_OPENAI.id: PROVIDER_OPENAI,
    PROVIDER_ANTHROPIC.id: PROVIDER_ANTHROPIC,
    PROVIDER_GEMINI.id: PROVIDER_GEMINI,
    PROVIDER_GROQ.id: PROVIDER_GROQ,
    PROVIDER_DEEPSEEK.id: PROVIDER_DEEPSEEK,
    PROVIDER_CEREBRAS.id: PROVIDER_CEREBRAS,
    PROVIDER_TOGETHER.id: PROVIDER_TOGETHER,
    PROVIDER_MISTRAL.id: PROVIDER_MISTRAL,
    PROVIDER_BASETEN.id: PROVIDER_BASETEN,
    PROVIDER_MINIMAX.id: PROVIDER_MINIMAX,
    PROVIDER_INCEPTION.id: PROVIDER_INCEPTION,
    PROVIDER_MOONSHOT.id: PROVIDER_MOONSHOT,
    PROVIDER_ALIYUN_INTL.id: PROVIDER_ALIYUN_INTL,
    PROVIDER_ALIYUN_CODINGPLAN.id: PROVIDER_ALIYUN_CODINGPLAN,
    PROVIDER_MODELSCOPE.id: PROVIDER_MODELSCOPE,
    PROVIDER_DASHSCOPE.id: PROVIDER_DASHSCOPE,
    PROVIDER_XAI.id: PROVIDER_XAI,
    PROVIDER_AZURE_OPENAI.id: PROVIDER_AZURE_OPENAI,
    PROVIDER_OLLAMA.id: PROVIDER_OLLAMA,
    PROVIDER_LLAMACPP.id: PROVIDER_LLAMACPP,
    PROVIDER_MLX.id: PROVIDER_MLX,
}

_VALID_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def get_provider(provider_id: str) -> Optional[ProviderDefinition]:
    return PROVIDERS.get(provider_id)


def get_provider_chat_model(
    provider_id: str,
    providers_data: Optional[ProvidersData] = None,
) -> str:
    """Get chat model name for a provider, checking JSON settings first.

    Args:
        provider_id: Provider identifier.
        providers_data: Optional ProvidersData. If None, will load from JSON.

    Returns:
        Chat model class name, defaults to "OpenAIChatModel".
    """
    if providers_data is None:
        from .store import load_providers_json

        providers_data = load_providers_json()

    cpd = providers_data.custom_providers.get(provider_id)
    if cpd is not None:
        return cpd.chat_model

    settings = providers_data.providers.get(provider_id)
    if settings and settings.chat_model:
        return settings.chat_model

    provider_def = get_provider(provider_id)
    if provider_def:
        return provider_def.chat_model

    return "OpenAIChatModel"


def list_providers() -> List[ProviderDefinition]:
    return list(PROVIDERS.values())


def is_builtin(provider_id: str) -> bool:
    return provider_id in _BUILTIN_IDS


def _custom_data_to_definition(cpd: CustomProviderData) -> ProviderDefinition:
    return ProviderDefinition(
        id=cpd.id,
        name=cpd.name,
        default_base_url=cpd.default_base_url,
        api_key_prefix=cpd.api_key_prefix,
        models=list(cpd.models),
        is_custom=True,
        chat_model=cpd.chat_model,
    )


def validate_custom_provider_id(provider_id: str) -> Optional[str]:
    """Return an error message if invalid, or None if valid."""
    if provider_id in _BUILTIN_IDS:
        return f"'{provider_id}' is a built-in provider id and cannot be used."
    if not _VALID_ID_RE.match(provider_id):
        return (
            f"Invalid provider id '{provider_id}'. "
            "Must start with a lowercase letter and contain only "
            "lowercase letters, digits, hyphens, and underscores "
            "(max 64 chars)."
        )
    return None


def register_custom_provider(cpd: CustomProviderData) -> ProviderDefinition:
    err = validate_custom_provider_id(cpd.id)
    if err:
        raise ValueError(err)
    defn = _custom_data_to_definition(cpd)
    PROVIDERS[cpd.id] = defn
    return defn


def unregister_custom_provider(provider_id: str) -> None:
    if provider_id in _BUILTIN_IDS:
        raise ValueError(f"Cannot remove built-in provider '{provider_id}'.")
    PROVIDERS.pop(provider_id, None)


def sync_custom_providers(
    custom_providers: dict[str, CustomProviderData],
) -> None:
    """Synchronise the in-memory registry with persisted custom providers."""
    stale = [
        pid
        for pid, defn in PROVIDERS.items()
        if defn.is_custom and pid not in custom_providers
    ]
    for pid in stale:
        del PROVIDERS[pid]
    for cpd in custom_providers.values():
        PROVIDERS[cpd.id] = _custom_data_to_definition(cpd)


def sync_local_models() -> None:
    """Refresh local provider model lists from the local models manifest."""
    try:
        from ..local_models.manager import list_local_models
        from ..local_models.schema import BackendType

        llamacpp_models: list[ModelInfo] = []
        mlx_models: list[ModelInfo] = []

        for model in list_local_models():
            info = ModelInfo(id=model.id, name=model.display_name)
            if model.backend == BackendType.LLAMACPP:
                llamacpp_models.append(info)
            elif model.backend == BackendType.MLX:
                mlx_models.append(info)

        PROVIDER_LLAMACPP.models = llamacpp_models
        PROVIDER_MLX.models = mlx_models
    except ImportError:
        # local_models dependencies not installed; leave model lists empty
        pass


def sync_ollama_models() -> None:
    """Refresh Ollama provider model list from the Ollama daemon.

    Models are derived from ``ollama.list()`` via :class:`OllamaModelManager`.
    If the SDK is not installed or the daemon is unavailable, the list is
    left unchanged.
    """
    try:
        from ..providers.ollama_manager import OllamaModelManager

        models: list[ModelInfo] = []
        for model in OllamaModelManager.list_models():
            models.append(ModelInfo(id=model.name, name=model.name))
        PROVIDER_OLLAMA.models = models
    except ImportError:
        # Ollama SDK not installed; treat as having no models
        PROVIDER_OLLAMA.models = []
    except Exception:
        # Any other error (e.g. daemon not running) — keep previous list.
        pass


_CHAT_MODEL_MAP: dict[str, Type[ChatModelBase]] = {
    "OpenAIChatModel": OpenAIChatModelCompat,
}


def get_chat_model_class(chat_model_name: str) -> Type[ChatModelBase]:
    """Get chat model class by name.

    Args:
        chat_model_name: Name of the chat model class (e.g., "OpenAIChatModel")

    Returns:
        Chat model class, defaults to OpenAIChatModel-compatible parser.
    """
    return _CHAT_MODEL_MAP.get(chat_model_name, OpenAIChatModelCompat)
