#!/usr/bin/env python3
"""Raspberry Pi meter‑watcher (per‑device subscribers)

Снимает кадр с USB‑камеры, раз в `PERIOD` секунд отправляет его
пользователям, подписанным **именно на этот Raspberry Pi**.

* REST‑реестр хранит связи *device_id ↔ chat_id*.
* Pi спрашивает `/subscribers/{DEVICE_ID}` и шлёт только своим.
* Один объект `Bot` reused для всех отправок → меньше TLS‑handshake.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List

import cv2                 # OpenCV
import requests            # REST‑запросы к реестру
from telegram import Bot, InputFile

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# -------------------- ENV --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

DEVICE_ID = os.getenv("DEVICE_ID")  # уникальный ID этой Pi
if not DEVICE_ID:
    raise RuntimeError("DEVICE_ID is not set")

REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")

PERIOD  = int(os.getenv("PERIOD", "3600"))              # секунд
CAM_ID  = os.getenv("CAM_ID", "auto")                    # auto|0|/dev/video1
IMG_DIR = Path(os.getenv("IMG_DIR", "/tmp/meter_frames"))
IMG_DIR.mkdir(parents=True, exist_ok=True)

bot = Bot(BOT_TOKEN)  # создаём один экземпляр на всё время работы

# -------------- subscribers from registry ---------------

def _load_users() -> List[int]:
    try:
        url = f"{REGISTRY_URL}/subscribers/{DEVICE_ID}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.json()  # list[int]
    except Exception as exc:
        logger.error("Registry error: %s", exc)
        return []

# -------------- telegram send ----------------------------

# -------------- telegram send ----------------------------
async def _send_to_chat(chat_id: int, caption: str | None, photo_path: str | None):
    try:
        if photo_path:
            # Открываем файл внутри каждой отправки
            with open(photo_path, "rb") as f:
                await bot.send_photo(chat_id, photo=f, caption=caption)
        else:
            await bot.send_message(chat_id, text=caption or "(пустое сообщение)")
    except Exception as exc:
        logger.error("Telegram send error to %s: %s", chat_id, exc)



def notify_users(value: float | None = None, photo_path: str | None = None) -> None:
    """Рассылаем фото/значение только своим подписчикам."""
    chats = _load_users()
    if not chats:
        logger.warning("No subscribers for %s", DEVICE_ID)
        return

    caption = f"Текущие показания: {value}" if value is not None else None
    # photo: InputFile | None = None
    # if photo_path:
    #     photo = InputFile(photo_path, filename=Path(photo_path).name)

    async def _run():
        await asyncio.gather(*[
            _send_to_chat(cid, caption, photo_path) for cid in chats
        ])


    asyncio.run(_run())

# -------------- camera helpers ---------------------------

def _resolve_cam() -> int | str:
    if CAM_ID.lower() == "auto":
        return cv2.CAP_ANY  # OpenCV выберет первую доступную
    return int(CAM_ID) if CAM_ID.isdigit() else CAM_ID

CAM_SRC = _resolve_cam()
logger.info("Using camera source: %s", CAM_SRC)


def capture_frame() -> Path:
    cap = cv2.VideoCapture(2)
    if not cap.isOpened():
        raise RuntimeError(f"Camera {CAM_ID} not available")

    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError("Failed to grab frame")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    img_path = IMG_DIR / f"meter_{ts}.jpg"
    cv2.imwrite(str(img_path), frame)
    return img_path

# ---------------------- main loop ------------------------

def _register_device():
    try:
        requests.post(
            f"{REGISTRY_URL}/devices",
            json={"device_id": DEVICE_ID},
            timeout=5
        )
    except Exception as exc:
        logger.error("Device register error: %s", exc)


def main() -> None:
    logger.info("Watcher %s started, period=%s s", DEVICE_ID, PERIOD)
    _register_device()
    while True:
        try:
            img = capture_frame()
            logger.info("Captured %s", img)
            notify_users(photo_path=str(img))
            logger.info("Sent to subscribers: %s", _load_users())
        except Exception as exc:
            logger.exception("Loop error: %s", exc)
        time.sleep(PERIOD)


if __name__ == "__main__":
    main()
