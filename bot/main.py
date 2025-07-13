# bot/main.py – Telegram‑бот, управляющий камерами
# -------------------------------------------------------------
# pip install python-telegram-bot aiohttp
#
#   export BOT_TOKEN="123:ABC…"
#   export REGISTRY_URL="http://localhost:8000"  # адрес FastAPI‑сервиса
# -------------------------------------------------------------
from __future__ import annotations

import os
from typing import Final

import aiohttp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

REGISTRY_URL: Final[str] = os.getenv("REGISTRY_URL", "http://localhost:8000")

# ---------------------- HTTP helper ----------------------------------
async def _post_json(url, params=None, json=None):
    async with aiohttp.ClientSession() as s:
        await s.post(url, params=params, json=json, timeout=5)


async def _del_json(url: str, params: dict):
    async with aiohttp.ClientSession() as s:
        await s.delete(url, params=params, timeout=5)


# ---------------------- универсальный reply --------------------------
async def _safe_reply(update: Update, text: str) -> None:
    """Отвечаем там, где можно: message → reply, иначе send_message."""
    if update.message:
        await update.message.reply_text(text)
    else:
        await update.effective_chat.send_message(text)


# -------------------------- handlers ---------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(
        update,
        "Привет! Я бот учёта показаний.\n"
        "• /register – включить чат в рассылку простых камер\n"
        "• /add_device <id> – привязать конкретную камеру\n"
        "• /remove_device <id> – отвязать камеру"
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = {
        "chat_id": update.effective_chat.id,
        "username": update.effective_user.username,
        "first_name": update.effective_user.first_name,
        "last_name": update.effective_user.last_name,
    }
    try:
        await _post_json(f"{REGISTRY_URL}/register", payload)
        await _safe_reply(update, "Регистрация прошла успешно! 📸")
    except Exception as exc:
        await _safe_reply(update, f"Ошибка регистрации: {exc}")


async def add_device(update, context):
    if not context.args:
        await _safe_reply(update, "Формат: /add_device <device_id>")
        return
    device_id = context.args[0]
    params = {"chat_id": update.effective_chat.id, "device_id": device_id}
    await _post_json(f"{REGISTRY_URL}/bind", params=params)   # ← !!! params
    await _safe_reply(update, f"📸 Камера {device_id} привязана!")



async def remove_device(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await _safe_reply(update, "Формат: /remove_device <device_id>")
        return
    device_id = context.args[0]
    params = {"chat_id": update.effective_chat.id, "device_id": device_id}
    try:
        await _del_json(f"{REGISTRY_URL}/bind", params)
        await _safe_reply(update, f"❌ Камера {device_id} отвязана.")
    except Exception as exc:
        await _safe_reply(update, f"Не удалось отвязать: {exc}")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _safe_reply(update, update.message.text if update.message else "")

# ----------------------------- main ----------------------------------

def main() -> None:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("add_device", add_device))
    app.add_handler(CommandHandler("remove_device", remove_device))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    app.run_polling()


if __name__ == "__main__":
    main()
