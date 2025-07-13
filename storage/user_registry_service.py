# storage/main.py – FastAPI + asyncpg
# -------------------------------------------------------------
# pip install fastapi uvicorn asyncpg
#
#   export DATABASE_URL="postgresql://meters:secret@localhost:5432/meters"
#   uvicorn storage.main:app --host 0.0.0.0 --port 8000
# -------------------------------------------------------------
from __future__ import annotations

import os
from typing import List, Optional

import asyncpg
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    raise RuntimeError("DATABASE_URL env var is required")

app = FastAPI(title="User-Device Registry")

# ------------------------- pydantic -------------------------- #
class UserIn(BaseModel):
    chat_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class DeviceIn(BaseModel):
    device_id: str
    nickname: Optional[str] = None          # «кухня», «подвал» и т.д.


# ------------------- DB init: create tables ------------------ #
DDL = """
CREATE TABLE IF NOT EXISTS registered_users(
    chat_id       BIGINT PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    last_name     TEXT,
    registered_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS devices(
    device_id     TEXT PRIMARY KEY,
    nickname      TEXT,
    registered_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_devices(
    chat_id   BIGINT REFERENCES registered_users(chat_id) ON DELETE CASCADE,
    device_id TEXT   REFERENCES devices(device_id)        ON DELETE CASCADE,
    PRIMARY KEY (chat_id, device_id)
);
"""

@app.on_event("startup")
async def startup() -> None:
    pool = await asyncpg.create_pool(DB_URL)
    async with pool.acquire() as conn:
        await conn.execute(DDL)
    app.state.pool = pool

@app.on_event("shutdown")
async def shutdown() -> None:
    await app.state.pool.close()

# ----------------------- user routes ------------------------- #
@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserIn):
    pool: asyncpg.Pool = app.state.pool
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO registered_users(chat_id, username, first_name, last_name)
            VALUES($1,$2,$3,$4)
            ON CONFLICT (chat_id)
            DO UPDATE SET username=$2, first_name=$3, last_name=$4
            """,
            user.chat_id, user.username, user.first_name, user.last_name
        )
    return {"status": "ok"}

# ----------------------- device routes ----------------------- #
@app.post("/devices", status_code=status.HTTP_201_CREATED)
async def register_device(dev: DeviceIn):
    pool: asyncpg.Pool = app.state.pool
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO devices(device_id, nickname)
            VALUES($1,$2)
            ON CONFLICT (device_id)
            DO UPDATE SET nickname = COALESCE($2, devices.nickname)
            """,
            dev.device_id, dev.nickname
        )
    return {"status": "ok"}

# --------------- bind / unbind (user ↔ device) --------------- #
@app.post("/bind", status_code=status.HTTP_201_CREATED)
async def bind(chat_id: int, device_id: str):
    pool: asyncpg.Pool = app.state.pool
    

    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO devices(device_id) VALUES($1) ON CONFLICT DO NOTHING",
            device_id,
        )
        await c.execute(
            "INSERT INTO user_devices(chat_id, device_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
            chat_id, device_id,
        )
    return {"status": "ok"}

@app.delete("/bind", status_code=status.HTTP_200_OK)
async def unbind(chat_id: int, device_id: str):
    pool: asyncpg.Pool = app.state.pool
    async with pool.acquire() as c:
        await c.execute(
            "DELETE FROM user_devices WHERE chat_id=$1 AND device_id=$2",
            chat_id, device_id,
        )
    return {"status": "ok"}

# ------------------- subscribers per device ------------------ #
@app.get("/subscribers/{device_id}", response_model=List[int])
async def subscribers_for_device(device_id: str):
    pool: asyncpg.Pool = app.state.pool
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT chat_id FROM user_devices WHERE device_id=$1",
            device_id,
        )
    return [r[0] for r in rows]

# ------------------- simple healthcheck ---------------------- #
@app.get("/health")
async def health():
    return {"status": "up"}
