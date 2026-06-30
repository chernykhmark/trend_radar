"""APScheduler: ежедневный collect+score, еженедельный digest+deliver."""
from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.pipeline.collect import run_collect
from src.pipeline.deliver import deliver_digest
from src.pipeline.digest import run_digest
from src.pipeline.score import run_score
from src.settings import settings

log = structlog.get_logger(__name__)


async def daily_pipeline() -> dict:
    """collect → score. Возвращает агрегированную статистику."""
    log.info("daily_pipeline.start")
    collect_stats = await run_collect()                   # dict[source_name, int]
    collected_total = sum(collect_stats.values()) if collect_stats else 0
    score_result = await run_score(limit=200)             # обычно dict|str
    stats = {
        "collected": collected_total,
        "by_source": collect_stats,
        "score": score_result,
    }
    log.info("daily_pipeline.done", **stats)
    return stats


async def weekly_pipeline(days: int = 7, min_relevance: int = 6) -> dict:
    """digest → deliver."""
    log.info("weekly_pipeline.start", days=days)
    digest_id = await run_digest(
        days=days,
        min_relevance=min_relevance,
        exclude_delivered=True,
        is_manual=False,
    )
    if digest_id is None:
        log.info("weekly_pipeline.nothing_to_digest")
        return {"digest_id": None, "delivered": 0}

    delivered = await deliver_digest(digest_id)
    log.info("weekly_pipeline.done", digest_id=digest_id, delivered=delivered)
    return {"digest_id": digest_id, "delivered": delivered}


async def _safe_daily() -> None:
    try:
        await daily_pipeline()
    except Exception:
        log.exception("daily_job.failed")


async def _safe_weekly() -> None:
    try:
        await weekly_pipeline()
    except Exception:
        log.exception("weekly_job.failed")


def build_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.TZ)

    scheduler.add_job(
        _safe_daily,
        trigger=CronTrigger.from_crontab(settings.COLLECT_CRON, timezone=settings.TZ),
        id="daily_job",
        name="collect+score",
        misfire_grace_time=3600,
        coalesce=True,
    )
    scheduler.add_job(
        _safe_weekly,
        trigger=CronTrigger.from_crontab(settings.DIGEST_CRON, timezone=settings.TZ),
        id="weekly_job",
        name="digest+deliver",
        misfire_grace_time=3600,
        coalesce=True,
    )

    log.info(
        "scheduler.built",
        tz=settings.TZ,
        collect_cron=settings.COLLECT_CRON,
        digest_cron=settings.DIGEST_CRON,
    )
    return scheduler