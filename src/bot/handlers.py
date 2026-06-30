from __future__ import annotations

import structlog
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from src.bot.keyboards import (
    BTN_DIGEST_TODAY,
    BTN_DIGEST_WEEK,
    BTN_HELP,
    BTN_STATUS,
    main_kb,
)
from src.db.engine import AsyncSessionLocal as async_session
from src.db.repository import get_status_stats
from src.pipeline.deliver import deliver_digest
from src.pipeline.digest import run_digest
from src.scheduler import daily_pipeline

log = structlog.get_logger(__name__)
router = Router()

from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

HELP_TEXT = (
    "Доступные действия (через кнопки внизу):\n\n"
    "📰 Дайджест за неделю — посты за последние 7 дней (только новые)\n"
    "☀️ Дайджест сегодня — только посты за последние сутки\n"
    "📊 Статус — статистика по базе\n"
    "❓ Помощь — это сообщение\n\n"
    "Служебные команды:\n"
    "/run_collect — принудительно запустить сбор и оценку"
)


# ---------- /start, /help и кнопка «Помощь» ----------

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я Trend Radar. Используй кнопки ниже.",
        reply_markup=main_kb,
    )


@router.message(Command("help"))
@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_kb)


# ---------- Статус ----------

def _fmt_dt(dt: datetime | None) -> str:
    if not dt:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M")


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message) -> None:
    try:
        async with async_session() as session:
            stats = await get_status_stats(session)
        text = (
            f"📊 *Статус*\n\n"
            f"Постов всего: *{stats['posts_total']}*\n"
            f"Оценено: *{stats['posts_scored']}*\n"
            f"Последний collect: {_fmt_dt(stats['last_collected_at'])}\n"
            f"Последний дайджест: {_fmt_dt(stats['last_digest_sent_at'])}\n"
            f"Дайджестов отправлено: *{stats['digests_sent_count']}*"
        )
        await message.answer(text, reply_markup=main_kb, parse_mode="Markdown")
    except Exception:
        log.exception("status_failed")
        await message.answer("Произошла ошибка, проверь логи", reply_markup=main_kb)

# ---------- Дайджесты ----------

async def _handle_digest(message: Message, days: int, label: str) -> None:
    """
    days=7  → недельный (ручной аналог авто-рассылки)
    days=1  → только за последние сутки
    В обоих случаях exclude_delivered=True: уже отправленные посты не дублируются.
    """
    try:
        await message.answer(f"⏳ Собираю {label}…", reply_markup=main_kb)
        digest_id = await run_digest(
            days=days,
            exclude_delivered=True,
            is_manual=True,
        )
        if digest_id is None:
            await message.answer(
                "За этот период новых постов нет 🙂",
                reply_markup=main_kb,
            )
            return
        await deliver_digest(digest_id)
    except Exception:
        log.exception("digest_handler_failed", days=days)
        await message.answer("Произошла ошибка, проверь логи", reply_markup=main_kb)


@router.message(Command("digest"))
@router.message(F.text == BTN_DIGEST_WEEK)
async def cmd_digest_week(message: Message) -> None:
    await _handle_digest(message, days=7, label="дайджест за неделю")


@router.message(Command("digest_today"))
@router.message(F.text == BTN_DIGEST_TODAY)
async def cmd_digest_today(message: Message) -> None:
    await _handle_digest(message, days=1, label="дайджест за сегодня")


# ---------- Служебное ----------

@router.message(Command("run_collect"))
async def cmd_run_collect(message: Message) -> None:
    await message.answer("⏳ collect + score…", reply_markup=main_kb)
    try:
        stats = await daily_pipeline()
        by_src = "\n".join(
            f"  {k}: +{v}" for k, v in (stats.get("by_source") or {}).items()
        )
        await message.answer(
            f"✅ Готово\n"
            f"Собрано всего: {stats['collected']}\n"
            f"{by_src}\n"
            f"Score: {stats['score']}",
            reply_markup=main_kb,
        )
    except Exception as e:
        log.exception("run_collect_failed")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_kb)