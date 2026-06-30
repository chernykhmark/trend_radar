from datetime import datetime, timedelta, timezone
from pathlib import Path

import structlog
import yaml

from src.db.engine import AsyncSessionLocal as async_session_maker
from src.db.repository import (
    get_last_collected_at,
    upsert_posts,
    upsert_source,
)
from src.sources.registry import build_source

log = structlog.get_logger(__name__)

CONFIG_PATH = Path("config/sources.yaml")
COLD_START_WINDOW = timedelta(days=7)


def _load_sources_config() -> list[dict]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("sources", []) or []


async def run_collect() -> dict[str, int]:
    stats: dict[str, int] = {}
    sources_cfg = _load_sources_config()
    now = datetime.now(timezone.utc)

    for cfg in sources_cfg:
        name = cfg.get("name")
        if not name:
            log.warning("collect.source_skipped_no_name", cfg=cfg)
            continue
        if not cfg.get("enabled", True):
            log.info("collect.source_disabled", source=name)
            continue

        try:
            async with async_session_maker() as session:
                source_id = await upsert_source(
                    session, name=name, type_=cfg["type"], config=cfg.get("params", {}) or {}
                )
                last = await get_last_collected_at(session, source_id)

            since = max(last, now - COLD_START_WINDOW) if last else now - COLD_START_WINDOW

            source = build_source(cfg)
            posts = await source.fetch(since)

            async with async_session_maker() as session:
                new_count = await upsert_posts(session, source_id, posts)

            stats[name] = new_count
            log.info("collect.done", source=name, found=len(posts), new=new_count)

        except Exception:
            log.exception("collect.source_failed", source=name)
            stats[name] = 0
            continue

    return stats