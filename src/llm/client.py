import json
import time
from typing import TypeVar

import structlog
from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, RateLimitError
from openai import APIStatusError
from pydantic import BaseModel, ValidationError

from src.settings import settings
from src.utils.retry import async_retry

log = structlog.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# Транзиентные ошибки сети/инфры — ретраим. 5xx ловим через APIStatusError по коду.
_TRANSIENT = (RateLimitError, APIConnectionError, APITimeoutError)


class _ServerError(Exception):
    """Внутренний маркер для ретраев на 5xx."""


class OpenAIClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def complete_json(
        self,
        system: str,
        user: str,
        model: str,
        response_schema: type[T],
    ) -> tuple[T, int]:
        # Первая попытка
        try:
            return await self._call(system, user, model, response_schema)
        except ValidationError as e:
            log.warning("llm.invalid_json_retry", error=str(e)[:300])
            # Одна повторная попытка с подсказкой
            hint = (
                user
                + "\n\n[STRICT] Return only valid JSON matching the schema. "
                "No prose, no markdown fences."
            )
            return await self._call(system, hint, model, response_schema)

    @async_retry(attempts=3, base_delay=1.0, exceptions=_TRANSIENT + (_ServerError,))
    async def _call(
        self,
        system: str,
        user: str,
        model: str,
        response_schema: type[T],
    ) -> tuple[T, int]:
        t0 = time.monotonic()
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
        except APIStatusError as e:
            if 500 <= e.status_code < 600:
                raise _ServerError(str(e)) from e
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        log_fields = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
        }
        if settings.OPENAI_PRICE_PER_1K_INPUT and settings.OPENAI_PRICE_PER_1K_OUTPUT:
            cost = (
                prompt_tokens / 1000 * settings.OPENAI_PRICE_PER_1K_INPUT
                + completion_tokens / 1000 * settings.OPENAI_PRICE_PER_1K_OUTPUT
            )
            log_fields["cost_usd"] = round(cost, 6)
        log.info("llm.call", **log_fields)

        content = resp.choices[0].message.content or "{}"
        data = json.loads(content)
        parsed = response_schema.model_validate(data)
        return parsed, total_tokens

    @async_retry(attempts=3, base_delay=1.0, exceptions=_TRANSIENT + (_ServerError,))
    async def complete_text(
            self,
            system: str,
            user: str,
            model: str,
    ) -> tuple[str, int]:
        """Plain-text completion с ретраями и логом стоимости."""
        t0 = time.monotonic()
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
            )
        except APIStatusError as e:
            if 500 <= e.status_code < 600:
                raise _ServerError(str(e)) from e
            raise

        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = resp.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        total_tokens = usage.total_tokens if usage else 0

        log_fields = {
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
        }
        if settings.OPENAI_PRICE_PER_1K_INPUT and settings.OPENAI_PRICE_PER_1K_OUTPUT:
            cost = (
                    prompt_tokens / 1000 * settings.OPENAI_PRICE_PER_1K_INPUT
                    + completion_tokens / 1000 * settings.OPENAI_PRICE_PER_1K_OUTPUT
            )
            log_fields["cost_usd"] = round(cost, 6)
        log.info("llm.call", **log_fields)

        text = resp.choices[0].message.content or ""
        return text, total_tokens

# Singleton
_client: OpenAIClient | None = None


def get_client() -> OpenAIClient:
    global _client
    if _client is None:
        _client = OpenAIClient()
    return _client