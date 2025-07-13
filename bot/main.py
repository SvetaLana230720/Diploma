# Simple Telegram bot using python-telegram-bot v20+
# Prerequisites:
#   pip install python-telegram-bot asyncpg
#   export BOT_TOKEN="your-telegram-bot-token"
#   export DATABASE_URL="postgresql://user:pwd@host:5432/dbname"
# Then run: python simple_telegram_bot.py
from __future__ import annotations

import os
import asyncpg
import asyncio
from typing import Any, Dict

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import json
from pathlib import Path

# ---------------------- Postgres helpers ------------------------------
async def _init_db(app: Application) -> None:
    """Создать пул соединений и таблицу, если её ещё нет."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    pool = await asyncpg.create_pool(db_url)
    app.bot_data["db"] = pool  # хранится в контексте приложения

    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registered_users(
                chat_id       BIGINT PRIMARY KEY,
                username      TEXT,
                first_name    TEXT,
                last_name     TEXT,
                registered_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

async def _close_db(app: Application) -> None:
    pool: asyncpg.Pool | None = app.bot_data.get("db")  # type: ignore
    if pool:
        await pool.close()

# -------------------------- handlers ----------------------------------


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Привет! Я бот учёта показаний.\n"
        "Используй /register, чтобы получать фото и данные."
    )

USERS_FILE = Path("registered_users.json")   # общий файл с meter_watcher

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool: asyncpg.Pool = context.application.bot_data["db"]  # type: ignore
    chat_id = update.effective_chat.id

    async with pool.acquire() as conn:
        rec: Dict[str, Any] | None = await conn.fetchrow(
            "SELECT chat_id FROM registered_users WHERE chat_id=$1", chat_id
        )
        if rec:
            await update.message.reply_text("Вы уже зарегистрированы ✅")
        else:
            await conn.execute(
                """
                INSERT INTO registered_users(chat_id, username, first_name, last_name)
                VALUES($1, $2, $3, $4)
                """,
                chat_id,
                update.effective_user.username,
                update.effective_user.first_name,
                update.effective_user.last_name,
            )
            await update.message.reply_text("Регистрация прошла успешно! 📸")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Echo back every text message that isn’t a command."""
    await update.message.reply_text(update.message.text)


def main() -> None:
    """Run the bot."""
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("Environment variable BOT_TOKEN is not set")

    # Build the application and register handlers
    application = (
        Application.builder()
        .token(token)
        .post_init(_init_db)
        .post_shutdown(_close_db)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    # Echo every text message except commands
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Run the bot until Ctrl‑C
    application.run_polling()


if __name__ == "__main__":
    main()
