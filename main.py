import os
import random
import asyncio
import time
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import CheckUsernameRequest
from telethon.errors import RPCError
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
RADAR_DB_PATH = os.path.join(BASE_DIR, "radar_db.json")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "leaderboard_db.json")

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "38162572"))
API_HASH = os.getenv("API_HASH", "71b8ecb44bddc1ae0a802f4a0f6628ba")
SESSION_STRING = os.getenv("TELEGRAM_SESSION")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher() if BOT_TOKEN else None

if SESSION_STRING:
    telethon_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    telethon_client = TelegramClient('checker_session', API_ID, API_HASH)

USER_COOLDOWNS = {}
COOLDOWN_SECONDS = 0.3

# =========================================================================
# 💎 ЛИНГВИСТИЧЕСКАЯ МАТРИЦА БРЕНД-НЕЙМИНГА (ОРФОЭПИЯ И СОНОРНОСТЬ)
# =========================================================================
TOP_BRANDS = list(set([
    "mcdonalds", "subway", "ronaldo", "messi", "nike", "adidas", "apple", "google",
    "tesla", "bitcoin", "crypto", "pavel", "durov", "telegram", "starbucks", "prada",
    "gucci", "porsche", "bmw", "mercedes", "ferrari", "redbull", "steam", "roblox"
]))

PURE_WORDS = list(set((
    "velvet aurora zenith vortex nebula horizon starlight crystal phoenix freedom "
    "infinity eternity paradise solitude serenity genesis paragon solstice obsidian "
    "valkyrie hyperion titanium cobalt specter vanguard solis aether kismet "
    "solace chronos tempest sapphire emerald olympus trident"
).split()))

# 1. Сонорные префиксы (легко выговариваются, звучат дорого и приятно)
BRAND_ROOTS = [
    "aeth", "aero", "ast", "chrom", "cyb", "hyp", "kism", "lum", "lun", 
    "mir", "nex", "orion", "phos", "prism", "sol", "spec", "stell", "temp", 
    "tit", "velv", "verv", "vort", "zeph", "zen", "valen", "zoran", "celest"
]

# 2. Окончания премиум-класса
BRAND_SUFFIXES = [
    "is", "ex", "or", "um", "on", "us", "ia", "ix", "ar", "al", "io", "ora", "eth"
]

CONSONANTS_SOFT = "bdfklmnprstvz"
VOWELS_SOFT = "aeiouy"

def generate_brand_username(len_mode: str = "5-6") -> str:
    """Генерирует звучный, легко запоминающийся ник по правилам орфоэпии."""
    roll = random.random()
    
    # 85% — Сочные бренд-неологизмы (префикс + премиум суффикс)
    if roll < 0.85 or len_mode == "5-6":
        root = random.choice(BRAND_ROOTS)
        suf = random.choice(BRAND_SUFFIXES)
        candidate = root + suf
        
        # Корректируем двойные буквы для идеального произношения
        candidate = candidate.replace("nn", "n").replace("ss", "s").replace("rr", "r").replace("oo", "o")
        
        if len_mode == "5-6" and len(candidate) > 6:
            candidate = candidate[:6]
        return candidate

    # 15% — Словарный эксклюзив
    else:
        return random.choice(PURE_WORDS)

# --- ХРАНИЛИЩЕ ЛИДЕРБОРДА ---
def load_leaderboard():
    if os.path.exists(LEADERBOARD_PATH):
        try:
            with open(LEADERBOARD_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_leaderboard(data):
    try:
        data = sorted(data, key=lambda x: x.get("score", 0), reverse=True)[:1000]
        with open(LEADERBOARD_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def add_to_leaderboard(username, rank, price, score, color, finder_name, finder_id):
    lb = load_leaderboard()
    if any(item["username"].lower() == username.lower() for item in lb):
        return
    
    lb.append({
        "username": username,
        "rank": rank,
        "price": price,
        "score": score,
        "color": color,
        "finder_name": finder_name or "Аноним",
        "finder_id": finder_id or "0",
        "timestamp": int(time.time())
    })
    save_leaderboard(lb)

# =========================================================================
# 🇷🇺 ЭКСПЕРТНАЯ ОЦЕНКА РАНГОВ И СТОИМОСТИ НА РУССКОМ
# =========================================================================
def calculate_catch_score(username: str, is_free: bool):
    if not is_free:
        return {"rank": "F", "status": "Занят пользователем или каналом", "color": "#ef4444", "score": 0}
    
    username = username.lower().replace("@", "").strip()
    length = len(username)
    
    if length < 5:
        return {"rank": "F", "status": "Короче 5 символов (Только Fragment)", "color": "#ef4444", "score": 0}

    if any(char.isdigit() or char == "_" for char in username):
        return {"rank": "F", "status": "Содержит цифры или символы", "color": "#ef4444", "score": 0}

    vowels = set("aeiouy")
    cons_streak = 0
    max_cons_streak = 0
    for char in username:
        if char not in vowels:
            cons_streak += 1
            max_cons_streak = max(max_cons_streak, cons_streak)
        else:
            cons_streak = 0

    is_trash = (max_cons_streak >= 3)

    # 💎 SSS+ РАНГ: Эксклюзивные 5-буквенные активы
    if (username in TOP_BRANDS) or (length == 5 and not is_trash):
        return {
            "rank": "SSS+", 
            "status": "Эксклюзивный актив (~150-600+ TON)", 
            "color": "#29c75f", 
            "score": 100
        }

    # 🥇 SS РАНГ: Сочные 6-буквенные бренды
    if (username in PURE_WORDS) or (length == 6 and not is_trash):
        return {
            "rank": "SS", 
            "status": "Редкий элитный ник (~40-150 TON)", 
            "color": "#eab308", 
            "score": 85
        }

    # 🥈 S РАНГ: Дорогие 7-буквенники
    if length == 7 and not is_trash:
        return {
            "rank": "S", 
            "status": "Премиум бренд (~10-40 TON)", 
            "color": "#a855f7", 
            "score": 65
        }

    # 🥉 A РАНГ: Солидные 8-буквенники
    if length == 8 and not is_trash:
        return {
            "rank": "A", 
            "status": "Стандартный красивый ник (~2-8 TON)", 
            "color": "#3b82f6", 
            "score": 40
        }

    # ⚪ B РАНГ
    if not is_trash and length <= 12:
        return {
            "rank": "B", 
            "status": "Для личного пользования (~1 TON)", 
            "color": "#64748b", 
            "score": 20
        }

    return {
        "rank": "F", 
        "status": "Низкая ценность (0 TON)", 
        "color": "#ef4444", 
        "score": 5
    }

# =========================================================================
# 🛡️ ПРОВЕРКА ЧЕРЕЗ TELETHON
# =========================================================================
async def check_username_telethon(username: str) -> bool:
    username = username.replace("@", "").strip().lower()
    if len(username) < 5: 
        return False

    try:
        result = await telethon_client(CheckUsernameRequest(username=username))
        return True if result is True else False
    except RPCError:
        return False
    except Exception:
        return False

# =========================================================================
# 📡 РАДАР
# =========================================================================
def load_radar_db() -> dict:
    if os.path.exists(RADAR_DB_PATH):
        try:
            with open(RADAR_DB_PATH, "r", encoding="utf-8") as f: 
                return json.load(f)
        except Exception: 
            return {}
    return {}

def save_radar_db(db: dict):
    try:
        with open(RADAR_DB_PATH, "w", encoding="utf-8") as f: 
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception: 
        pass

async def radar_worker():
    print("🚀 Автономный Радар запущен!")
    while True:
        try:
            db = load_radar_db()
            if db and bot:
                all_targets = set()
                for chat_id, targets in db.items():
                    for target in targets: 
                        all_targets.add(target.lower())

                for username in list(all_targets):
                    is_free = await check_username_telethon(username)
                    if is_free is True:
                        notified_chats = []
                        for chat_id, targets in list(db.items()):
                            if username in [t.lower() for t in targets]:
                                try:
                                    await bot.send_message(
                                        chat_id=int(chat_id), 
                                        text=f"🚨 **РАДАР: НИК ОСВОБОДИЛСЯ!**\n\nЮзернейм: `@{username}`\nБыстрее забирай!", 
                                        parse_mode="Markdown"
                                    )
                                    notified_chats.append(chat_id)
                                except Exception: 
                                    pass

                        for chat_id in notified_chats:
                            db[chat_id] = [t for t in db[chat_id] if t.lower() != username]
                            if not db[chat_id]: 
                                del db[chat_id]
                        save_radar_db(db)
                    await asyncio.sleep(1.5)
        except Exception: 
            pass
        await asyncio.sleep(5)

# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("⏳ Запуск Telethon...")
    await telethon_client.start()
    print("✅ Telethon успешно запущен!")
    
    asyncio.create_task(radar_worker())
    
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))
    
    yield
    await telethon_client.disconnect()

app = FastAPI(title="Username Generator & Checker PRO", lifespan=lifespan)

# --- API ---
@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH): 
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})

@app.get("/api/generate")
async def generate_username(
    request: Request, 
    platform: str = Query("telegram"),
    len_mode: str = Query("5-6"),
    finder_name: str = Query("Аноним"),
    finder_id: str = Query("0")
):
    client_ip = request.client.host if request.client else "global"
    now = time.time()
    if client_ip in USER_COOLDOWNS:
        elapsed = now - USER_COOLDOWNS[client_ip]
        if elapsed < COOLDOWN_SECONDS:
            await asyncio.sleep(COOLDOWN_SECONDS - elapsed)
    USER_COOLDOWNS[client_ip] = time.time()

    # До 15 быстрых проверок в секунду для мгновенного поиска свободного бренд-ника
    for _ in range(15):
        generated = generate_brand_username(len_mode)
        is_free = await check_username_telethon(generated)
        if is_free:
            eval_data = calculate_catch_score(generated, True)
            if eval_data["score"] >= 40:
                add_to_leaderboard(generated, eval_data["rank"], eval_data["status"], eval_data["score"], eval_data["color"], finder_name, finder_id)
            return {
                "status": "success", 
                "generated_username": generated, 
                "platform": platform, 
                "is_free": True, 
                "evaluation": eval_data
            }
        await asyncio.sleep(0.05)

    fallback_nick = generate_brand_username(len_mode)
    is_free_fallback = await check_username_telethon(fallback_nick)
    eval_data = calculate_catch_score(fallback_nick, is_free_fallback)
    
    if is_free_fallback and eval_data["score"] >= 40:
        add_to_leaderboard(fallback_nick, eval_data["rank"], eval_data["status"], eval_data["score"], eval_data["color"], finder_name, finder_id)

    return {
        "status": "success", 
        "generated_username": fallback_nick, 
        "platform": platform, 
        "is_free": is_free_fallback, 
        "evaluation": eval_data
    }

@app.get("/api/leaderboard")
async def get_leaderboard(period: str = Query("all")):
    lb = load_leaderboard()
    now = int(time.time())
    if period == "day": 
        lb = [x for x in lb if now - x.get("timestamp", 0) <= 86400]
    elif period == "week": 
        lb = [x for x in lb if now - x.get("timestamp", 0) <= 604800]
    elif period == "month": 
        lb = [x for x in lb if now - x.get("timestamp", 0) <= 2592000]
    return {"status": "ok", "leaderboard": lb[:1000]}

@app.get("/api/radar/add")
async def radar_add(chat_id: str, username: str):
    db = load_radar_db()
    chat_id, username = str(chat_id).strip(), username.replace("@", "").strip().lower()
    if not username: 
        return {"status": "error", "message": "Пустой юзернейм"}
    if chat_id not in db: 
        db[chat_id] = []
    if username not in db[chat_id]: 
        db[chat_id].append(username)
        save_radar_db(db)
    return {"status": "ok", "targets": db[chat_id]}

@app.get("/api/radar/list")
async def radar_list(chat_id: str):
    return {"targets": load_radar_db().get(str(chat_id).strip(), [])}

@app.get("/api/radar/remove")
async def radar_remove(chat_id: str, username: str):
    db = load_radar_db()
    chat_id, username = str(chat_id).strip(), username.replace("@", "").strip().lower()
    if chat_id in db and username in db[chat_id]:
        db[chat_id].remove(username)
        if not db[chat_id]: 
            del db[chat_id]
        save_radar_db(db)
    return {"status": "ok", "targets": db.get(chat_id, [])}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
