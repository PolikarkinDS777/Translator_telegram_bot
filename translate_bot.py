import asyncio
import requests
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

load_dotenv()  # загружает все переменные из .env в окружение


# --- WHITELIST USERS HERE ---
ALLOWED_USERS = set(map(int, os.getenv("ALLOWED_USERS", "").split(',')))

BOT_TOKEN = os.getenv("BOT_TOKEN")
DEEPL_API_KEY = os.getenv("DEEPL_API_KEY")
DEEPL_API_URL = os.getenv("DEEPL_API_URL")

language_pairs = {
    "en-ru": ("EN", "RU"),
    "ru-en": ("RU", "EN"),
    "en-ro": ("EN", "RO"),
    "ro-en": ("RO", "EN"),
}

user_lang_choice = {}

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

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
            InlineKeyboardButton(text="🇬🇧 EN → 🇷🇺 RU", callback_data="set_lang_en-ru"),
            InlineKeyboardButton(text="🇷🇺 RU → 🇬🇧 EN", callback_data="set_lang_ru-en"),
        ],
        [
            InlineKeyboardButton(text="🇬🇧 EN → 🇷🇴 RO", callback_data="set_lang_en-ro"),
            InlineKeyboardButton(text="🇷🇴 RO → 🇬🇧 EN", callback_data="set_lang_ro-en"),
        ]
    ]
)
    await message.answer("👋 Hey! Select the translation direction:", reply_markup=kb)

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
    data = {
        "auth_key": DEEPL_API_KEY,
        "text": text,
        "source_lang": src,
        "target_lang": tgt,
        "preserve_formatting": "1",
        "formality": "prefer_more"
    }
    resp = requests.post(DEEPL_API_URL, data=data)
    resp.raise_for_status()
    result = resp.json()
    return result["translations"][0]["text"]

@dp.message()
async def translate_handler(message: Message):
    user_id = message.from_user.id
    if not is_allowed(user_id):
        await message.answer("🚫 This bot is private. No access.")
        return
    pair_code = user_lang_choice.get(user_id, "en-ru")
    src, tgt = language_pairs.get(pair_code, ("EN", "RU"))

    user_text = message.text.strip()
    if not user_text:
        await message.answer("Send me the text for translation.")
        return

    try:
        translation = await asyncio.get_event_loop().run_in_executor(
            None, deepl_translate, user_text, src, tgt
        )
        await message.answer(f"<b>:</b>\n{translation}")
    except Exception as e:
        await message.answer(f"Error requesting DeepL: {e}")

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot))
