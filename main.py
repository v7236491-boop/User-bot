import os
import random
import asyncio
import time
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request, HTTPException
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

# --- ГЛОБАЛЬНАЯ ПАМЯТЬ СЕРВЕРА ---
GENERATED_HISTORY = set()
MAX_HISTORY_SIZE = 15000

# --- ЗАЩИТА ОТ DDOS / RATE LIMITING ---
IP_REQUEST_HISTORY = {}
MAX_REQUESTS_PER_MINUTE = 25
USER_COOLDOWNS = {}
COOLDOWN_SECONDS = 0.4

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

# =========================================================================
# 💎 МИЛЛИОННАЯ КОМБИНАТОРНАЯ МАТРИЦА И ПРЕМИУМ-СОСТАВНЫЕ НИКИ
# =========================================================================

# Базовые бренды и слова для составных 5% сочетаний (Subway Fresh style)
CORE_BRANDS = [
    "subway", "matrix", "crypto", "cyber", "orbit", "vortex", "nexus", "shadow",
    "phantom", "vector", "signal", "pulse", "aether", "solaris", "velvet", "zenith",
    "qubit", "prisma", "apex", "vertex", "sigma", "hyper", "titan", "astro"
]

PREMIUM_MODIFIERS = [
    "fresh", "club", "lab", "hub", "space", "vibe", "zone", "prime", "pro",
    "one", "base", "core", "link", "wave", "flow", "spot", "vault", "mind"
]

# Топовые сонорные корни (50+)
BRAND_ROOTS = [
    "aeth", "chron", "sol", "vort", "lum", "phos", "zeph", "celest", "aeg", "crest",
    "val", "kism", "ast", "spect", "temp", "tit", "mir", "aur", "prism", "orion",
    "verv", "lun", "stell", "zen", "hyp", "myth", "nobl", "quant", "rhod", "sir",
    "solac", "krypt", "nebul", "synth", "neor", "vax", "zoran", "velv", "aero", "omni",
    "dusk", "dawn", "echo", "flux", "rift", "glow", "pulse", "crest", "vark", "zene"
]

# Связующие элементы для богатства звучания (16)
BRAND_MIDDLES = [
    "o", "a", "i", "e", "u", "ar", "or", "in", "is", "ex", "an", "el", "on", "al", "ev", "ix"
]

# Сочные суффиксы (24)
BRAND_SUFFIXES = [
    "is", "ex", "or", "um", "on", "us", "ia", "ix", "ar", "al", "io", "ora", "eth",
    "is", "ux", "ax", "era", "ita", "ys", "en", "op", "ez", "os", "id"
]

TOP_BRANDS_EVAL = set(CORE_BRANDS)
PURE_WORDS_EVAL = set(PREMIUM_MODIFIERS)

def generate_brand_username(len_mode: str = "5-6") -> str:
    """Генерирует уникальный, сочный никнейм из миллиона вариантов."""
    global GENERATED_HISTORY
    
    if len(GENERATED_HISTORY) > MAX_HISTORY_SIZE:
        GENERATED_HISTORY.clear()

    for _ in range(20):
        roll = random.random()
        
        # 🌟 5% ШАНС: Составной Ультра-дорогой никнейм (Subway Fresh style)
        if roll < 0.05:
            brand = random.choice(CORE_BRANDS)
            modifier = random.choice(PREMIUM_MODIFIERS)
            candidate = brand + modifier
        
        # 🌟 95% ШАНС: Трехсложные или двухсложные миллионные неологизмы
        else:
            root = random.choice(BRAND_ROOTS)
            suf = random.choice(BRAND_SUFFIXES)
            
            # 40% шанс добавить связующую медиаль для усложнения и сочности
            if random.random() < 0.40 and len_mode != "5-6":
                mid = random.choice(BRAND_MIDDLES)
                candidate = root + mid + suf
            else:
                candidate = root + suf
                
            # Очистка сложных стыков
            candidate = (candidate.replace("nn", "n")
                                 .replace("ss", "s")
                                 .replace("rr", "r")
                                 .replace("oo", "o")
                                 .replace("ee", "e"))
            
            if len_mode == "5-6" and len(candidate) > 6:
                candidate = candidate[:6]

        if candidate not in GENERATED_HISTORY and len(candidate) >= 5:
            return candidate

    root = random.choice(BRAND_ROOTS)
    return (root + random.choice(BRAND_SUFFIXES))[:6]

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

    # Двухсоставные топовые брендовые уловы (SubwayFresh стиль)
    is_composite_premium = any(brand in username for brand in CORE_BRANDS) and any(mod in username for mod in PREMIUM_MODIFIERS)

    if is_composite_premium or (length == 5 and not is_trash):
        return {
            "rank": "SSS+", 
            "status": "Эксклюзивный актив (~200-800+ TON)", 
            "color": "#29c75f", 
            "score": 100
        }

    if length == 6 and not is_trash:
        return {
            "rank": "SS", 
            "status": "Редкий элитный ник (~50-200 TON)", 
            "color": "#eab308", 
            "score": 85
        }

    if length == 7 and not is_trash:
        return {
            "rank": "S", 
            "status": "Премиум бренд (~15-50 TON)", 
            "color": "#a855f7", 
            "score": 65
        }

    if length <= 10 and not is_trash:
        return {
            "rank": "A", 
            "status": "Стандартный красивый ник (~3-15 TON)", 
            "color": "#3b82f6", 
            "score": 40
        }

    return {
        "rank": "B", 
        "status": "Для личного пользования (~1 TON)", 
        "color": "#64748b", 
        "score": 20
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

# =========================================================================
# 🛡️ MIDDLEWARE ЗАЩИТЫ ОТ DDOS / БОТОВ
# =========================================================================
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "global"
    now = time.time()

    if request.url.path in ["/", "/index.html"]:
        return await call_next(request)

    if client_ip not in IP_REQUEST_HISTORY:
        IP_REQUEST_HISTORY[client_ip] = []

    IP_REQUEST_HISTORY[client_ip] = [
        t for t in IP_REQUEST_HISTORY[client_ip] if now - t < 60
    ]

    if len(IP_REQUEST_HISTORY[client_ip]) >= MAX_REQUESTS_PER_MINUTE:
        return JSONResponse(
            status_code=429,
            content={"status": "error", "message": "Слишком много запросов! Подождите минуту."}
        )

    IP_REQUEST_HISTORY[client_ip].append(now)
    return await call_next(request)

# --- API ROUTING ---
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

    # До 8 точечных быстрых проверок
    for _ in range(8):
        generated = generate_brand_username(len_mode)
        is_free = await check_username_telethon(generated)
        if is_free:
            GENERATED_HISTORY.add(generated)
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
        await asyncio.sleep(0.04)

    fallback_nick = generate_brand_username(len_mode)
    is_free_fallback = await check_username_telethon(fallback_nick)
    eval_data = calculate_catch_score(fallback_nick, is_free_fallback)
    
    if is_free_fallback:
        GENERATED_HISTORY.add(fallback_nick)
        if eval_data["score"] >= 40:
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
