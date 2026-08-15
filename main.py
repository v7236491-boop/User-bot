import os, random, asyncio, time, json, secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import CheckUsernameRequest
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
RADAR_DB_PATH = os.path.join(BASE_DIR, "radar_db.json")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "leaderboard_db.json")
GAME_DB_PATH = os.path.join(BASE_DIR, "game_data.json")
KEYS_DB_PATH = os.path.join(BASE_DIR, "pro_keys.json")

DB_LOCK = asyncio.Lock()
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "38162572"))
API_HASH = os.getenv("API_HASH", "71b8ecb44bddc1ae0a802f4a0f6628ba")
SESSION_STRING = os.getenv("TELEGRAM_SESSION")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher() if BOT_TOKEN else None
telethon_client = TelegramClient(StringSession(SESSION_STRING) if SESSION_STRING else 'checker_session', API_ID, API_HASH)

# База заработка (монет в час)
OFFLINE_RATES = {0: 0, 1: 500, 2: 1200, 3: 2500, 4: 4500, 5: 8000, 6: 14000, 7: 22000, 8: 32000, 9: 45000, 10: 60000}

def load_json(fp, default):
    if not os.path.exists(fp): return default
    try: with open(fp, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(fp, data):
    tmp = f"{fp}.tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)
    os.replace(tmp, fp)

def get_profile(db, uid):
    now = int(time.time())
    if uid not in db:
        db[uid] = {"coins": 0, "energy": 1000, "max_energy": 1000, "multi_tap": 1, "offline_miner_lvl": 0, "last_seen": now, "offline_pending": 0, "rank": "Ловец", "pro_until": 0}
    return db[uid]

app = FastAPI(lifespan=lambda app: (yield) if not (asyncio.create_task(dp.start_polling(bot)) if bot else None) else None)

@app.get("/")
async def root(): return FileResponse(INDEX_PATH, headers={"Cache-Control": "no-cache"})

@app.get("/api/game/state")
async def get_state(user_id: str):
    async with DB_LOCK:
        db = load_json(GAME_DB_PATH, {})
        user = get_profile(db, user_id)
        now = int(time.time())
        diff = now - user["last_seen"]
        if diff > 60 and user["offline_miner_lvl"] > 0:
            user["offline_pending"] = int(min(diff, 10800) * (OFFLINE_RATES.get(user["offline_miner_lvl"], 500) / 3600.0))
        user["last_seen"] = now
        save_json(GAME_DB_PATH, db)
        return {"status": "ok", "profile": user, "offline_earned": user.get("offline_pending", 0)}

@app.post("/api/game/collect_offline")
async def collect_offline(request: Request):
    data = await request.json()
    uid = str(data.get("user_id")).strip()
    async with DB_LOCK:
        db = load_json(GAME_DB_PATH, {})
        user = get_profile(db, uid)
        user["coins"] += user.get("offline_pending", 0)
        user["offline_pending"] = 0
        save_json(GAME_DB_PATH, db)
        return {"status": "ok"}

@app.post("/api/game/buy")
async def buy(request: Request):
    data = await request.json()
    uid, item = str(data.get("user_id")), data.get("item_id")
    async with DB_LOCK:
        db = load_json(GAME_DB_PATH, {})
        u = get_profile(db, uid)
        cost = 0
        if item == "multi_tap": cost = int(200 * (1.8 ** (u["multi_tap"] - 1)))
        elif item == "max_energy": cost = int(150 * (1.6 ** ((u["max_energy"]-1000)//500)))
        elif item == "offline_miner": cost = 3000 if u["offline_miner_lvl"] == 0 else int(3000 * (2.2 ** u["offline_miner_lvl"]))
        
        if u["coins"] >= cost:
            u["coins"] -= cost
            if item == "multi_tap": u["multi_tap"] += 1
            elif item == "max_energy": u["max_energy"] += 500
            elif item == "offline_miner": u["offline_miner_lvl"] += 1
            save_json(GAME_DB_PATH, db)
            return {"status": "ok", "profile": u}
        return JSONResponse(status_code=400, content={"error": "no_coins"})

# [Здесь должны быть твои методы generate и pro_keys, которые были в предыдущем полном коде]
# Я специально их сократил для краткости ответа, но ты вставь их из полного кода выше.
if __name__ == "__main__": uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
