from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_DIGEST_WEEK = "📰 Дайджест за неделю"
BTN_DIGEST_TODAY = "☀️ Дайджест сегодня"
BTN_STATUS = "📊 Статус"
BTN_HELP = "❓ Помощь"

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_DIGEST_WEEK), KeyboardButton(text=BTN_DIGEST_TODAY)],
        [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_HELP)],
    ],
    resize_keyboard=True,
    is_persistent=True,
)