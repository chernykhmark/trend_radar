
# PROMPTS.md

Промпты для пошаговой реализации Trend Radar. Каждый промпт прикрепляется в новую сессию вместе с актуальным `ARCHITECTURE.md`.




**Общие правила для всех этапов:**
- ARCHITECTURE.md — единый источник правды. При противоречии между промптом и архитектурой — приоритет у архитектуры, исполнитель обязан сообщить о расхождении.
- Контракты раздела 6 (`RawPost`, `PostScore`, `BaseSource`) — неизменны без явной правки ARCHITECTURE.md.
- Структура папок — строго по разделу 5.
- CLI — `typer` (раздел 2 ARCHITECTURE.md), без альтернатив.
- Все межмодульные обмены — через pydantic-модели из `schemas/` (принцип 3.2), не через ORM-объекты.
- Все `datetime` — UTC.
- Каждый ответ заканчивается блоком **"Как проверить"** с точными командами.

---

## Промпт для Этапа 1: Скелет проекта + БД

````
Прикреплён ARCHITECTURE.md — единый источник правды. Прочитай разделы 4, 5, 8, 12 (Этап 1), 13, 14.

Задача: реализуй **Этап 1 (Скелет проекта + БД)**.

Требования:
1. Структура папок — строго по разделу 5 ARCHITECTURE.md.
2. Создай все файлы Этапа 1 из раздела 12.
3. `db/models.py` — SQLAlchemy 2.x declarative, типизированный (`Mapped[...]`), все таблицы из раздела 4. Поле `posts.rating INTEGER NULL` обязательно.
4. `db/init.sql` — DDL всех таблиц + `UNIQUE(source_id, external_id)` на `posts` + индексы на `posts.published_at`, `post_scores.scored_at`, `digests.sent_at`, `delivery_log.post_id`. Поле `rating` обязательно.
5. `db/engine.py` — async-движок SQLAlchemy на `asyncpg`, фабрика `AsyncSession`.
6. `settings.py` — pydantic-settings, читает `.env`, типизированные поля под все переменные раздела 8. Добавь опциональные `OPENAI_PRICE_PER_1K_INPUT: float | None = None` и `OPENAI_PRICE_PER_1K_OUTPUT: float | None = None` (понадобятся позже для лога стоимости LLM).
7. `Dockerfile` — `python:3.11-slim`, ставим `requirements.txt`, копируем `src/` и `config/`.
8. `docker-compose.yml` — сервис `app`, подключается к внешней Postgres по `DATABASE_URL`, `restart: unless-stopped`, монтирует `./config` как volume. Команда запуска по умолчанию — `python -m src.main run` (на Этапе 1 эта команда выводит "service started" и спит; в Этапе 6 обретёт полное содержание). Это сделано намеренно, чтобы не менять compose-файл между этапами.
9. `main.py` — CLI на `typer` с командой `run` (заглушка: инициализация логгера, лог "service started", `asyncio.sleep` в бесконечном цикле). Никаких других команд на Этапе 1.
10. `utils/logging.py` — structlog в JSON, уровень из `LOG_LEVEL`.
11. `utils/retry.py` — оставить пустым с TODO-комментарием (наполнится в Этапе 3).
12. `requirements.txt` — только: `sqlalchemy`, `asyncpg`, `pydantic-settings`, `structlog`, `typer`. Последние стабильные версии.
13. `.env.example` — все переменные раздела 8 + `OPENAI_PRICE_PER_1K_INPUT`, `OPENAI_PRICE_PER_1K_OUTPUT` (закомментированные, опциональные).
14. `README.md` — короткий: что за проект, как запустить Этап 1.

Дополнительно:
- `schemas/__init__.py` создать пустым (модули добавляются по этапам).
- `sources/`, `llm/`, `pipeline/`, `bot/` — НЕ создавать на Этапе 1, появятся позже.
- Никакого Alembic.

В конце — блок **"Как проверить"**:
- `cp .env.example .env` и заполнение `DATABASE_URL`.
- `docker compose build`.
- Применение `init.sql` к Postgres (команда `psql`).
- `docker compose up app` — видим "service started" в логах.
- `psql ... -c "\dt"` — все 6 таблиц на месте.
````



---

## Промпт для Этапа 2: Источник Habr + collect

````
Прикреплён ARCHITECTURE.md. Этап 1 реализован (структура, БД, init.sql, settings, логгер, заглушка `main.py run`).

Задача: реализуй **Этап 2 (Источник Habr + Pipeline.collect)**.

Требования:
1. `schemas/post.py` — pydantic-модель `RawPost` строго по контракту раздела 6 ARCHITECTURE.md. **Файл именно `post.py`, не `raw_post.py`** (раздел 5 — основной источник). Если в разделе 12 встречается `raw_post.py` — это опечатка, ориентируйся на раздел 5.

2. `sources/__init__.py` — пустой.

3. `sources/base.py` — абстрактный `BaseSource` строго по разделу 6:
   ```python
   class BaseSource(ABC):
       name: str
       type: str
       @abstractmethod
       async def fetch(self, since: datetime) -> list[RawPost]: ...
   ```

4. `sources/registry.py` — словарь `SOURCE_TYPES: dict[str, type[BaseSource]]` + функция `build_source(config: dict) -> BaseSource`, создающая инстанс по полю `type` с `params` из YAML.

5. `sources/habr.py` — `HabrSource(BaseSource)`:
   - RSS: `https://habr.com/ru/rss/hub/{hub}/all/?fl=ru`.
   - `feedparser` оборачивай в `asyncio.to_thread` (никакого блокирующего I/O в async).
   - Извлечение `rating`: best effort. Способ выбираешь сам (раздел 14: можно через HTML-страницу поста, можно — оставлять `None`). Если `None` — фильтр `min_rating` пропускается.
   - Фильтр по `since` (только посты с `published_at > since`).
   - `external_id` — стабильный (например, ID из URL `/articles/{id}/`).
   - `published_at` приводи к UTC.
   - Все ошибки парсинга отдельных постов — лог `WARNING`, пост пропускается, остальные обрабатываются.

6. `config/sources.yaml` — 2-3 хаба (например, `machine-learning`, `python`, `analytics`) по формату раздела 7.

7. `db/repository.py` — методы:
   - `async def upsert_source(session, name: str, type_: str, config: dict) -> int` (возвращает `source_id`)
   - `async def upsert_posts(session, source_id: int, posts: list[RawPost]) -> int` (возвращает число новых, `INSERT ... ON CONFLICT (source_id, external_id) DO NOTHING`)
   - `async def get_last_collected_at(session, source_id: int) -> datetime | None`
   - На вход и выход — pydantic-модели или примитивы, не ORM-объекты наружу.

8. `pipeline/__init__.py` — пустой.

9. `pipeline/collect.py`:
   - `async def run_collect() -> dict[str, int]` — статистика `{source_name: new_posts_count}`.
   - Читает `config/sources.yaml`.
   - Для каждого enabled-источника: `upsert_source` → определение `since = max(last_collected_at, now - 7d)` (на холодном старте `now - 7d`) → `build_source(cfg).fetch(since)` → `upsert_posts`.
   - Падение одного источника не валит весь collect: `try/except` с `log.exception`, переход к следующему.
   - Структурное логирование: `source`, `found`, `new`.

10. `main.py` — добавь команду `collect` (через `typer`), запускающую `asyncio.run(run_collect())` и печатающую итоговую статистику. Команда `run` остаётся заглушкой.

11. `requirements.txt` — добавь `feedparser`, `httpx`, `beautifulsoup4`, `pyyaml`.

Ограничения:
- Не трогай LLM, бот, scheduler, `llm/`, `bot/`, `scheduler.py`.
- Контракт `RawPost` — неизменен.
- Технические детали (User-Agent, таймауты httpx, формат `raw`, точные селекторы HTML) — принимай сам по разделу 14.

В конце — **"Как проверить"**:
- `docker compose run --rm app python -m src.main collect`
- `psql $DATABASE_URL -c "SELECT s.name, count(p.*) FROM sources s LEFT JOIN posts p ON p.source_id=s.id GROUP BY s.name;"`
- Повторный запуск `collect` — число новых постов = 0 (идемпотентность).
````

---

## Промпт для Этапа 3: LLM-оценка постов

````
Прикреплён ARCHITECTURE.md. Этапы 1-2 реализованы: посты собираются в `posts`.

Задача: реализуй **Этап 3 (LLM-оценка постов)**.

Требования:

1. `config/prompts/user_profile.md` — профиль пользователя:
   - Системный аналитик и инженер данных.
   - Интересы: проектирование систем, прикладная работа с данными, запуск MVP, автоматизация, продуктовые идеи, профессиональный путь.
   - Целевые сегменты: SMB, стартапы, продуктовые команды.
   Формулируй так, чтобы LLM использовала это для оценки релевантности.

2. `config/prompts/score_post.md` — промпт оценки одного поста:
   - Используй плейсхолдеры в формате `$variable` (для `string.Template.safe_substitute`).
   - **System-часть**: роль — аналитик контента, ориентация на профиль пользователя.
   - **User-часть**: `$profile` + `$source_name` + `$title` + `$author` + `$content`.
   - Требование вернуть СТРОГО JSON по схеме `PostScore`:
     - `relevance_score`: 0-10 (0 = нерелевантно, 10 = идеально).
     - `category`: `trend | pain | case | idea | other`.
     - `summary`: 1-2 предложения по-русски.
     - `topics`: 1-5 тегов.
   - Критерии категорий:
     - `trend` — обсуждение технологии/подхода, набирающего популярность.
     - `pain` — жалоба, вопрос, нерешённая проблема.
     - `case` — описание реализованного решения, MVP, продукта.
     - `idea` — концепция, гипотеза, предложение.
     - `other` — новости, мнения без конкретики.
   - Структура промпта (system/user разделы) оформи комментариями или явными секциями — формат на твоё усмотрение, скорер должен уметь распарсить.

3. `schemas/score.py` — pydantic `PostScore` строго по контракту раздела 6.

4. `schemas/post.py` — добавь DTO `PostForScoring`:
   ```python
   class PostForScoring(BaseModel):
       id: int
       title: str
       content: str
       author: str | None
       source_name: str
   ```
   Это явный контракт между repository и LLM-слоем (принцип 3.2 — без ORM наружу).

5. `utils/retry.py` — декоратор `async_retry(attempts=3, base_delay=1.0, exceptions=(...))` с экспоненциальной паузой.

6. `llm/__init__.py` — пустой.

7. `llm/client.py`:
   - Класс `OpenAIClient`, инициализируется из `settings`.
   - Метод `async def complete_json(system: str, user: str, model: str, response_schema: type[BaseModel]) -> tuple[BaseModel, int]` — возвращает (валидированную модель, total_tokens).
   - `response_format={"type": "json_object"}`.
   - Ретраи через `utils/retry.py`: 3 попытки, 1s/2s/4s, на 429/500/timeout.
   - При невалидном JSON — одна повторная попытка с подсказкой "Return only valid JSON matching the schema".
   - Логирование: `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `latency_ms`. Если `OPENAI_PRICE_PER_1K_INPUT` и `OPENAI_PRICE_PER_1K_OUTPUT` заданы в settings — добавь поле `cost_usd`.

8. `llm/scorer.py`:
   - `async def score_post(post: PostForScoring) -> tuple[PostScore, int]` — принимает pydantic-DTO, не ORM.
   - Загружает `user_profile.md` и `score_post.md` (кэш в памяти модуля).
   - Подстановка через `string.Template.safe_substitute` (НЕ `str.format`).
   - Обрезает `post.content` до 4000 символов.
   - Модель — `settings.OPENAI_MODEL_SCORE`.

9. `pipeline/score.py`:
   - `async def run_score(limit: int = 50) -> dict` — возвращает `{processed, failed, total_tokens}`.
   - Берёт через repository посты без записи в `post_scores` (MVP: без учёта модели).
   - Параллелизация: `asyncio.gather` с `asyncio.Semaphore(5)`.
   - Ошибка на конкретном посте — лог `exception`, пропуск, не валим батч.

10. `db/repository.py` — добавь:
    - `async def get_unscored_posts(session, limit: int) -> list[PostForScoring]` — возвращает DTO, не ORM. Технический долг (для MVP): "без записи в `post_scores` любой моделью". Если позже понадобится перескор новой моделью — рефакторинг.
    - `async def save_score(session, post_id: int, score: PostScore, model: str, tokens: int) -> None`.

11. `main.py` — команда `score` с опциональным `--limit` (default 50).

12. `requirements.txt` — добавь `openai`, `tenacity` (если используешь для ретраев) или оставь самописный декоратор.

Ограничения:
- Не реализуй digest, бот, scheduler.
- Контракт `PostScore` — неизменен.
- Технические детали — по разделу 14.

В конце — **"Как проверить"**:
- `docker compose run --rm app python -m src.main score --limit 20`
- SQL: распределение по категориям + средний `relevance_score`:
  `SELECT category, count(*), round(avg(relevance_score)::numeric, 2) FROM post_scores GROUP BY category;`
- SQL: top-10 по релевантности с заголовками:
  `SELECT p.title, ps.category, ps.relevance_score, ps.summary FROM post_scores ps JOIN posts p ON p.id=ps.post_id ORDER BY ps.relevance_score DESC LIMIT 10;`
- Глазами: профильные посты — >6, мусор — <4.
````

---

## Промпт для Этапа 4: Сборка дайджеста

````
Прикреплён ARCHITECTURE.md. Этапы 1-3 реализованы: посты собраны и оценены.

Задача: реализуй **Этап 4 (Сборка дайджеста)**.

Бизнес-параметры (зафиксированы для MVP):
- Период дайджеста: 7 дней (default).
- Порог релевантности: `relevance_score >= 6`.
- "Высокововлечённые посты": `rating IS NOT NULL AND rating >= 50` OR `relevance_score >= 9`. Порог 50 — для Habr; для других источников будет переопределён позже.
- "Тренды недели": тема (любой элемент из `topics`) встречается ≥2 раз в выборке.

Требования:

1. `config/prompts/build_digest.md`:
   - Плейсхолдеры через `$variable`.
   - **System**: ты редактор еженедельного дайджеста, формируешь структурированный Markdown.
   - **User**: `$profile` + `$period_start` + `$period_end` + `$posts_json` (список постов с полями `title`, `url`, `summary`, `category`, `topics`, `relevance_score`, `source_name`, `rating`, `published_at`).
   - Формат вывода — Markdown строго по шаблону раздела 9 ARCHITECTURE.md:
     - Заголовок с диапазоном дат.
     - 🔥 **Тренды недели** — группировка по повторяющимся `topics` (≥2 раза).
     - 😣 **Боли и вопросы** (`category=pain`).
     - 💡 **Кейсы и MVP** (`category in [case, idea]`).
     - 📈 **Высокововлечённые посты** (критерий выше).
   - Пустые секции — опускать.
   - Тон: деловой, без воды, эмодзи только в заголовках секций.

2. `schemas/digest.py`:
   ```python
   class PostWithScore(BaseModel):
       post_id: int
       title: str
       url: str
       summary: str
       category: str
       topics: list[str]
       relevance_score: int
       rating: int | None
       source_name: str
       published_at: datetime

   class DigestInput(BaseModel):
       period_start: datetime
       period_end: datetime
       posts: list[PostWithScore]
       profile: str

   class DigestOutput(BaseModel):
       content_md: str
   ```
   Файл именно `digest.py` (если в разделе 5 видишь `digest.p` — опечатка).

3. `llm/client.py` — добавь метод:
   - `async def complete_text(system: str, user: str, model: str) -> tuple[str, int]` (текст + total_tokens) с теми же ретраями и логированием стоимости.

4. `llm/digest_builder.py`:
   - `async def build_digest(input_: DigestInput) -> DigestOutput`.
   - Модель — `settings.OPENAI_MODEL_DIGEST`.
   - Если `len(input_.posts) > 80` — нарезай по категориям, делай отдельный LLM-вызов на каждую секцию, конкатенируй итоговый Markdown.
   - Ответ LLM — plain markdown, не JSON.

5. `pipeline/digest.py`:
   - `async def run_digest(days: int = 7, min_relevance: int = 6, exclude_delivered: bool = True, is_manual: bool = False) -> int | None`.
   - Отбор: посты с `scored_at` (или `published_at`) в `[now - days, now]`, `relevance_score >= min_relevance`.
   - При `exclude_delivered=True` — исключить `post_id`, присутствующие в `delivery_log`.
   - Если выборка пуста — лог "nothing to digest", `return None`.
   - Загружает `user_profile.md`.
   - Вызывает `build_digest`, сохраняет в `digests` (`content_md`, `period_start`, `period_end`, `is_manual`) + `digest_posts`. Возвращает `digest_id`.

6. `db/repository.py` — добавь:
   - `async def get_posts_for_digest(session, period_start, period_end, min_relevance: int, exclude_delivered: bool) -> list[PostWithScore]`.
   - `async def save_digest(session, content_md: str, period_start, period_end, post_ids: list[int], is_manual: bool) -> int`.

7. `main.py` — команда `digest` с аргументами `--days` (default 7), `--min-relevance` (default 6), `--manual` (флаг).

Ограничения:
- Не реализуй бот и доставку. `content_md` только сохраняется в БД.
- Не реализуй scheduler.
- Технические детали — по разделу 14.

В конце — **"Как проверить"**:
- `docker compose run --rm app python -m src.main digest --days 7`
- `psql $DATABASE_URL -c "SELECT id, period_start, period_end, length(content_md), is_manual FROM digests ORDER BY id DESC;"`
- `psql $DATABASE_URL -c "SELECT count(*) FROM digest_posts WHERE digest_id=(SELECT max(id) FROM digests);"`
- Выгрузка для просмотра: `psql $DATABASE_URL -c "\copy (SELECT content_md FROM digests ORDER BY id DESC LIMIT 1) TO '/tmp/digest.md'"` и `cat /tmp/digest.md`.
- Структура соответствует шаблону раздела 9.
````

---

## Промпт для Этапа 5: Telegram-бот + доставка

````
Прикреплён ARCHITECTURE.md. Этапы 1-4 реализованы: дайджесты собираются и лежат в БД.

Задача: реализуй **Этап 5 (Telegram-бот + доставка)**.

Требования:

1. `bot/__init__.py` — пустой.

2. `bot/bot.py`:
   - Инициализация `aiogram.Bot` и `Dispatcher` с `TELEGRAM_BOT_TOKEN`.
   - Middleware авторизации: хендлеры срабатывают только при `message.from_user.id == settings.TELEGRAM_USER_ID`. Прочие — игнор без ответа.
   - `async def run_bot() -> None` — запускает polling.

3. `bot/handlers.py`:
   - `/help` — список команд.
   - `/digest` — `await message.answer("Собираю дайджест, подождите...")` → `run_digest(days=7, exclude_delivered=True, is_manual=True)` → если `digest_id is None`: "Нет новых постов за период"; иначе `deliver_digest(digest_id)`.
   - `/digest_today` — то же, но `days=1`.
   - `/status` — статистика: всего постов, оценено, дата последнего `collected_at`, дата последнего `sent_at` дайджеста, число отправленных дайджестов. Формат — компактный, по одной метрике на строку.
   - Любая ошибка в хендлере — `log.exception` + ответ "Произошла ошибка, проверь логи".

4. `pipeline/deliver.py`:
   - `async def deliver_digest(digest_id: int) -> None`.
   - Загружает `content_md` и список `post_ids` из `digest_posts`.
   - Разбивает `content_md` на части ≤4000 символов, режет по `\n\n`, не разрывая буллеты (если буллет длиннее лимита — режет по `\n`).
   - Отправляет через `bot.send_message`, `parse_mode="Markdown"`, `disable_web_page_preview=True`. При ошибке форматирования Markdown — повторная отправка без `parse_mode`.
   - **Атомарность**: только после успешной отправки ВСЕХ частей — `UPDATE digests SET sent_at=now() WHERE id=...` + bulk insert в `delivery_log` (по записи на каждый `post_id` с `digest_id` и `sent_at`). Если упало на середине — `sent_at` и `delivery_log` НЕ пишутся.

5. `db/repository.py` — добавь:
   - `async def get_digest(session, digest_id: int) -> tuple[str, list[int]]` (content_md + post_ids).
   - `async def mark_digest_delivered(session, digest_id: int, post_ids: list[int]) -> None`.
   - `async def get_status_stats(session) -> dict` — `{posts_total, posts_scored, last_collected_at, last_digest_sent_at, digests_sent_count}`.

6. `main.py`:
   - Команда `bot` — `asyncio.run(run_bot())`.
   - Команда `deliver --digest-id N` — ручная доставка существующего дайджеста.
   - Команда `run` пока остаётся заглушкой (полное содержание — в Этапе 6).

7. `requirements.txt` — добавь `aiogram>=3.0`.

8. `docker-compose.yml` — НЕ меняй команду запуска (она уже `python -m src.main run` с Этапа 1). На время Этапа 5 для ручной проверки используй `docker compose run --rm app python -m src.main bot`. Полная интеграция бота в `run` — в Этапе 6.

Ограничения:
- Не реализуй scheduler. Бот работает в polling, без автоматических джоб.
- Команды `/run_collect` и `/run_digest_now` появятся в Этапе 6.
- Технические детали (алгоритм разбиения сообщений, формат вывода `/status`) — по разделу 14.

В конце — **"Как проверить"**:
- `docker compose run --rm app python -m src.main bot` — бот стартует.
- В Telegram: `/help`, `/status`, `/digest_today`, `/digest`.
- Чужой аккаунт пишет боту — игнор (проверка middleware).
- `psql $DATABASE_URL -c "SELECT digest_id, count(*) FROM delivery_log GROUP BY digest_id;"`
- `psql $DATABASE_URL -c "SELECT id, sent_at FROM digests WHERE sent_at IS NOT NULL;"`
- Повторный `/digest` за тот же период — приходит "Нет новых постов" (фильтр `exclude_delivered` работает).
- Ручная доставка: `docker compose run --rm app python -m src.main deliver --digest-id 1`.
````

---

## Промпт для Этапа 6: Scheduler + автономный режим

````
Прикреплён ARCHITECTURE.md. Этапы 1-5 реализованы: всё работает по командам и через бота.

Задача: реализуй **Этап 6 (Scheduler + полный цикл в проде)**.

Требования:

1. `scheduler.py`:
   - `AsyncIOScheduler` (APScheduler).
   - Таймзона — из `settings.TZ`.
   - Джоба `daily_job` (cron из `COLLECT_CRON`): `run_collect()` → `run_score()`. Логирует итоговую статистику.
   - Джоба `weekly_job` (cron из `DIGEST_CRON`): `run_digest(days=7)` → если `digest_id` не `None`: `deliver_digest(digest_id)`; иначе лог "nothing to digest".
   - Обе джобы — в `try/except Exception`, ошибка логируется через `log.exception`, scheduler не падает.
   - Параметры триггеров: `misfire_grace_time=3600`, `coalesce=True`.
   - Функция `def build_scheduler() -> AsyncIOScheduler` — собирает и возвращает экземпляр с зарегистрированными джобами (не стартует).

2. `main.py`:
   - Команда `run` (default) — наполняется содержанием:
     - Инициализация логгера.
     - Параллельный запуск `run_bot()` и старт `scheduler` в одном event loop через `asyncio.gather`.
     - Graceful shutdown по `SIGTERM`/`SIGINT`: `scheduler.shutdown(wait=True)`, `await bot.session.close()`, отмена задач.
   - Команды `collect`, `score`, `digest`, `deliver`, `bot` — остаются для ручного запуска (без изменений).

3. `bot/handlers.py` — добавь dev-команды (только для `TELEGRAM_USER_ID`):
   - `/run_collect` — выполняет тело `daily_job` (collect → score), отвечает итоговой статистикой.
   - `/run_digest_now` — выполняет тело `weekly_job` (digest → deliver). Если постов нет — отвечает "Нет новых постов".
   - Эти хендлеры используют ТУ ЖЕ логику, что и джобы scheduler (вынеси тело джоб в отдельные `async def daily_pipeline()` / `async def weekly_pipeline()` в `scheduler.py` и вызывай их из обоих мест).

4. `docker-compose.yml`:
   - `command: python -m src.main run` (уже так с Этапа 1 — проверь, что не сбилось).
   - `restart: unless-stopped`.
   - Logging: драйвер `json-file`, `max-size=10m`, `max-file=3`.
   - Healthcheck (опционально): `pg_isready` в сторону БД либо простой `python -c "import sys; sys.exit(0)"`, интервал 60s.

5. `requirements.txt` — добавь `apscheduler>=3.10`.

6. `README.md` — добавь раздел "Production режим":
   - Команды развёртывания на сервере (clone, .env, init.sql, `docker compose up -d`).
   - Просмотр логов: `docker compose logs -f app`.
   - Ручной триггер через бота: `/run_collect`, `/run_digest_now`.
   - Откат: `docker compose down && git checkout <prev>`.

Ограничения:
- Не реализуй новые источники — это Этап 7+.
- Контракты разделов 4 и 6 — неизменны.
- Технические детали (точная реализация graceful shutdown, команда healthcheck) — по разделу 14.

В конце — **"Как проверить"**:
- `docker compose up -d`.
- `docker compose logs -f app` — видим "scheduler started" и список зарегистрированных джоб.
- В Telegram: `/run_collect` → отрабатывает, в БД появляются новые posts и post_scores.
- В Telegram: `/run_digest_now` → приходит дайджест.
- Перезапуск контейнера (`docker compose restart app`) — джобы переподхватываются по расписанию, `delivery_log` не дублируется.
- Временный тест cron: поставить `COLLECT_CRON="*/2 * * * *"`, перезапустить контейнер, наблюдать запуск каждые 2 минуты в логах. После проверки — вернуть исходное значение.

**MVP закрыт.**
````

---

## Промпт-шаблон для Этапов 7-10 (новые источники)

````
Прикреплён ARCHITECTURE.md. MVP (Этапы 1-6) полностью реализован, работает на Habr.

Задача: реализуй **Этап N — добавление источника {SOURCE_NAME}** (подставить: Reddit / VK / Telegram / YouTube).

Контекст: ядро трогать нельзя. Архитектура plugin-based (принцип 3.1): новый источник = новый файл в `sources/`, регистрация в `registry.py`, секция в `sources.yaml`. Контракт `RawPost` (раздел 6) — неизменен.

Требования:

1. `sources/{source_name}.py` — класс `{SourceName}Source(BaseSource)`:
   - Реализует `async def fetch(self, since: datetime) -> list[RawPost]`.
   - Маппинг полей источника → `RawPost`.
   - `external_id` — стабильный уникальный идентификатор в рамках источника (post_id, video_id, message_id).
   - `rating` — лайки / upvotes / просмотры (что применимо). Если недоступно — `None`.
   - `content` — основной текст поста. Если источник даёт только превью — извлекать полный текст отдельным запросом.
   - Rate limiting: sleep / exponential backoff / уважение `Retry-After`.
   - `published_at` — в UTC.
   - Ошибки сети/парсинга отдельных постов — лог `WARNING`, пост пропускается. Падение всего fetch — `log.exception`, пустой список (collect не валится).
   - Структурное логирование: source, fetched, parsed, skipped.

2. `sources/registry.py` — зарегистрируй новый тип в `SOURCE_TYPES`.

3. `config/sources.yaml` — добавь 2-3 релевантных канала/сабреддита/паблика, подобранных под `user_profile.md`. Подбор — твоя инициатива.

4. `requirements.txt` — нужные библиотеки:
   - Reddit: `asyncpraw`.
   - VK: `vk-api` (оборачивать в `asyncio.to_thread`).
   - Telegram: `telethon` (требует `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, persistent session в volume).
   - YouTube: `google-api-python-client` + `youtube-transcript-api`.

5. Новые env-переменные (API ключи источника):
   - Добавь в `.env.example`.
   - Добавь типизированные поля в `settings.py` (опциональные, чтобы запуск без них не падал, если источник отключён в YAML).

6. Если источнику нужна персистентная сессия (Telegram/Telethon) — опиши процедуру первичной авторизации в `README.md`, путь к сессии — через volume в `docker-compose.yml`.

7. Тест (минимум один): `tests/test_sources_{source_name}.py` — integration-тест с моком HTTP/API ответа, проверка маппинга в `RawPost` (`external_id`, `url`, `title`, `published_at` в UTC).

Ограничения:
- Ядро (`pipeline/`, `llm/`, `bot/`, `scheduler.py`, `schemas/`, `db/`) — НЕ трогать.
- Контракт `RawPost` — неизменен. Если источнику жизненно нужны дополнительные поля (например, `duration` или `transcript` для YouTube) — НЕ хардкодить:
  1. Сначала предложить правку в ARCHITECTURE.md (новые nullable-поля в разделе 6 и в таблице `posts` раздела 4).
  2. Указать миграционный SQL (`ALTER TABLE posts ADD COLUMN ...`).
  3. Только после явного подтверждения — менять код.
  Альтернатива: складывать спец-данные в `raw_json` (без изменения схемы).
- Технические детали (rate limit, формат `raw`, конкретные API endpoints) — по разделу 14.

В конце — **"Как проверить"**:
- Инструкция по получению ключей (где зарегистрировать app, какие scope/permissions).
- Команда `docker compose run --rm app python -m src.main collect`.
- SQL-проверка постов нового источника:
  `psql $DATABASE_URL -c "SELECT s.name, count(p.*) FROM sources s LEFT JOIN posts p ON p.source_id=s.id WHERE s.type='{source_name}' GROUP BY s.name;"`
- Проверка, что `score` source-agnostic: `docker compose run --rm app python -m src.main score`, посты получают оценки без модификации ядра.
- Прогон тестов: `pytest tests/test_sources_{source_name}.py`.
````

---