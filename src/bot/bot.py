from __future__ import annotations

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import TelegramObject, Message
from aiogram import BaseMiddleware
from typing import Any, Awaitable, Callable

from src.settings import settings

log = structlog.get_logger(__name__)

_bot: Bot | None = None


def get_bot() -> Bot:
    """Singleton-доступ к Bot. Используется и хендлерами, и deliver."""
    global _bot
    if _bot is None:
        _bot = Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=None),
        )
    return _bot


class AuthMiddleware(BaseMiddleware):
    """Пропускает только сообщения от TELEGRAM_USER_ID."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            uid = event.from_user.id if event.from_user else None
            if uid != settings.TELEGRAM_USER_ID:
                log.warning("unauthorized_access", user_id=uid)
                return  # игнор
        return await handler(event, data)


def build_bot() -> tuple[Bot, Dispatcher]:
    """Для использования в main.run (бот + scheduler в одном loop)."""
    from src.bot.handlers import router

    bot = get_bot()
    dp = Dispatcher()
    dp.message.middleware(AuthMiddleware())
    dp.include_router(router)
    return bot, dp


async def run_bot() -> None:
    bot, dp = build_bot()
    log.info("bot_starting")
    await dp.start_polling(bot)