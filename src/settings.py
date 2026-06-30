from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    DATABASE_URL: str

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL_SCORE: str = "gpt-4o-mini"
    OPENAI_MODEL_DIGEST: str = "gpt-4o"
    OPENAI_PRICE_PER_1K_INPUT: float | None = None
    OPENAI_PRICE_PER_1K_OUTPUT: float | None = None

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_USER_ID: int = 0

    # Runtime
    TZ: str = "UTC"
    LOG_LEVEL: str = "INFO"

    # Schedule
    COLLECT_CRON: str = "0 7 * * *"
    DIGEST_CRON: str = "0 10 * * 1"


settings = Settings()  # type: ignore[call-arg]