# -*- coding: utf-8 -*-
# pylint: disable=too-many-branches
"""Telegram channel: Bot API with polling; receive/send via chat_id."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional, Union

from agentscope_runtime.engine.schemas.agent_schemas import (
    TextContent,
    ImageContent,
    VideoContent,
    AudioContent,
    FileContent,
    ContentType,
)

from ....config.config import TelegramConfig as TelegramChannelConfig
from ..base import (
    BaseChannel,
    OnReplySent,
    ProcessHandler,
    OutgoingContentPart,
)

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096
TELEGRAM_SEND_CHUNK_SIZE = 4000

_DEFAULT_MEDIA_DIR = Path(
    os.environ.get("ADCLAW_WORKING_DIR", "~/.adclaw"),
).expanduser() / "media" / "telegram"

_MEDIA_ATTRS: list[tuple[str, type, Any, str]] = [
    ("document", FileContent, ContentType.FILE, "file_url"),
    ("video", VideoContent, ContentType.VIDEO, "video_url"),
    ("voice", AudioContent, ContentType.AUDIO, "data"),
    ("audio", AudioContent, ContentType.AUDIO, "data"),
]


async def _download_telegram_file(
    *,
    bot: Any,
    file_id: str,
    media_dir: Path,
    filename_hint: str = "",
) -> Optional[str]:
    """Download a Telegram file to local media_dir; return local path.

    Never exposes the bot token in the returned path.
    """
    try:
        from telegram.error import TelegramError

        tg_file = await bot.get_file(file_id)
    except TelegramError:
        logger.exception("telegram: get_file failed for file_id=%s", file_id)
        return None

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        suffix = ""
        file_path = (getattr(tg_file, "file_path", None) or "").strip()
        if file_path:
            suffix = Path(file_path).suffix
        if filename_hint and not suffix:
            suffix = Path(filename_hint).suffix
        local_name = f"{uuid.uuid4().hex[:12]}{suffix or '.bin'}"
        local_path = media_dir / local_name
        await tg_file.download_to_drive(str(local_path))
        return str(local_path)
    except Exception:
        logger.exception("telegram: download failed for file_id=%s", file_id)
        return None


async def _resolve_telegram_file_url(
    *,
    bot: Any,
    file_id: str,
    bot_token: str,
) -> str:
    """Resolve the remote URL for a Telegram file.

    Returns the file URL (either Telegram API URL or external URL).
    Never exposes the bot token in the returned URL.
    """
    try:
        from telegram.error import TelegramError

        tg_file = await bot.get_file(file_id)
    except TelegramError:
        logger.exception("telegram: get_file failed for file_id=%s", file_id)
        return ""
    file_path = getattr(tg_file, "file_path", None) or ""
    if not file_path:
        return ""
    if file_path.startswith("http"):
        return file_path
    return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"


async def _build_content_parts_from_message(
    update: Any,
    *,
    bot: Any,
    media_dir: Path,
) -> tuple[list, bool]:
    """Build runtime content_parts from Telegram message.

    Returns (content_parts, has_bot_command).
    """
    message = getattr(update, "message", None) or getattr(
        update,
        "edited_message",
    )
    if not message:
        return [TextContent(type=ContentType.TEXT, text="")], False

    content_parts: list[Any] = []
    text = (
        getattr(message, "text", None) or getattr(message, "caption") or ""
    ).strip()

    entities = (
        getattr(message, "entities", None)
        or getattr(message, "caption_entities", None)
        or []
    )
    has_bot_command = False
    if entities:
        for entity in entities:
            if getattr(entity, "type", None) == "bot_command":
                has_bot_command = True
                break

    if text:
        content_parts.append(TextContent(type=ContentType.TEXT, text=text))

    photo = getattr(message, "photo", None)
    if photo and len(photo) > 0:
        largest = photo[-1]
        file_id = getattr(largest, "file_id", None)
        if file_id:
            local_path = await _download_telegram_file(
                bot=bot,
                file_id=file_id,
                media_dir=media_dir,
                filename_hint="photo.jpg",
            )
            if local_path:
                content_parts.append(
                    ImageContent(type=ContentType.IMAGE, image_url=local_path),
                )

    for attr_name, content_cls, content_type, url_field in _MEDIA_ATTRS:
        media_obj = getattr(message, attr_name, None)
        if not media_obj:
            continue
        file_id = getattr(media_obj, "file_id", None)
        if not file_id:
            continue
        file_name = getattr(media_obj, "file_name", None) or attr_name
        local_path = await _download_telegram_file(
            bot=bot,
            file_id=file_id,
            media_dir=media_dir,
            filename_hint=file_name,
        )
        if local_path:
            content_parts.append(
                content_cls(type=content_type, **{url_field: local_path}),
            )

    if not content_parts:
        content_parts.append(TextContent(type=ContentType.TEXT, text=""))

    return content_parts, has_bot_command


def _message_meta(update: Any) -> dict:
    """Extract chat_id, user_id, etc. from Telegram update."""
    message = getattr(update, "message", None) or getattr(
        update,
        "edited_message",
    )
    if not message:
        return {}
    chat = getattr(message, "chat", None)
    user = getattr(message, "from_user", None)
    chat_id = str(getattr(chat, "id", "")) if chat else ""
    user_id = str(getattr(user, "id", "")) if user else ""
    username = (getattr(user, "username", None) or "") if user else ""
    chat_type = getattr(chat, "type", "") if chat else ""
    return {
        "chat_id": chat_id,
        "user_id": user_id,
        "username": username,
        "message_id": str(getattr(message, "message_id", "")),
        "is_group": chat_type in ("group", "supergroup", "channel"),
    }


class TelegramChannel(BaseChannel):
    """Telegram channel: Bot API polling; session_id = telegram:{chat_id}."""

    channel = "telegram"
    uses_manager_queue = True

    def __init__(
        self,
        process: ProcessHandler,
        enabled: bool,
        bot_token: str,
        http_proxy: str,
        http_proxy_auth: str,
        bot_prefix: str,
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = False,
        media_dir: str = "",
        show_typing: bool = True,
        filter_tool_messages: bool = True,
    ):
        super().__init__(
            process,
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
        )
        self.enabled = enabled
        self._bot_token = bot_token
        self._http_proxy = http_proxy or ""
        self._http_proxy_auth = http_proxy_auth or ""
        self.bot_prefix = bot_prefix
        self._media_dir = (
            Path(media_dir).expanduser() if media_dir else _DEFAULT_MEDIA_DIR
        )
        self._show_typing = show_typing
        self._task: Optional[asyncio.Task] = None
        self._application = None
        self._chat_persona: dict[str, str] = {}  # chat_id → persona_id
        if self.enabled and self._bot_token:
            try:
                self._application = self._build_application()
                logger.info(
                    "telegram: channel initialized (polling will start)",
                )
            except Exception:
                logger.exception("telegram: failed to build application")
                self._application = None
        else:
            if self.enabled and not self._bot_token:
                logger.info("telegram: channel disabled (bot_token empty)")
            elif not self.enabled:
                logger.debug(
                    "telegram: channel disabled (enabled=false in config)",
                )

    def _build_application(self):
        from telegram import Update
        from telegram.ext import (
            Application,
            ContextTypes,
            MessageHandler,
            filters,
        )

        def proxy_url() -> Optional[str]:
            if not self._http_proxy:
                return None
            if self._http_proxy_auth:
                if "://" in self._http_proxy:
                    prefix, rest = self._http_proxy.split("://", 1)
                    return f"{prefix}://{self._http_proxy_auth}@{rest}"
                return f"http://{self._http_proxy_auth}@{self._http_proxy}"
            return self._http_proxy

        builder = Application.builder().token(self._bot_token)
        proxy = proxy_url()
        if proxy:
            builder = builder.proxy(proxy).get_updates_proxy(proxy)

        app = builder.build()

        # Menu button texts that should be intercepted
        _MENU_BUTTONS = {
            "👤 Persona", "⚙️ Model", "🆕 New Chat",
            "🔧 Skills", "📊 Status", "🌐 Tasks",
        }
        # Slash commands handled directly (not forwarded to agent)
        _DIRECT_COMMANDS = {
            "/start", "/new",
            "/personas", "/model", "/skills", "/status",
            "/compact", "/clear", "/history", "/tasks",
        }

        async def handle_message(
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
        ) -> None:
            if not update.message and not getattr(
                update,
                "edited_message",
                None,
            ):
                return

            # Intercept menu button presses and slash commands
            msg = update.message or getattr(update, "edited_message", None)
            raw_text = (msg.text or "").strip() if msg else ""
            meta = _message_meta(update)
            chat_id = meta.get("chat_id", "")

            # Strip @botname from commands (e.g. /skills@your_bot → /skills)
            text = raw_text.split("@")[0] if raw_text.startswith("/") else raw_text

            if text in _MENU_BUTTONS or text in _DIRECT_COMMANDS:
                await self._handle_menu_command(chat_id, text, meta=meta)
                return

            (
                content_parts,
                has_bot_command,
            ) = await _build_content_parts_from_message(
                update,
                bot=context.bot,
                media_dir=self._media_dir,
            )
            if has_bot_command:
                meta["has_bot_command"] = True

            # Inject persona tag if chat has a selected persona
            active_pid = self._chat_persona.get(chat_id)
            if active_pid and content_parts:
                first = content_parts[0]
                if hasattr(first, "text") and first.text:
                    # Don't re-tag if already has @mention
                    if not first.text.startswith("@"):
                        content_parts[0] = TextContent(
                            type=ContentType.TEXT,
                            text=f"@{active_pid} {first.text}",
                        )

            user = getattr(msg, "from_user", None)
            sender_id = str(getattr(user, "id", "")) if user else chat_id
            native = {
                "channel_id": self.channel,
                "sender_id": sender_id,
                "content_parts": content_parts,
                "meta": meta,
            }
            if self._enqueue is not None:
                self._enqueue(native)
            else:
                logger.warning("telegram: _enqueue not set, message dropped")

        async def handle_callback_query(
            update: "Update",
            context: ContextTypes.DEFAULT_TYPE,
        ) -> None:
            """Handle inline keyboard button presses."""
            query = update.callback_query
            if not query:
                return
            await query.answer()
            data = query.data or ""
            chat = query.message.chat if query.message else None
            chat_id = str(chat.id) if chat else ""
            bot = context.bot

            # --- Persona selection ---
            if data.startswith("persona::"):
                pid = data.split("::", 1)[1]
                self._chat_persona[chat_id] = pid
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                kb = await self._build_personas_keyboard(chat_id)
                try:
                    await query.edit_message_text(
                        f"✅ Switched to **{pid}**",
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
                return

            # --- Provider selection (level 1 of model picker) ---
            if data.startswith("provider::"):
                provider_id = data.split("::", 1)[1]
                kb = await self._build_models_keyboard(provider_id)
                try:
                    await query.edit_message_text(
                        f"⚙️ Models for **{provider_id}**:",
                        parse_mode="Markdown",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
                return

            # --- Model selection (level 2) ---
            if data.startswith("model::"):
                parts = data.split("::", 2)
                if len(parts) == 3:
                    provider_id, model_name = parts[1], parts[2]
                    await self._switch_model(provider_id, model_name)
                    try:
                        await query.edit_message_text(
                            f"✅ Model switched to **{model_name}** ({provider_id})",
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass
                return

            # --- Back to providers list ---
            if data == "back::providers":
                kb = await self._build_providers_keyboard()
                try:
                    await query.edit_message_text(
                        "⚙️ Select provider:",
                        reply_markup=kb,
                    )
                except Exception:
                    pass
                return

            # --- Skills pagination ---
            if data.startswith("skills_page::"):
                page = int(data.split("::")[1])
                await self._handle_menu_command(chat_id, f"skills_page::{page}")
                try:
                    await query.message.delete()
                except Exception:
                    pass
                return

            # --- Confirm new chat ---
            if data == "confirm_new::yes":
                # Forward as /new command
                user = query.from_user
                sender_id = str(user.id) if user else chat_id
                content_parts = [
                    TextContent(type=ContentType.TEXT, text="/new"),
                ]
                meta = {
                    "chat_id": chat_id,
                    "user_id": sender_id,
                    "username": (user.username or "") if user else "",
                    "message_id": "",
                    "is_group": False,
                    "has_bot_command": True,
                }
                native = {
                    "channel_id": self.channel,
                    "sender_id": sender_id,
                    "content_parts": content_parts,
                    "meta": meta,
                }
                if self._enqueue is not None:
                    self._enqueue(native)
                try:
                    await query.edit_message_text("🆕 Starting new chat...")
                except Exception:
                    pass
                return
            if data == "confirm_new::no":
                try:
                    await query.edit_message_text("Cancelled.")
                except Exception:
                    pass
                return

            # /clear bypasses queue in callbacks too
            if data == "/clear":
                user = query.from_user
                sender_id = str(user.id) if user else chat_id
                await self._force_clear_session(chat_id, sender_id)
                return

            # --- Legacy commands (/compact, /history) ---
            if data in ("/new", "/compact", "/history"):
                user = query.from_user
                sender_id = str(user.id) if user else chat_id
                content_parts = [
                    TextContent(type=ContentType.TEXT, text=data),
                ]
                meta = {
                    "chat_id": chat_id,
                    "user_id": sender_id,
                    "username": (user.username or "") if user else "",
                    "message_id": "",
                    "is_group": False,
                    "has_bot_command": True,
                }
                native = {
                    "channel_id": self.channel,
                    "sender_id": sender_id,
                    "content_parts": content_parts,
                    "meta": meta,
                }
                if self._enqueue is not None:
                    self._enqueue(native)
                return

        from telegram.ext import CallbackQueryHandler

        app.add_handler(CallbackQueryHandler(handle_callback_query))
        app.add_handler(MessageHandler(filters.ALL, handle_message))
        return app

    @classmethod
    def from_env(
        cls,
        process: ProcessHandler,
        on_reply_sent: OnReplySent = None,
    ) -> "TelegramChannel":
        import os

        return cls(
            process=process,
            enabled=os.getenv("TELEGRAM_CHANNEL_ENABLED", "0") == "1",
            bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            http_proxy=os.getenv("TELEGRAM_HTTP_PROXY", ""),
            http_proxy_auth=os.getenv("TELEGRAM_HTTP_PROXY_AUTH", ""),
            bot_prefix=os.getenv("TELEGRAM_BOT_PREFIX", ""),
            on_reply_sent=on_reply_sent,
            show_typing=os.getenv("TELEGRAM_SHOW_TYPING", "1") == "1",
        )

    @classmethod
    def from_config(
        cls,
        process: ProcessHandler,
        config: Union[TelegramChannelConfig, dict],
        on_reply_sent: OnReplySent = None,
        show_tool_details: bool = False,
        filter_tool_messages: bool = True,
    ) -> "TelegramChannel":
        channel_show_typing = None
        if isinstance(config, dict):
            channel_show_typing = config.get("show_typing")
        else:
            channel_show_typing = getattr(config, "show_typing", None)

        if isinstance(config, dict):
            bot_prefix_raw = config.get("bot_prefix")
            return cls(
                process=process,
                enabled=bool(config.get("enabled", False)),
                bot_token=(config.get("bot_token") or "").strip(),
                http_proxy=(config.get("http_proxy") or "").strip(),
                http_proxy_auth=(config.get("http_proxy_auth") or "").strip(),
                bot_prefix=bot_prefix_raw.strip() if bot_prefix_raw else "",
                on_reply_sent=on_reply_sent,
                show_tool_details=show_tool_details,
                filter_tool_messages=filter_tool_messages,
                show_typing=channel_show_typing
                if channel_show_typing is not None
                else True,
            )
        return cls(
            process=process,
            enabled=config.enabled,
            bot_token=config.bot_token or "",
            http_proxy=config.http_proxy or "",
            http_proxy_auth=config.http_proxy_auth or "",
            bot_prefix=config.bot_prefix or "",
            on_reply_sent=on_reply_sent,
            show_tool_details=show_tool_details,
            filter_tool_messages=filter_tool_messages,
            show_typing=channel_show_typing
            if channel_show_typing is not None
            else True,
        )

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into chunks under Telegram's message length limit."""
        if not text or len(text) <= TELEGRAM_SEND_CHUNK_SIZE:
            return [text] if text else []
        chunks: list[str] = []
        rest = text
        while rest:
            if len(rest) <= TELEGRAM_SEND_CHUNK_SIZE:
                chunks.append(rest)
                break
            chunk = rest[:TELEGRAM_SEND_CHUNK_SIZE]
            last_nl = chunk.rfind("\n")
            if last_nl > TELEGRAM_SEND_CHUNK_SIZE // 2:
                chunk = chunk[: last_nl + 1]
            else:
                last_space = chunk.rfind(" ")
                if last_space > TELEGRAM_SEND_CHUNK_SIZE // 2:
                    chunk = chunk[: last_space + 1]
            chunks.append(chunk)
            rest = rest[len(chunk) :].lstrip("\n ")
        return chunks

    async def _run_process_loop(
        self,
        request: Any,
        to_handle: str,
        send_meta: dict,
    ) -> None:
        """Override to send continuous typing indicator while processing."""
        chat_id = str(
            (send_meta or {}).get("chat_id")
            or to_handle.removeprefix("telegram:")
        )

        async def _typing_loop() -> None:
            """Send typing every 4s (Telegram clears it after ~5s)."""
            while True:
                await self._send_chat_action(chat_id, "typing")
                await asyncio.sleep(4)

        typing_task = None
        if self._show_typing and chat_id:
            typing_task = asyncio.create_task(_typing_loop())

        try:
            await super()._run_process_loop(request, to_handle, send_meta)
        finally:
            if typing_task:
                typing_task.cancel()

    async def _send_chat_action(
        self,
        chat_id: str,
        action: str = "typing",
    ) -> None:
        """Send chat action (typing, uploading_photo, etc.) to Telegram."""
        if not self.enabled or not self._application:
            return
        bot = self._application.bot
        if not bot:
            return
        try:
            await bot.send_chat_action(chat_id=chat_id, action=action)
        except Exception:
            logger.debug(
                "telegram send_chat_action failed for chat_id=%s",
                chat_id,
            )

    def _build_menu_keyboard(self) -> Any:
        """Build inline keyboard with common actions."""
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            return InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "New Chat", callback_data="/new",
                    ),
                    InlineKeyboardButton(
                        "History", callback_data="/history",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Compact Memory", callback_data="/compact",
                    ),
                    InlineKeyboardButton(
                        "Clear All", callback_data="/clear",
                    ),
                ],
            ])
        except ImportError:
            return None

    def _build_persistent_keyboard(self) -> Any:
        """Build persistent reply keyboard (always visible at bottom)."""
        try:
            from telegram import ReplyKeyboardMarkup, KeyboardButton
            return ReplyKeyboardMarkup(
                [
                    [
                        KeyboardButton("👤 Persona"),
                        KeyboardButton("⚙️ Model"),
                        KeyboardButton("🆕 New Chat"),
                    ],
                    [
                        KeyboardButton("🔧 Skills"),
                        KeyboardButton("📊 Status"),
                        KeyboardButton("🌐 Tasks"),
                    ],
                ],
                resize_keyboard=True,
            )
        except ImportError:
            return None

    async def _fetch_personas(self) -> list[dict]:
        """Fetch personas from local API."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "http://localhost:8088/api/agents/personas",
                    timeout=5,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            logger.debug("telegram: failed to fetch personas")
        return []

    async def _fetch_providers(self) -> list[dict]:
        """Fetch providers with configured API keys."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "http://localhost:8088/api/models",
                    timeout=5,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            logger.debug("telegram: failed to fetch providers")
        return []

    async def _fetch_active_model(self) -> dict:
        """Fetch currently active model."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "http://localhost:8088/api/models/active",
                    timeout=5,
                )
                if r.status_code == 200:
                    return r.json().get("active_llm", {})
        except Exception:
            pass
        return {}

    async def _fetch_skills(self) -> list[dict]:
        """Fetch skills list."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "http://localhost:8088/api/skills",
                    timeout=5,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return []

    async def _fetch_health(self) -> dict:
        """Fetch diagnostics health."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "http://localhost:8088/api/diagnostics/health",
                    timeout=5,
                )
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        return {}

    async def _switch_model(self, provider_id: str, model_name: str) -> bool:
        """Switch active model via API."""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                r = await client.put(
                    "http://localhost:8088/api/models/active",
                    json={
                        "provider_id": provider_id,
                        "model": model_name,
                    },
                    timeout=5,
                )
                return r.status_code == 200
        except Exception:
            return False

    async def _build_personas_keyboard(self, chat_id: str = "") -> Any:
        """Build inline keyboard with personas list."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        personas = await self._fetch_personas()
        if not personas:
            return None
        active_pid = self._chat_persona.get(chat_id, "")
        buttons = []
        for p in personas:
            pid = p.get("id", "")
            name = p.get("name", pid)
            is_coord = p.get("is_coordinator", False)
            mark = " ✓" if pid == active_pid else ""
            emoji = "🎯" if is_coord else "👤"
            label = f"{emoji} {name}{mark}"
            buttons.append([
                InlineKeyboardButton(label, callback_data=f"persona::{pid}")
            ])
        return InlineKeyboardMarkup(buttons)

    async def _build_providers_keyboard(self) -> Any:
        """Build inline keyboard with providers (level 1)."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        providers = await self._fetch_providers()
        active = await self._fetch_active_model()
        active_provider = active.get("provider_id", "")
        buttons = []
        row = []
        for p in providers:
            pid = p.get("id", "")
            models = p.get("models", [])
            if not models:
                continue
            mark = " ✓" if pid == active_provider else ""
            row.append(
                InlineKeyboardButton(
                    f"{pid}{mark}",
                    callback_data=f"provider::{pid}",
                )
            )
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        return InlineKeyboardMarkup(buttons) if buttons else None

    async def _build_models_keyboard(self, provider_id: str) -> Any:
        """Build inline keyboard with models for a provider (level 2)."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        providers = await self._fetch_providers()
        active = await self._fetch_active_model()
        active_model = active.get("model", "")
        active_provider = active.get("provider_id", "")
        buttons = []
        for p in providers:
            if p.get("id") != provider_id:
                continue
            for m in p.get("models", []):
                mid = m.get("id", "") if isinstance(m, dict) else str(m)
                display = m.get("name", mid) if isinstance(m, dict) else str(m)
                mark = " ✓" if (
                    mid == active_model and provider_id == active_provider
                ) else ""
                buttons.append([
                    InlineKeyboardButton(
                        f"{display}{mark}",
                        callback_data=f"model::{provider_id}::{mid}",
                    )
                ])
            break
        buttons.append([
            InlineKeyboardButton("⬅️ Back", callback_data="back::providers")
        ])
        return InlineKeyboardMarkup(buttons)

    async def _handle_menu_command(
        self, chat_id: str, command: str, *, meta: Optional[dict] = None,
    ) -> bool:
        """Handle menu button commands. Returns True if handled."""
        bot = self._application.bot if self._application else None
        if not bot:
            return False

        if command == "/start":
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "👋 Welcome to AdClaw!\n\n"
                    "Use the menu below or type a message to chat."
                ),
                reply_markup=self._build_persistent_keyboard(),
            )
            return True

        if command == "/new":
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Yes, reset", callback_data="confirm_new::yes",
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data="confirm_new::no",
                ),
            ]])
            await bot.send_message(
                chat_id=chat_id,
                text="🆕 Start a new chat? This will clear the current session.",
                reply_markup=kb,
            )
            return True

        if command in ("👤 Persona", "/personas"):
            kb = await self._build_personas_keyboard(chat_id)
            if kb:
                await bot.send_message(
                    chat_id=chat_id,
                    text="🎭 Choose a persona:",
                    reply_markup=kb,
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text="No personas configured.",
                )
            return True

        if command in ("⚙️ Model", "/model"):
            kb = await self._build_providers_keyboard()
            if kb:
                await bot.send_message(
                    chat_id=chat_id,
                    text="⚙️ Select provider:",
                    reply_markup=kb,
                )
            else:
                await bot.send_message(
                    chat_id=chat_id,
                    text="No providers with models available.",
                )
            return True

        if command == "🆕 New Chat":
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Yes, reset", callback_data="confirm_new::yes",
                ),
                InlineKeyboardButton(
                    "Cancel", callback_data="confirm_new::no",
                ),
            ]])
            await bot.send_message(
                chat_id=chat_id,
                text="🆕 Start a new chat? This will clear the current session.",
                reply_markup=kb,
            )
            return True

        if command in ("🔧 Skills", "/skills") or (
            isinstance(command, str) and command.startswith("skills_page::")
        ):
            page = 0
            if isinstance(command, str) and command.startswith("skills_page::"):
                page = int(command.split("::")[1])
            skills = await self._fetch_skills()
            if not skills:
                await bot.send_message(
                    chat_id=chat_id, text="No skills loaded.",
                )
                return True
            enabled = [s for s in skills if s.get("enabled", True)]
            per_page = 10
            total_pages = (len(enabled) + per_page - 1) // per_page
            page = max(0, min(page, total_pages - 1))
            start = page * per_page
            chunk = enabled[start:start + per_page]
            lines = [f"🔧 Skills ({start+1}-{start+len(chunk)} of {len(enabled)}):"]
            for s in chunk:
                name = s.get("name", "?")
                sec = s.get("security")
                score = f" ({sec['score']}/100)" if sec else ""
                lines.append(f"  🟢 {name}{score}")
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton(
                    "◀️ Prev", callback_data=f"skills_page::{page-1}",
                ))
            if page < total_pages - 1:
                nav.append(InlineKeyboardButton(
                    "Next ▶️", callback_data=f"skills_page::{page+1}",
                ))
            kb = InlineKeyboardMarkup([nav]) if nav else None
            await bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                reply_markup=kb,
            )
            return True

        if command in ("📊 Status", "/status"):
            active = await self._fetch_active_model()
            personas = await self._fetch_personas()
            skills = await self._fetch_skills()
            health = await self._fetch_health()
            active_pid = self._chat_persona.get(chat_id, "coordinator")
            persona_name = active_pid
            for p in personas:
                if p.get("id") == active_pid:
                    persona_name = p.get("name", active_pid)
                    break
            model_name = active.get("model", "unknown")
            provider = active.get("provider_id", "unknown")
            enabled_skills = len(
                [s for s in skills if s.get("enabled", True)]
            )
            uptime = health.get("uptime_seconds", 0)
            h, m = int(uptime // 3600), int((uptime % 3600) // 60)
            status = health.get("status", "unknown")
            lines = [
                "📊 *Current Status*",
                f"├ Persona: {persona_name}",
                f"├ Model: {model_name} ({provider})",
                f"├ Skills: {enabled_skills} active",
                f"├ Health: {status}",
                f"└ Uptime: {h}h {m}m",
            ]
            await bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode="Markdown",
            )
            return True

        if command in ("🌐 Tasks", "/tasks"):
            # Forward to agent so it uses agenthub-worker skill
            content_parts = [
                TextContent(
                    type=ContentType.TEXT,
                    text="Show me open tasks on AgentHub",
                ),
            ]
            meta = {
                "chat_id": chat_id,
                "user_id": chat_id,
                "username": "",
                "message_id": "",
                "is_group": False,
                "has_bot_command": True,
            }
            native = {
                "channel_id": self.channel,
                "sender_id": chat_id,
                "content_parts": content_parts,
                "meta": meta,
            }
            if self._enqueue is not None:
                self._enqueue(native)
            return True

        # /clear bypasses queue — directly resets session
        if command == "/clear":
            # Debounce key is sender_id (user_id), not chat_id (differs in groups)
            sender_id = (meta or {}).get("user_id") or chat_id
            await self._force_clear_session(chat_id, sender_id)
            return True

        # Forward agent-handled commands (/compact, /history)
        if command in ("/compact", "/history"):
            content_parts = [
                TextContent(type=ContentType.TEXT, text=command),
            ]
            meta = {
                "chat_id": chat_id,
                "user_id": chat_id,
                "username": "",
                "message_id": "",
                "is_group": False,
                "has_bot_command": True,
            }
            native = {
                "channel_id": self.channel,
                "sender_id": chat_id,
                "content_parts": content_parts,
                "meta": meta,
            }
            if self._enqueue is not None:
                self._enqueue(native)
            return True

        return False

    async def _force_clear_session(
        self, chat_id: str, sender_id: Optional[str] = None,
    ) -> None:
        """Clear session bypassing the message queue entirely."""
        if not chat_id:
            logger.warning("_force_clear_session: empty chat_id")
            return
        bot = self._application.bot if self._application else None
        # Debounce key is sender_id (= user_id); fallback to chat_id for private chats
        key = sender_id or chat_id
        mgr = self._channel_manager
        if mgr:
            await mgr.force_clear_session(self.channel, key)
        else:
            logger.warning("_force_clear_session: no channel_manager wired")
        if bot:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "*History Cleared!*\n\n"
                    "- Session reset\n"
                    "- Memory is now empty\n"
                    "- Ready for new conversation"
                ),
                parse_mode="Markdown",
                reply_markup=self._build_persistent_keyboard(),
            )

    async def send_system_message(self, to: str, text: str) -> None:
        """Send a system message to the user (for timeout notifications)."""
        bot = self._application.bot if self._application else None
        if bot:
            await bot.send_message(chat_id=to, text=text)

    async def send(
        self,
        to_handle: str,
        text: str,
        meta: Optional[dict] = None,
    ) -> None:
        """Send text to chat_id (to_handle or meta['chat_id'])."""
        if not self.enabled or not self._application:
            return
        if meta is None:
            meta = {}
        chat_id = meta.get("chat_id") or to_handle
        if not chat_id:
            logger.warning("telegram send: no chat_id in to_handle or meta")
            return
        bot = self._application.bot
        if not bot:
            return
        if self._show_typing:
            asyncio.create_task(self._send_chat_action(chat_id, "typing"))
        chunks = self._chunk_text(text)
        for i, chunk in enumerate(chunks):
            try:
                # Attach persistent keyboard on bot command responses
                reply_markup = None
                if i == len(chunks) - 1 and meta.get("has_bot_command"):
                    reply_markup = self._build_persistent_keyboard()
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode="Markdown",
                        reply_markup=reply_markup,
                    )
                except Exception:
                    # Markdown parsing failed — retry as plain text
                    await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        reply_markup=reply_markup,
                    )
            except Exception:
                logger.exception("telegram send_message failed")
                return

    async def send_media(
        self,
        to_handle: str,
        part: OutgoingContentPart,
        meta: Optional[dict] = None,
    ) -> None:
        """Send a media part (image, video, audio, file) to chat_id."""
        if not self.enabled or not self._application:
            return
        meta = meta or {}
        chat_id = meta.get("chat_id") or to_handle
        if not chat_id:
            logger.warning(
                "telegram send_media: no chat_id in to_handle or meta",
            )
            return
        bot = self._application.bot
        if not bot:
            return

        part_type = getattr(part, "type", None)
        try:
            if part_type == ContentType.IMAGE:
                image_url = getattr(part, "image_url", None)
                if image_url and image_url.startswith("file://"):
                    local_path = image_url.replace("file://", "")
                    with open(local_path, "rb") as f:
                        await bot.send_photo(chat_id=chat_id, photo=f)
                elif image_url:
                    await bot.send_photo(chat_id=chat_id, photo=image_url)
            elif part_type == ContentType.VIDEO:
                video_url = getattr(part, "video_url", None)
                if video_url and video_url.startswith("file://"):
                    local_path = video_url.replace("file://", "")
                    with open(local_path, "rb") as f:
                        await bot.send_video(chat_id=chat_id, video=f)
                elif video_url:
                    await bot.send_video(chat_id=chat_id, video=video_url)
            elif part_type == ContentType.AUDIO:
                data = getattr(part, "data", None)
                if data:
                    await bot.send_audio(chat_id=chat_id, audio=data)
            elif part_type == ContentType.FILE:
                file_url = getattr(part, "file_url", None)
                if file_url and file_url.startswith("file://"):
                    local_path = file_url.replace("file://", "")
                    with open(local_path, "rb") as f:
                        await bot.send_document(chat_id=chat_id, document=f)
                elif file_url:
                    await bot.send_document(chat_id=chat_id, document=file_url)
        except Exception:
            logger.exception("telegram send_media failed")

    async def _run_polling(self) -> None:
        """Run Telegram bot in existing event loop (FastAPI/uvicorn).
        Do not use run_polling() - it calls run_until_complete() and fails when
        the event loop is already running.
        """
        if not self.enabled or not self._application or not self._bot_token:
            return
        try:
            from telegram.error import TelegramError
            from telegram import BotCommand

            def _on_poll_error(exc: TelegramError) -> None:
                self._application.create_task(
                    self._application.process_error(error=exc, update=None),
                )

            await self._application.initialize()

            commands = [
                BotCommand("start", "Start a new conversation"),
                BotCommand("personas", "Switch persona"),
                BotCommand("model", "Switch LLM model"),
                BotCommand("new", "New conversation (clear memory)"),
                BotCommand("skills", "View active skills"),
                BotCommand("status", "Current status"),
                BotCommand("compact", "Compact conversation memory"),
                BotCommand("clear", "Clear conversation history"),
                BotCommand("history", "Show conversation history"),
                BotCommand("tasks", "Browse AgentHub tasks"),
            ]
            try:
                await self._application.bot.set_my_commands(commands)
                logger.info(
                    "telegram: registered %d bot commands",
                    len(commands),
                )
            except Exception:
                logger.warning(
                    "telegram: failed to register commands (non-fatal)",
                )

            await self._application.updater.start_polling(
                allowed_updates=[
                    "message",
                    "edited_message",
                    "callback_query",
                ],
                error_callback=_on_poll_error,
            )
            await self._application.start()
            logger.info("telegram: polling started (receiving updates)")
            await asyncio.Future()  # never completes until cancelled
        except asyncio.CancelledError:
            logger.debug("telegram: polling cancelled")
            raise
        except Exception:
            logger.exception(
                "telegram: polling error (check token, network, proxy; "
                "in China you may need TELEGRAM_HTTP_PROXY)",
            )
            raise

    async def start(self) -> None:
        if not self.enabled or not self._application:
            logger.debug(
                "telegram: start() skipped (enabled=%s, application=%s)",
                self.enabled,
                "built" if self._application else "not built",
            )
            return
        self._task = asyncio.create_task(
            self._run_polling(),
            name="telegram_polling",
        )
        logger.info("telegram: channel started (polling task created)")

    async def stop(self) -> None:
        if not self.enabled:
            return
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass
            self._task = None
        if self._application:
            try:
                updater = getattr(self._application, "updater", None)
                if updater and getattr(updater, "running", False):
                    await updater.stop()
                if getattr(self._application, "running", False):
                    await self._application.stop()
                await self._application.shutdown()
            except Exception as exc:
                logger.debug("telegram stop: %s", exc)

    def resolve_session_id(
        self,
        sender_id: str,
        channel_meta: Optional[dict] = None,
    ) -> str:
        """Session by chat_id (one session per chat)."""
        meta = channel_meta or {}
        chat_id = meta.get("chat_id")
        if chat_id:
            return f"telegram:{chat_id}"
        return f"telegram:{sender_id}"

    def get_to_handle_from_request(self, request: Any) -> str:
        """Send target is chat_id from meta or session_id suffix."""
        meta = getattr(request, "channel_meta", None) or {}
        chat_id = meta.get("chat_id")
        if chat_id:
            return str(chat_id)
        sid = getattr(request, "session_id", "")
        if sid.startswith("telegram:"):
            return sid.split(":", 1)[-1]
        return getattr(request, "user_id", "") or ""

    def build_agent_request_from_native(self, native_payload: Any) -> Any:
        """Build AgentRequest from Telegram native dict."""
        payload = native_payload if isinstance(native_payload, dict) else {}
        channel_id = payload.get("channel_id") or self.channel
        sender_id = payload.get("sender_id") or ""
        content_parts = payload.get("content_parts") or []
        meta = payload.get("meta") or {}
        session_id = self.resolve_session_id(sender_id, meta)
        user_id = str(meta.get("user_id") or sender_id)
        request = self.build_agent_request_from_user_content(
            channel_id=channel_id,
            sender_id=sender_id,
            session_id=session_id,
            content_parts=content_parts,
            channel_meta=meta,
        )
        request.user_id = user_id
        request.channel_meta = meta
        return request

    def to_handle_from_target(self, *, user_id: str, session_id: str) -> str:
        """Cron dispatch: use session_id suffix as chat_id."""
        if session_id.startswith("telegram:"):
            return session_id.split(":", 1)[-1]
        return user_id
