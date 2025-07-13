#!/usr/bin/env python3
"""Raspberry Pi meter‑watcher

Скрипт делает снимок с камеры через заданный интервал и отправляет
фото (и/или цифровое значение) всем пользователям, зарегистрированным
в Telegram‑боте simple_telegram_bot.py.

Ключевые фишки
==============
* **Автопоиск USB‑камеры**: если `CAM_ID=auto` (по умолчанию),
  скрипт сам найдёт первое устройство `/dev/video*`, которое открывается.
* Легковесная рассылка фото/значений в зарегистрированные чаты.

Зависимости:
  pip install opencv-python python-telegram-bot

Переменные окружения:
  BOT_TOKEN  – токен Вашего бота
  PERIOD     – период в секундах между кадрами (по умолчанию 3600)
  CAM_ID     – индекс/путь к камере (по умолчанию 0)
  IMG_DIR    – куда складывать кадры (по умолчанию /tmp/meter_frames)

Формат хранилища зарегистрированных чатов тот же, что и у бота –
JSON‑файл registered_users.json в рабочем каталоге.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List

import cv2  # OpenCV
from telegram import Bot

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -------------------- Конфигурация из ENV --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is not set")

PERIOD = int(os.getenv("PERIOD", "3600"))  # default: 1 час
CAM_ID = os.getenv("CAM_ID", "0")  # "0" -> /dev/video0
IMG_DIR = Path(os.getenv("IMG_DIR", "/tmp/meter_frames"))
IMG_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = Path("registered_users.json")

# -------------------------------------------------------------
# --- helpers for sending data back to Telegram ----------------

def _load_users() -> List[int]:
    if USERS_FILE.exists():
        try:
            return json.loads(USERS_FILE.read_text("utf-8"))
        except Exception as exc:
            logger.error("Failed to parse %s: %s", USERS_FILE, exc)
    return []


async def _push_to_chat(bot_token: str, chat_id: int, value: float | None, photo: str | None):
    bot = Bot(bot_token)
    async with bot:
        if photo:
            caption = f"Текущие показания: {value}" if value is not None else None
            await bot.send_photo(chat_id, photo=open(photo, "rb"), caption=caption)
        elif value is not None:
            await bot.send_message(chat_id, text=f"Текущие показания: {value}")


def notify_user(bot_token: str, value: float | None = None, photo_path: str | None = None) -> None:
    """Разослать `value` и/или `photo_path` всем зарегистрированным чатам."""
    chats = _load_users()
    if not chats:
        logger.warning("No registered users – nothing to send.")
        return

    async def _run():
        await asyncio.gather(*[_push_to_chat(bot_token, cid, value, photo_path) for cid in chats])

    asyncio.run(_run())

# -------------------------------------------------------------
# --------- работа с камерой и основной цикл ------------------

def capture_frame() -> Path:
    """Снять кадр с камеры и сохранить в IMG_DIR."""
    cam_index = int(CAM_ID) if CAM_ID.isdigit() else CAM_ID
    cap = cv2.VideoCapture(2)
    if not cap.isOpened():
        raise RuntimeError(f"Camera {CAM_ID} not available")

    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError("Failed to grab frame from camera")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    img_path = IMG_DIR / f"meter_{ts}.jpg"
    cv2.imwrite(str(img_path), frame)
    return img_path


def main() -> None:
    logger.info("Meter watcher started – every %s s", PERIOD)
    while True:
        try:
            img = capture_frame()
            logger.info("Captured %s", img)
            notify_user(BOT_TOKEN, photo_path=str(img))
            logger.info("Photo sent via Telegram")
        except Exception as exc:
            logger.exception("Error: %s", exc)
        time.sleep(PERIOD)


if __name__ == "__main__":
    main()
