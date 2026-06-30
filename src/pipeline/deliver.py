from __future__ import annotations

import structlog
from aiogram.exceptions import TelegramBadRequest

from src.bot.bot import get_bot
from src.db.engine import AsyncSessionLocal as async_session
from src.db.repository import get_digest, mark_digest_delivered
from src.settings import settings

log = structlog.get_logger(__name__)

MAX_LEN = 4000


def _split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    """Режет текст по \\n\\n, при необходимости — по \\n, в крайнем — жёстко."""
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            parts.append(buf.rstrip())
            buf = ""

    for block in text.split("\n\n"):
        candidate = (buf + "\n\n" + block) if buf else block
        if len(candidate) <= limit:
            buf = candidate
            continue
        # block не лезет в текущий буфер
        flush()
        if len(block) <= limit:
            buf = block
        else:
            # режем по \n
            for line in block.split("\n"):
                cand2 = (buf + "\n" + line) if buf else line
                if len(cand2) <= limit:
                    buf = cand2
                else:
                    flush()
                    if len(line) <= limit:
                        buf = line
                    else:
                        # крайний случай — жёсткий слайс
                        for i in range(0, len(line), limit):
                            chunk = line[i : i + limit]
                            if len(buf) + len(chunk) + 1 <= limit:
                                buf = (buf + "\n" + chunk) if buf else chunk
                            else:
                                flush()
                                buf = chunk
    flush()
    return parts


async def deliver_digest(digest_id: int) -> None:
    async with async_session() as session:
        content_md, post_ids = await get_digest(session, digest_id)

    parts = _split_message(content_md)
    bot = get_bot()
    chat_id = settings.TELEGRAM_USER_ID

    for idx, part in enumerate(parts, 1):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=part,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except TelegramBadRequest as e:
            log.warning("markdown_failed_fallback_plain", digest_id=digest_id, part=idx, err=str(e))
            await bot.send_message(
                chat_id=chat_id,
                text=part,
                disable_web_page_preview=True,
            )

    async with async_session() as session:
        await mark_digest_delivered(session, digest_id, post_ids)

    log.info("digest_delivered", digest_id=digest_id, parts=len(parts), posts=len(post_ids))