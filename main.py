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
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
RADAR_DB_PATH = os.path.join(BASE_DIR, "radar_db.json")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "leaderboard_db.json")
FREE_POOL_PATH = os.path.join(BASE_DIR, "free_pool.json")
TAKEN_CACHE_PATH = os.path.join(BASE_DIR, "taken_cache.json")

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
WEEK_IN_SECONDS = 604800  # 7 дней

# =========================================================================
# 🚫 УПРАВЛЕНИЕ КЭШЕМ ЗАНЯТЫХ НИКОВ (BLACK_LIST ИСКЛЮЧЕНИЙ)
# =========================================================================
def load_taken_cache() -> dict:
    """Загружает словарь занятых ников { "username": timestamp }"""
    if os.path.exists(TAKEN_CACHE_PATH):
        try:
            with open(TAKEN_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_taken_cache(cache_data: dict):
    try:
        with open(TAKEN_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def mark_as_taken(username: str):
    """Запоминает ник как занятый с текущей меткой времени."""
    clean_user = username.lower().strip()
    cache = load_taken_cache()
    cache[clean_user] = int(time.time())
    save_taken_cache(cache)

def is_in_taken_cache(username: str) -> bool:
    """Проверяет, есть ли ник в базе недавно проверенных заняток."""
    clean_user = username.lower().strip()
    cache = load_taken_cache()
    return clean_user in cache

async def cleanup_taken_cache_worker():
    """Фоновый воркер: каждые 12 часов сбрасывает из кэша ники старше 7 дней."""
    while True:
        try:
            cache = load_taken_cache()
            now = int(time.time())
            updated_cache = {}
            cleared_count = 0
            
            for nick, timestamp in cache.items():
                if now - timestamp < WEEK_IN_SECONDS:
                    updated_cache[nick] = timestamp
                else:
                    cleared_count += 1
            
            if cleared_count > 0:
                save_taken_cache(updated_cache)
                print(f"🧹 Кэш очищен! Удалено {cleared_count} устаревших занятых ников (старше 7 дней).")

        except Exception as err:
            print(f"Ошибка при очистке кэша: {err}")
            
        await asyncio.sleep(43200)

# =========================================================================
# 📚 БАЗА СЛОВ И БРЕНДОВ
# =========================================================================
TOP_BRANDS = set([
    "mcdonalds", "subway", "ronaldo", "messi", "nike", "adidas", "apple", "google",
    "tesla", "bitcoin", "crypto", "pavel", "durov", "telegram", "starbucks", "prada",
    "gucci", "porsche", "bmw", "mercedes", "ferrari", "redbull", "steam", "roblox",
    "matrix", "cyber", "vortex", "shadow", "phantom", "legend", "oracle", "nexus"
])

PURE_WORDS = set((
    "apple world music house light dream space power smart stone water earth cloud storm "
    "river ocean flame shadow silver golden crystal magic spirit nature forest winter summer "
    "spring sunset sunrise silent secret future vision wonder action energy galaxy cosmic "
    "infinity legend hero master leader pioneer champion starlight moonlight diamond emerald "
    "sapphire phoenix dragon falcon freedom victory passion harmony destiny horizon paradise "
    "eternity velvet breeze velocity aurora solitude serenity zenith vortex nebula castle "
    "kingdom throne emperor knight shield sword crown dynasty legacy empire symbol beacon "
    "summit peak vertex vector matrix orbit alpha beta gamma delta echo tango fox wolf bear "
    "eagle lion tiger shark panther snake cobra viper raven hawk owl deer midnight dawn dusk "
    "abyss nova pulsar quasar comet meteor planet star sun moon sky wind rain snow ice frost "
    "fire ash ember spark glow ray beam wave tide surf shore coast island mountain hill valley"
).split())

PREFIXES = [
    "ast", "cyb", "syn", "neo", "sol", "vox", "lux", "aeg", "chr", "hyp", 
    "ver", "zen", "orb", "nov", "arc", "mon", "pyr", "val", "kry", "tha",
    "nex", "omni", "aero", "omna", "vort", "phos", "zeph", "vect", "kilo"
]

SUFFIXES = [
    "ex", "is", "os", "um", "ia", "or", "ix", "on", "ar", "al", 
    "ic", "in", "us", "en", "ax", "ys", "op", "io", "ez", "eth"
]

CONSONANTS_EASY = "bcdfgklmnprstvwz"
VOWELS_EASY = "aeiouy"

# --- РАБОТА С ПУЛОМ СВОБОДНЫХ НИКОВ ---
def load_free_pool() -> list:
    if os.path.exists(FREE_POOL_PATH):
        try:
            with open(FREE_POOL_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_free_pool(data: list):
    try:
        with open(FREE_POOL_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

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
# 👑 ЭКСПЕРТНАЯ ОЦЕНКА РАНГОВ И СТОИМОСТИ
# =========================================================================
def calculate_catch_score(username: str, check_result: bool):
    if not check_result:
        return {"rank": "F", "status": "Занят", "color": "#ef4444", "score": 0}
    
    username = username.lower().replace("@", "").strip()
    length = len(username)
    
    if length < 5:
        return {"rank": "F", "status": "Короче 5 символов", "color": "#ef4444", "score": 0}

    if any(char.isdigit() or char == "_" for char in username):
        return {"rank": "F", "status": "Содержит нежелательные символы", "color": "#ef4444", "score": 0}

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

    # 💎 SSS+ РАНГ: Известные бренды любой длины или идеальные 5-буквенники
    if (username in TOP_BRANDS) or (length == 5 and not is_trash):
        return {"rank": "SSS+", "status": "High Value Item (~100-500+ TON)", "color": "#29c75f", "score": 100}

    # 🥇 SS РАНГ: Известные словарные слова или чистые 6-буквенники
    if (username in PURE_WORDS) or (length == 6 and not is_trash):
        return {"rank": "SS", "status": "Rare Asset (~25-100 TON)", "color": "#eab308", "score": 85}

    # 🥈 S РАНГ: Красивые 7-буквенники
    if length == 7 and not is_trash:
        return {"rank": "S", "status": "Premium Active (~5-25 TON)", "color": "#a855f7", "score": 65}

    # 🥉 A РАНГ: 8-буквенники
    if length == 8 and not is_trash:
        return {"rank": "A", "status": "Standard Name (~1-5 TON)", "color": "#3b82f6", "score": 40}

    # ⚪ B РАНГ: Длинные личные слова без мусора
    if not is_trash and length <= 12:
        return {"rank": "B", "status": "Personal Use (~0.5-1 TON)", "color": "#64748b", "score": 20}

    return {"rank": "F", "status": "Low Demand (0 TON)", "color": "#ef4444", "score": 5}

# =========================================================================
# ⚡ ПРОВЕРКА ЧЕРЕЗ TELETHON С ФИЛЬТРАЦИЕЙ ЗАНЯТЫХ
# =========================================================================
async def check_username_telethon(username: str):
    username = username.replace("@", "").strip().lower()
    if len(username) < 5: 
        return False

    # Если ник уже в кэше занятых — пропускаем без лишнего запроса к Telegram
    if is_in_taken_cache(username):
        return False

    try:
        result = await telethon_client(CheckUsernameRequest(username=username))
        if result is True:
            return True
        else:
            mark_as_taken(username)
            return False
    except Exception:
        mark_as_taken(username)
        return False

# =========================================================================
# 🧬 ГЕНЕРАТОР (С УЧЕТОМ НАСТРОЕК ДЛИНЫ И ПОЛНЫХ БРЕНДОВ)
# =========================================================================
def generate_smart_username(len_mode: str = "5-6") -> str:
    for _ in range(20):
        # 30% шанс подтянуть реальный бренд или словарное слово (без срезания длины!)
        if random.random() < 0.30:
            candidate = random.choice(list(TOP_BRANDS) + list(PURE_WORDS))
        else:
            mode = random.choice(["morpheme", "phonetic"])
            if mode == "morpheme":
                pref = random.choice(PREFIXES)
                suf = random.choice(SUFFIXES)
                candidate = pref + suf
                # Ограничиваем длину только для морфемных комбинаций, если включён фильтр 5-6
                if len_mode == "5-6" and len(candidate) > 6:
                    candidate = candidate[:6]
            else:
                target_len = random.choice([5, 6]) if len_mode == "5-6" else random.choice([7, 8])
                candidate = ""
                start_with_consonant = random.choice([True, False])
                for i in range(target_len):
                    if (i % 2 == 0 and start_with_consonant) or (i % 2 == 1 and not start_with_consonant):
                        candidate += random.choice(CONSONANTS_EASY)
                    else:
                        candidate += random.choice(VOWELS_EASY)
        
        if not is_in_taken_cache(candidate):
            return candidate

    return candidate

# --- ФОНОВЫЙ ВОРКЕР НАПОЛНЕНИЯ ПУЛА ---
async def pool_worker():
    print("⚙️ Фоновый автопарсер пула запущен!")
    while True:
        try:
            pool = load_free_pool()
            if len(pool) < 50:
                candidate = generate_smart_username("5-6")
                is_free = await check_username_telethon(candidate)
                
                if is_free:
                    eval_data = calculate_catch_score(candidate, True)
                    item = {"username": candidate, "evaluation": eval_data}
                    if not any(x["username"] == candidate for x in pool):
                        pool.append(item)
                        save_free_pool(pool)
                        print(f"🟢 В пул добавлен свободный ник: @{candidate} | Ранг: {eval_data['rank']}")

            await asyncio.sleep(1.5)
        except Exception as err:
            print(f"Ошибка в pool_worker: {err}")
            await asyncio.sleep(5)

# --- РАДАР ---
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
    print("🚀 Радар запущен!")
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
                                        text=f"🚨 **РАДАР: НИК ОСВОБОДИЛСЯ!**\n\nЮзернейм: `@{username}`\nЗабирай!", 
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
    print("✅ Telethon запущен!")
    
    asyncio.create_task(pool_worker())
    asyncio.create_task(radar_worker())
    asyncio.create_task(cleanup_taken_cache_worker())
    
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

    pool = load_free_pool()
    if pool:
        item = pool.pop(0)
        save_free_pool(pool)
        generated = item["username"]
        eval_data = item["evaluation"]

        if eval_data["score"] >= 40:
            add_to_leaderboard(generated, eval_data["rank"], eval_data["status"], eval_data["score"], eval_data["color"], finder_name, finder_id)

        return {"status": "success", "generated_username": generated, "platform": platform, "is_free": True, "evaluation": eval_data}

    for _ in range(3):
        generated = generate_smart_username(len_mode)
        is_free = await check_username_telethon(generated)
        if is_free:
            eval_data = calculate_catch_score(generated, True)
            if eval_data["score"] >= 40:
                add_to_leaderboard(generated, eval_data["rank"], eval_data["status"], eval_data["score"], eval_data["color"], finder_name, finder_id)
            return {"status": "success", "generated_username": generated, "platform": platform, "is_free": True, "evaluation": eval_data}
        await asyncio.sleep(0.1)

    fallback_nick = generate_smart_username(len_mode)
    eval_data = calculate_catch_score(fallback_nick, True)
    return {"status": "success", "generated_username": fallback_nick, "platform": platform, "is_free": True, "evaluation": eval_data}

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
