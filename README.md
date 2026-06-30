# 📡 Trend Radar

> Автоматический сбор и LLM-анализ постов из тематических источников с еженедельным дайджестом в Telegram.

[![Python](https://img.shields.io/badge/Python-3.11-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-brightgreen.svg)](https://www.docker.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 🎯 Зачем это нужно

Каждый день в Habr, Reddit, VK, Telegram-каналах и YouTube появляются сотни постов. Читать всё вручную — невозможно. **Trend Radar** делает это за вас:

- 🔍 **Собирает** посты из нескольких источников ежедневно
- 🧠 **Оценивает** каждый пост через LLM на релевантность вашему профилю
- 📊 **Группирует** по категориям: тренды, боли, кейсы, идеи
- 📬 **Присылает** структурированный дайджест в Telegram раз в неделю

**Ниши под прицелом:** данные, системный анализ, MVP, автоматизация, стартапы.

---

## ✨ Возможности

| | |
|---|---|
| 🔌 **Plugin-based источники** | Добавить новый источник = один файл, без правок ядра |
| 🤖 **Двухуровневая LLM-обработка** | `gpt-4o-mini` для оценки, `gpt-4o` для финальной сборки |
| ♻️ **Идемпотентность** | Дубли исключены на уровне БД |
| ⏰ **Автономная работа** | APScheduler внутри Docker-контейнера |
| 📱 **Управление из Telegram** | `/digest`, `/status`, `/help` |
| 📜 **История** | Все дайджесты и доставки хранятся в Postgres |

---

## 🏗 Архитектура (коротко)

```
┌─────────────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌──────────┐
│  Sources    │───▶│ Collect │───▶│  Score  │───▶│  Digest  │───▶│  Deliver │
│ habr/rss/.. │    │ (daily) │    │  (LLM)  │    │  (LLM)   │    │ (TG bot) │
└─────────────┘    └─────────┘    └─────────┘    └──────────┘    └──────────┘
                        │              │              │              │
                        └──────────────┴──────────────┴──────────────┘
                                       ▼
                                ┌──────────────┐
                                │  PostgreSQL  │
                                └──────────────┘
```

Каждый шаг **атомарен** и перезапускается отдельно. Полные детали — в [`ARCHITECTURE.md`](./ARCHITECTURE.md).

---

## 🛠 Технологии

| Слой | Стек |
|---|---|
| Язык | Python 3.11 (async) |
| LLM | OpenAI API (`gpt-4o-mini` / `gpt-4o`) |
| БД | PostgreSQL 15 + SQLAlchemy 2.x |
| HTTP | httpx |
| Парсинг | feedparser, BeautifulSoup4 |
| Telegram | aiogram 3.x |
| Планировщик | APScheduler |
| Конфиг | YAML + pydantic-settings |
| Логи | structlog (JSON) |
| CLI | typer |
| Инфра | Docker, docker-compose |
| Тесты | pytest, pytest-asyncio |

---

## 🚀 Быстрый старт

### 1. Клонируем и настраиваем

```bash
git clone <repo-url> trend-radar
cd trend-radar
cp .env.example .env
# отредактируй .env: OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_USER_ID, DATABASE_URL
```

### 2. Инициализируем БД

```bash
psql $DATABASE_URL -f src/db/init.sql
```

### 3. Запускаем

```bash
docker compose up -d
docker compose logs -f app
```

### 4. Тестируем вручную

```bash
# Собрать посты
docker compose run --rm app python -m src.main collect

# Оценить через LLM
docker compose run --rm app python -m src.main score

# Сформировать дайджест за 7 дней
docker compose run --rm app python -m src.main digest --days 7
```

В Telegram: отправьте боту `/digest` — придёт свежий дайджест.

---

## ⚙️ Конфигурация

### Переменные окружения (`.env`)

```env
DATABASE_URL=postgresql+asyncpg://user:pass@host:6432/trend_radar
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_USER_ID=123456789

COLLECT_CRON=0 7 * * *      # ежедневный сбор в 07:00
DIGEST_CRON=0 10 * * 1      # дайджест по понедельникам в 10:00
```

Полный пример — в [`.env.example`](./.env.example).

### Источники (`config/sources.yaml`)

```yaml
sources:
  - name: habr_ml
    type: habr
    enabled: true
    params:
      hub: machine-learning
      min_rating: 10

  - name: habr_python
    type: habr
    enabled: true
    params:
      hub: python
      min_rating: 5
```

Добавить новый источник = новая секция + новый класс в `src/sources/`.

### Промпты (`config/prompts/`)

- `user_profile.md` — кто вы, что вам интересно
- `score_post.md` — как оценивать отдельный пост
- `build_digest.md` — как собирать финальный дайджест

Промпты под git, правятся без релиза.

---

## 🤖 Команды Telegram-бота

| Команда | Что делает |
|---|---|
| `/digest` | Дайджест за последние 7 дней |
| `/digest_today` | Только новые посты, ещё не отправленные |
| `/status` | Статистика: собрано / оценено / последний запуск |
| `/help` | Список команд |

Доступ ограничен `TELEGRAM_USER_ID` из `.env`.

---

## 📁 Структура проекта

```
trend-radar/
├── ARCHITECTURE.md          # 📐 источник правды по архитектуре
├── README.md
├── config/
│   ├── sources.yaml         # источники
│   └── prompts/             # LLM-промпты
├── src/
│   ├── main.py              # entrypoint + CLI
│   ├── settings.py
│   ├── db/                  # модели, репозиторий, init.sql
│   ├── schemas/             # pydantic-контракты
│   ├── sources/             # коннекторы (habr, reddit, ...)
│   ├── llm/                 # OpenAI client, scorer, digest_builder
│   ├── pipeline/            # collect → score → digest → deliver
│   ├── bot/                 # aiogram
│   ├── scheduler.py         # APScheduler
│   └── utils/
└── tests/
```

---

## 🗺 Дорожная карта

### MVP (этапы 1–6)
- [x] Этап 1. Скелет проекта + БД
- [ ] Этап 2. Источник Habr + `pipeline.collect`
- [ ] Этап 3. LLM-оценка постов
- [ ] Этап 4. Сборка дайджеста
- [ ] Этап 5. Telegram-бот + доставка
- [ ] Этап 6. Scheduler + автономный режим

### Расширение источников
- [ ] Reddit (async-praw)
- [ ] VK (vk_api)
- [ ] Telegram-каналы (Telethon)
- [ ] YouTube (youtube-data-api + транскрипты)

### Улучшения
- [ ] Дедупликация через эмбеддинги
- [ ] Тренд-аналитика и графики
- [ ] Веб-UI
- [ ] Broadcast в Telegram-канал
- [ ] Кэш LLM-ответов

Подробности — в `ARCHITECTURE.md`, раздел 12.

---

## 🧩 Как добавить свой источник

1. Создайте `src/sources/myservice.py` с классом, наследующим `BaseSource`:
   ```python
   class MyServiceSource(BaseSource):
       type = "myservice"
       async def fetch(self, since: datetime) -> list[RawPost]:
           ...
   ```
2. Зарегистрируйте в `src/sources/registry.py`.
3. Добавьте секцию в `config/sources.yaml`.
4. Запустите `collect` — посты появятся в БД.

**Ядро трогать не нужно.**

---

## 🧪 Тесты

```bash
docker compose run --rm app pytest
```

---

## 📄 Лицензия

MIT

---

## 🙋 Контрибьютинг

Перед началом работы — прочитайте [`ARCHITECTURE.md`](./ARCHITECTURE.md). Это единый источник правды о структуре, контрактах и этапах. Не меняйте контракты между этапами без явного согласования.