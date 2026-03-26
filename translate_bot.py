import asyncio
import requests
import os
import json
from datetime import datetime
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()

ALLOWED_USERS = {
    int(uid) for uid in os.getenv("ALLOWED_USERS", "").split(",") if uid.strip()
}

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
DEEPL_API_URL = os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

USAGE_FILE = "usage.json"
CHAR_LIMIT = 500_000

language_pairs = {
    "en-ru": ("EN", "RU"),
    "ru-en": ("RU", "EN"),
    "en-ro": ("EN", "RO"),
    "ro-en": ("RO", "EN"),
}

user_lang_choice = {}

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set")

if not DEEPL_API_KEY:
    raise ValueError("DEEPL_API_KEY is not set")

if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL is not set")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


def _load_usage():
    month = datetime.utcnow().strftime("%Y-%m")
    data = {}

    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    used = data.get(month, 0)
    return {month: used}


def _save_usage(data: dict):
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)


def can_use_chars(text_length: int) -> bool:
    data = _load_usage()
    month = next(iter(data))
    used = data[month]
    return used + text_length <= CHAR_LIMIT


def commit_usage(text_length: int):
    data = _load_usage()
    month = next(iter(data))
    used = data[month]
    data[month] = used + text_length
    _save_usage(data)


def is_allowed(user_id):
    return user_id in ALLOWED_USERS


@dp.message(Command("start"))
async def start_handler(message: Message):
    if not is_allowed(message.from_user.id):
        await message.answer("🚫 This bot is private. No access.")
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇬🇧 EN → 🇷🇺 RU",
                    callback_data="set_lang_en-ru"
                ),
                InlineKeyboardButton(
                    text="🇷🇺 RU → 🇬🇧 EN",
                    callback_data="set_lang_ru-en"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🇬🇧 EN → 🇷🇴 RO",
                    callback_data="set_lang_en-ro"
                ),
                InlineKeyboardButton(
                    text="🇷🇴 RO → 🇬🇧 EN",
                    callback_data="set_lang_ro-en"
                ),
            ]
        ]
    )

    await message.answer(
        "👋 Hey! Select the translation direction:",
        reply_markup=kb
    )


@dp.callback_query(lambda c: c.data and c.data.startswith("set_lang_"))
async def set_lang_handler(callback: CallbackQuery):
    if not is_allowed(callback.from_user.id):
        await callback.message.answer("🚫 This bot is private. No access.")
        await callback.answer()
        return

    pair_code = callback.data.replace("set_lang_", "")

    if pair_code in language_pairs:
        user_lang_choice[callback.from_user.id] = pair_code
        src, tgt = language_pairs[pair_code]

        await callback.message.answer(
            f"Done! Now I will translate from <b>{src}</b> to <b>{tgt}</b>.\n\nSend me the text for translation."
        )
    else:
        await callback.message.answer("Language selection error.")

    await callback.answer()


def deepl_translate(text: str, src: str, tgt: str) -> str:
    headers = {
        "Authorization": f"DeepL-Auth-Key {DEEPL_API_KEY}"
    }

    data = {
        "text": text,
        "source_lang": src,
        "target_lang": tgt,
        "preserve_formatting": "1",
        "formality": "prefer_more"
    }

    resp = requests.post(
        DEEPL_API_URL,
        headers=headers,
        data=data,
        timeout=30
    )

    if not resp.ok:
        raise Exception(f"{resp.status_code} Client Error: {resp.text}")

    result = resp.json()

    if "translations" not in result or not result["translations"]:
        raise Exception(f"Unexpected DeepL response: {result}")

    return result["translations"][0]["text"]


@dp.message()
async def translate_handler(message: Message):
    user_id = message.from_user.id

    if not is_allowed(user_id):
        await message.answer("🚫 This bot is private. No access.")
        return

    pair_code = user_lang_choice.get(user_id, "en-ru")
    src, tgt = language_pairs.get(pair_code, ("EN", "RU"))

    if not message.text:
        await message.answer("Send me the text for translation.")
        return

    user_text = message.text.strip()

    if not user_text:
        await message.answer("Send me the text for translation.")
        return

    if not can_use_chars(len(user_text)):
        await message.answer(
            "⚠️ Limit exceeded. Please try again next month or contact the bot owner."
        )
        return

    try:
        translation = await asyncio.get_event_loop().run_in_executor(
            None,
            deepl_translate,
            user_text,
            src,
            tgt
        )

        commit_usage(len(user_text))

        await message.answer(f"</b>\n{translation}")

    except Exception as e:
        await message.answer(f"Error requesting DeepL: {e}")


# --- WEBHOOK STARTUP ---
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)


def main():
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path="/")
    app.on_startup.append(on_startup)
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()