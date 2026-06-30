````markdown
# ARCHITECTURE.md

## 0. Назначение документа

Этот файл — единый источник правды о проекте. Прикрепляется в начало любой сессии разработки с промптом вида:
> "Используя архитектурный контекст, реализуй **Этап N**. Следуй контрактам, не меняй структуру модулей без явного запроса."

---

## 1. Цель проекта

Сервис автоматически собирает посты из источников (стартуем с Habr, далее Reddit/VK/Telegram/YouTube), ежедневно оценивает их LLM-ом на релевантность профилю пользователя, а раз в неделю отправляет структурированный дайджест в Telegram. Цель — экономия времени на мониторинг трендов и болей в нишах "данные, системный анализ, MVP, автоматизация".

---

## 2. Технологический стек

| Слой | Технология |
|---|---|
| Язык | Python 3.11 |
| LLM | OpenAI API (gpt-4o-mini для оценки, gpt-4o для финального дайджеста) |
| БД | PostgreSQL (в Docker на сервере, подключение по URL) |
| ORM | SQLAlchemy 2.x |
| Схема БД | SQL-скрипт init.sql (выполняется один раз вручную) |
| HTTP | httpx (async) |
| Парсинг | feedparser (RSS), BeautifulSoup4 (HTML по необходимости) |
| Telegram | aiogram 3.x |
| Планировщик | APScheduler (внутри контейнера) |
| Конфиг | YAML (sources) + .env (секреты) + pydantic-settings |
| Логи | structlog (JSON) |
| Зависимости | pip + requirements.txt |
| Контейнеризация | Docker + docker-compose |
| Тесты | pytest + pytest-asyncio |

CLI: typer

---

## 3. Принципы архитектуры

1. **Plugin-based источники.** Каждый источник = отдельный класс, реализующий интерфейс `BaseSource`. Добавление нового источника = новый файл, без изменений в ядре.
2. **Слой контрактов.** Все межмодульные обмены — через pydantic-модели (`schemas/`).
3. **Идемпотентность.** Повторный запуск не создаёт дубли (уникальность по `source + external_id`).
4. **Все шаги — атомарны и отдельно перезапускаемы:** collect → score → digest → deliver.
5. **LLM-вызовы изолированы** в одном модуле с ретраями и логом стоимости.
6. **Никаких изменений контрактов между этапами без обновления этого файла.**

---

## 4. Доменные сущности (схема БД)

```
sources              -- справочник источников (habr, reddit, ...)
  id, name, type, config_json, is_active

posts                -- сырые посты
  id, source_id, external_id, url, title, author,
  content, published_at, rating, raw_json, collected_at
  UNIQUE(source_id, external_id)

post_scores          -- оценка LLM
  id, post_id, relevance_score (0-10),
  category (trend|pain|case|idea|other),
  summary (короткое саммари 1-2 предложения),
  topics (jsonb массив тем),
  scored_at, model, tokens_used

digests              -- сформированные дайджесты
  id, period_start, period_end, content_md,
  created_at, sent_at, is_manual

digest_posts         -- какие посты вошли в дайджест
  digest_id, post_id

delivery_log         -- что уже отправлено пользователю
  id, post_id, sent_at, digest_id
```

Схема создаётся один раз через `db/init.sql` (DDL всех таблиц). При изменении моделей — правим SQL вручную и применяем psql (это осознанное решение для одиночной разработки MVP).

---

## 5. Структура проекта

```
trend-radar/
├── ARCHITECTURE.md              # этот файл
├── README.md
├── requirements.txt
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── config/
│   ├── sources.yaml             # описание источников
│   └── prompts/
│       ├── user_profile.md      # профиль интересов
│       ├── score_post.md        # промпт для оценки поста
│       └── build_digest.md      # промпт для сборки дайджеста
├── src/
│   ├── __init__.py
│   ├── main.py                  # entrypoint, инициализация scheduler
│   ├── settings.py              # pydantic-settings
│   ├── db/
│   │   ├── engine.py
│   │   ├── models.py
│   │   ├── repository.py
│   │   └── init.sql             # DDL: CREATE TABLE ...
│   ├── schemas/                 # pydantic-контракты
│   │   └── __init__.py          # bot/scheduler появляются позже
│   │   ├── post.py
│   │   ├── score.py
│   │   └── digest.py
│   ├── sources/
│   │   ├── base.py              # BaseSource (ABC)
│   │   ├── registry.py          # реестр доступных источников
│   │   └── habr.py
│   │   # позже: reddit.py, vk.py, telegram.py, youtube.py
│   ├── llm/
│   │   ├── client.py            # OpenAI клиент + ретраи
│   │   ├── scorer.py            # оценка поста
│   │   └── digest_builder.py    # сборка дайджеста
│   ├── pipeline/
│   │   ├── collect.py           # шаг сбора
│   │   ├── score.py             # шаг оценки
│   │   ├── digest.py            # шаг формирования
│   │   └── deliver.py           # шаг отправки
│   ├── bot/
│   │   ├── bot.py               # aiogram setup
│   │   └── handlers.py          # /digest, /status, /help
│   ├── scheduler.py             # APScheduler jobs
│   └── utils/
│       ├── logging.py
│       └── retry.py
└── tests/
    ├── test_sources_habr.py
    ├── test_scorer.py
    └── ...
```

---

## 6. Ключевые контракты (pydantic)

### `schemas/post.py`
```python
class RawPost(BaseModel):
    source_name: str
    external_id: str
    url: HttpUrl
    title: str
    author: str | None = None
    content: str = ""
    published_at: datetime          # всегда UTC
    rating: int | None = None
    raw: dict = {}
```

### `schemas/score.py`
```python
class PostScore(BaseModel):
    relevance_score: int        # 0-10
    category: Literal["trend", "pain", "case", "idea", "other"]
    summary: str                # 1-2 предложения
    topics: list[str]           # ["data engineering", "MVP"]
```

### `sources/base.py`
```python
class BaseSource(ABC):
    name: str
    type: str

    @abstractmethod
    async def fetch(self, since: datetime) -> list[RawPost]:
        ...
```

**Контракты не меняем между этапами.** Если на этапе обнаруживается необходимость — обновляем `ARCHITECTURE.md` отдельным шагом.

---

## 7. Формат `config/sources.yaml`

```yaml
sources:
  - name: habr_ml
    type: habr
    enabled: true
    params:
      hub: machine-learning      # slug хаба Habr
      min_rating: 10             # минимальный рейтинг статьи (если доступен)
    # режим сбора — только RSS в MVP

  - name: habr_python
    type: habr
    enabled: true
    params:
      hub: python
      min_rating: 5
```

Поля:
- `name` — уникальный идентификатор источника (используется как `sources.name` в БД).
- `type` — тип источника (`habr`, в будущем `telegram`, `rss_generic` и т.д.).
- `enabled` — если `false`, источник пропускается при `collect`.
- `params` — произвольный dict, специфичный для типа источника. Валидируется внутри коннектора.

Файл читается при каждом запуске `collect`. Несуществующие в БД источники добавляются автоматически (upsert по `name`).

---

## 8. Конфигурация окружения (`.env.example`)

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:6432/trend_radar

OPENAI_API_KEY=sk-...
OPENAI_MODEL_SCORE=gpt-4o-mini
OPENAI_MODEL_DIGEST=gpt-4o

TELEGRAM_BOT_TOKEN=...
TELEGRAM_USER_ID=123456789

TZ=Europe/Moscow

LOG_LEVEL=INFO
COLLECT_CRON=0 7 * * *          # ежедневно в 07:00
DIGEST_CRON=0 10 * * 1          # понедельник в 10:00

OPENAI_PRICE_PER_1K_INPUT=0.00015     # опционально, для лога стоимости
OPENAI_PRICE_PER_1K_OUTPUT=0.0006     # опционально
```

---

## 9. Pipeline (логика работы)

### Ежедневно (COLLECT_CRON):
1. `pipeline.collect` — читает `sources.yaml`, для каждого active source вызывает `fetch(since=last_run)`, складывает `RawPost` в `posts` (idempotent через UNIQUE).
2. `pipeline.score` — берёт все `posts` без записи в `post_scores`, прогоняет через `llm.scorer`, пишет `PostScore`. Промпт включает `user_profile.md`.

### Еженедельно (DIGEST_CRON) и по команде `/digest`:
3. `pipeline.digest` — берёт посты за период (по умолчанию 7 дней) с `relevance_score >= 6`, **исключая те, что уже есть в `delivery_log`**. Группирует по категориям. `llm.digest_builder` собирает итоговый Markdown.
4. `pipeline.deliver` — отправляет Markdown в Telegram (с разбиением на сообщения, если >4096 символов). Пишет в `delivery_log`.

### Структура дайджеста (выход `digest_builder`):
```
🗓 Дайджест за 12–18 ноября

🔥 Тренды недели
— Тема X (упоминалась в 5 постах)
   • Заголовок [ссылка] — краткое саммари

😣 Боли и вопросы
— ...

💡 Кейсы и MVP
— ...

📈 Высокововлечённые посты
— ...
```

---

## 10. LLM-промпты (расположение)

- `config/prompts/user_profile.md` — статичный профиль пользователя (системный аналитик / данные / MVP / автоматизация / SMB / стартапы).
- `config/prompts/score_post.md` — промпт оценки одного поста. Вход: profile + post. Выход: JSON по схеме `PostScore`.
- `config/prompts/build_digest.md` — промпт сборки дайджеста. Вход: profile + список оценённых постов. Выход: Markdown.

Все промпты — версионируются в git, легко правятся без релиза.

---

## 11. Telegram-бот

Команды:
- `/digest` — собрать и прислать дайджест за последние 7 дней (по запросу).
- `/digest_today` — то же за сегодня (только новые посты, ещё не отправленные).
- `/status` — статистика: сколько постов собрано, оценено, последний запуск.
- `/help` — список команд.

Доступ: только `TELEGRAM_USER_ID` из .env. Возможность работы в канале — добавляем во 2-й фазе (отправка в `chat_id` канала вместо личного).

---

## 12. Этапы разработки

> Каждый этап = отдельная ветка `stage/N-name`, после ручного теста — merge в `main`. Перед каждым этапом — прикрепить `ARCHITECTURE.md` и указать "Реализуй Этап N".

---

### Этап 1. Скелет проекта + БД

**Цель:** есть репо, докер поднимается, БД готова.

**Делаем:**
- Структура папок по разделу 5.
- `requirements.txt`, `Dockerfile`, `docker-compose.yml` (app + ссылка на внешний Postgres).
- `settings.py` (pydantic-settings, читает .env).
- `db/models.py` — все таблицы из раздела 4 (SQLAlchemy 2.x, `Mapped[...]`).
- `db/init.sql` — DDL всех таблиц + UNIQUE-констрейнты + индексы.
- ВАЖНО: поле `posts.rating INTEGER NULL` должно присутствовать в `models.py` и `init.sql`.
- `utils/logging.py` (structlog в JSON).
- `main.py` — заглушка, выводит "service started".

DATABASE_URL использует драйвер postgresql+asyncpg://... для приложения. Для psql нужен чистый postgresql://... — задавать отдельной переменной PSQL_URL или вручную.

**Проверка:**
```bash
cp .env.example .env
docker compose build
psql $DATABASE_URL -f src/db/init.sql
docker compose up app
psql $DATABASE_URL -c "\dt"
```

---

### Этап 2. Источник Habr + Pipeline.collect

**Цель:** запускаем команду — в БД появляются посты с Habr.

**Делаем:**
- `config/sources.yaml` — начальный конфиг с 2-3 хабами Habr.
- `schemas/post.py` — pydantic-модель `RawPost` (см. раздел 6).
- `sources/base.py` — абстрактный `BaseSource` с методом `async fetch(since: datetime) -> list[RawPost]`.
- `sources/habr.py` — реализация для Habr через RSS (`feedparser` + `httpx` для скачивания фида).
- `sources/registry.py` — фабрика: по `type` из YAML возвращает экземпляр коннектора.
- `pipeline/collect.py` — оркестратор: читает YAML, для каждого enabled-источника зовёт `fetch`, передаёт результат в репозиторий.
- `db/repository.py` — методы `upsert_source(name, type, config)`, `upsert_posts(source_id, posts: list[RawPost])`, `get_last_collected_at(source_id) -> datetime | None`.
- `main.py` — CLI-команда `collect` (запуск пайплайна сбора).

**Правила:**
- Дедуп по `UNIQUE(source_id, external_id)` — конфликт → `ON CONFLICT DO NOTHING`.
- `since = max(last_collected_at, now - 7d)`; на холодном старте — `now - 7d`.
- Если у источника нет рейтинга — `rating = None`, фильтр `min_rating` пропускается.
- Все ошибки сети/парсинга по конкретному источнику — лог `ERROR` и продолжение со следующим источником (не падаем целиком).
- Все `datetime` приводим к UTC перед сохранением.

**Проверка:**
```bash
docker compose run --rm app python -m src.main collect
psql $DATABASE_URL -c "SELECT source_id, count(*) FROM posts GROUP BY source_id;"
```
Ожидаем >0 постов по каждому активному хабу.

---

### Этап 3. LLM-оценка постов (pipeline.score)

**Цель:** каждый собранный пост получает оценку и саммари.

**Делаем:**
- `config/prompts/user_profile.md` (профиль из брифа).
- `config/prompts/score_post.md` (JSON-output по схеме `PostScore`).
- `llm/client.py` — OpenAI wrapper с ретраями (3 попытки, экспоненциальная пауза), логом токенов.
- `llm/scorer.py` — оценка одного поста, валидация ответа через pydantic.
- `pipeline/score.py` — берёт необработанные посты, прогоняет, сохраняет в `post_scores`. Параллелизация 5 запросов.
- CLI: `python -m src.main score`.

**Проверка:**
```bash
docker compose run --rm app python -m src.main score
psql $DATABASE_URL -c "SELECT category, count(*), avg(relevance_score) FROM post_scores GROUP BY category;"
```
Проверяем, что у релевантных постов оценка >6, у мусора <4.

---

### Этап 4. Сборка дайджеста (pipeline.digest)

**Цель:** генерируется Markdown-дайджест и сохраняется в БД.

**Делаем:**
- `config/prompts/build_digest.md`.
- `llm/digest_builder.py` — на вход `list[PostScore + Post]`, на выход Markdown по шаблону из раздела 9.
- `pipeline/digest.py` — отбор постов за период, исключение уже отправленных, вызов builder, сохранение в `digests` + `digest_posts`.
- CLI: `python -m src.main digest --days 7`.

**Проверка:**
```bash
docker compose run --rm app python -m src.main digest --days 7
psql $DATABASE_URL -c "SELECT id, period_start, period_end, length(content_md) FROM digests;"
```
Открываем `content_md` глазами — проверяем структуру.

---

### Этап 5. Telegram-бот + доставка

**Цель:** дайджест приходит в Telegram, есть команды.

**Делаем:**
- `bot/bot.py`, `bot/handlers.py` (aiogram 3, polling).
- `pipeline/deliver.py` — отправка с разбиением >4096 символов, запись в `delivery_log`.
- Хендлеры: `/digest`, `/digest_today`, `/status`, `/help`.
- Авторизация по `TELEGRAM_USER_ID`.

**Проверка:**
```bash
docker compose up app
# В Telegram: /digest — получаем последний или новый дайджест.
# /status — видим цифры.
```

---

### Этап 6. Scheduler + полный цикл в проде

**Цель:** сервис работает автономно.

**Делаем:**
- `scheduler.py` — APScheduler с двумя джобами (`COLLECT_CRON`, `DIGEST_CRON`), каждая = collect → score (для daily) / digest → deliver (для weekly).
- Ретрай-логика на уровне docker compose (`restart: unless-stopped`) + try/except внутри jobs.
- `main.py` запускает одновременно бота и scheduler в одном event loop.
- Healthcheck-эндпоинт (опционально, простой HTTP `/health`).

**Проверка:**
```bash
docker compose up -d
docker compose logs -f app
# Триггерим джобу руками через хендлер /run_collect (dev-only) или ждём cron.
```

**На этом MVP закрыт.** Дальше — расширение.

---

### Этап 7+. Расширение источников (по одному источнику = один этап)

- 7: Reddit (через PRAW / async-praw, конфиг сабреддитов).
- 8: VK (vk_api, паблики).
- 9: Telegram-каналы (Telethon, сессия в volume).
- 10: YouTube (youtube-data-api, каналы + транскрипты через youtube-transcript-api).

Каждый этап = только новый файл в `sources/`, регистрация в `registry.py`, секция в `sources.yaml`. Ядро не трогаем.

---

### Этап 11+. Улучшения (по желанию)

- Дедупликация похожих постов между источниками (эмбеддинги + cosine).
- Тренд-аналитика: подсчёт частоты тем, графики динамики.
- Веб-UI для просмотра истории и тюнинга профиля.
- Поддержка работы в Telegram-канале (broadcast).
- Кэш LLM-ответов.

---

## 13. Правила работы Claude в чате

При запросе на реализацию этапа:
1. **Не выдумывать структуру** — следовать разделу 5.
2. **Не менять контракты** из раздела 6 без явного запроса.
3. При изменении `models.py` — обязательно синхронизировать `db/init.sql` (добавить ALTER/CREATE) и указать в ответе, какой SQL нужно выполнить вручную.
4. **Каждый ответ заканчивать блоком "Как проверить"** — конкретные команды.
5. **Если нужны изменения архитектуры** — сначала предложить правки в `ARCHITECTURE.md`, потом код.
6. Код — типизированный (mypy-friendly), async где имеет смысл (HTTP, БД, LLM).

---

## 14. Свобода реализации

Claude (или другой исполнитель) **НЕ должен** спрашивать разрешения на технические детали реализации. Принимает решение сам, фиксирует выбор в коде или коротким комментарием. К таким деталям относятся:

- Парсинг HTML: библиотека (BeautifulSoup / selectolax), селекторы, очистка тегов.
- HTTP-клиент: таймауты, User-Agent, ретраи, лимиты параллелизма.
- Формирование `external_id` — любое стабильное значение, уникальное в рамках источника.
- Состав служебных полей внутри `raw_json` / `raw`.
- Sync vs async внутри модуля, если контракт раздела 6 не диктует обратное.
- Обработка таймзон — всё приводим к UTC.
- Graceful degradation: если опциональные данные не извлекаются — `None` + лог `WARNING`, пайплайн не падает.
- Внутренние вспомогательные функции, приватные классы, структура модуля.

**Спрашивать обязательно** только в случаях:
1. Нестыковка между разделами `ARCHITECTURE.md`.
2. Пробел или противоречие в контрактах раздела 6.
3. Бизнес-решение: что считать релевантным, какие пороги фильтров, какие источники приоритетны.
4. Изменение схемы БД (раздел 4) или добавление/удаление полей в контрактах.
5. Добавление новой внешней зависимости, не упомянутой в `requirements.txt` соответствующего этапа.

Во всех остальных случаях — делаем и идём дальше. Если выбор неочевиден — короткий комментарий в коде с обоснованием (1 строка).

---

**Конец документа.**
````