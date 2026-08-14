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
from telethon.errors import RPCError, FloodWaitError
from telethon.tl.functions.account import CheckUsernameRequest
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
RADAR_DB_PATH = os.path.join(BASE_DIR, "radar_db.json")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "leaderboard_db.json")
GAME_DB_PATH = os.path.join(BASE_DIR, "game_data.json")

# Асинхронный замок для защиты от одновременной записи в БД
DB_LOCK = asyncio.Lock()

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
CHECK_CACHE = {}
CACHE_TTL = 86400

# =========================================================================
# 💾 ИГРОВАЯ БАЗА ДАННЫХ И ЭКОНОМИКА (CYBER TYCOON)
# =========================================================================
def load_game_db() -> dict:
    if os.path.exists(GAME_DB_PATH):
        try:
            with open(GAME_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_game_db(db: dict):
    try:
        with open(GAME_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def get_user_profile(db: dict, user_id: str) -> dict:
    now = int(time.time())
    user_id = str(user_id).strip()
    if user_id not in db:
        db[user_id] = {
            "coins": 0,
            "energy": 1000,
            "max_energy": 1000,
            "multi_tap": 1,
            "energy_regen": 1,  # Строгий баланс: +1 энергия в секунду
            "offline_miner_lvl": 0,
            "last_seen": now,
            "unlocked_themes": [],
            "radar_extra_slots": 0,
            "has_turbo": False,
            "rank": "Ловец"
        }
    
    user = db[user_id]
    time_passed = now - user.get("last_seen", now)
    if time_passed > 0 and user["energy"] < user["max_energy"]:
        regen_amount = time_passed * user.get("energy_regen", 1)
        user["energy"] = min(user["max_energy"], user["energy"] + regen_amount)

    return user

# =========================================================================
# 📚 БАЗА БРЕНДОВ И ТОПОВЫХ СЛОВ
# =========================================================================
TOP_BRANDS = set([
    "mcdonalds", "subway", "ronaldo", "messi", "nike", "adidas", "apple", "google",
    "tesla", "bitcoin", "crypto", "pavel", "durov", "telegram", "starbucks", "prada",
    "gucci", "porsche", "bmw", "mercedes", "ferrari", "redbull", "steam", "roblox"
])

PURE_WORDS = (
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
).split()

CONSONANTS_EASY = "bcdfgklmnprstvwz"
VOWELS_EASY = "aeiouy"

def generate_smart_username(len_mode: str, use_num: bool, use_und: bool) -> tuple[str, bool, bool]:
    target_len = random.choice([5, 6]) if len_mode == "5-6" else random.choice([7, 8])
    res = ""
    start_with_consonant = random.choice([True, False])
    for i in range(target_len):
        if (i % 2 == 0 and start_with_consonant) or (i % 2 == 1 and not start_with_consonant):
            res += random.choice(CONSONANTS_EASY)
        else:
            res += random.choice(VOWELS_EASY)

    if use_und and len(res) >= 5:
        pos = random.randint(2, len(res) - 2)
        res = res[:pos] + "_" + res[pos+1:]

    if use_num and len(res) >= 5:
        num = str(random.randint(1, 99))
        res = res[:-len(num)] + num

    return res, True, use_und

# =========================================================================
# 👑 ХРАНИЛИЩЕ ЛИДЕРБОРДА
# =========================================================================
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
# 💎 АЛГОРИТМ ОЦЕНКИ
# =========================================================================
def calculate_catch_score(username: str, check_result, is_pure: bool, has_und: bool):
    if check_result is not True:
        return {"rank": "F", "status": "Занят", "color": "#ef4444", "score": 0}
    
    username = username.lower().replace("@", "").strip()
    length = len(username)
    vowels = set("aeiouy")
    has_num = any(char.isdigit() for char in username)
    
    if has_und or has_num or length > 8:
        return {"rank": "A", "status": "Обычный ник (~1-2 TON)", "color": "#3b82f6", "score": 20}
    
    cons_streak = 0
    max_cons_streak = 0
    for char in username:
        if char not in vowels:
            cons_streak += 1
            max_cons_streak = max(max_cons_streak, cons_streak)
        else:
            cons_streak = 0

    if max_cons_streak >= 3:
        return {"rank": "A", "status": "Набор букв (~1 TON)", "color": "#3b82f6", "score": 10}

    if username in TOP_BRANDS or username in PURE_WORDS:
        return {"rank": "SSS+", "status": "Fragment: High Value (~100-500+ TON)", "color": "#29c75f", "score": 100}

    if length <= 4:
        return {"rank": "SSS+", "status": "Fragment (~50-150 TON)", "color": "#29c75f", "score": 90}
    elif length == 5:
        return {"rank": "SS", "status": "Fragment (~15-40 TON)", "color": "#eab308", "score": 75}
    elif length == 6:
        return {"rank": "S", "status": "Красивый актив (~5-15 TON)", "color": "#a855f7", "score": 55}
    
    return {"rank": "A", "status": "Обычный ник (~1-3 TON)", "color": "#3b82f6", "score": 30}

# =========================================================================
# 🔎 ПРОВЕРКА TELETHON
# =========================================================================
async def check_username_telethon(username: str, ignore_cache: bool = False):
    username = username.replace("@", "").strip().lower()
    if len(username) < 5: 
        return False
    now = time.time()

    if not ignore_cache and username in CHECK_CACHE:
        cached_result, cached_time = CHECK_CACHE[username]
        if now - cached_time < CACHE_TTL:
            return cached_result

    try:
        result = await telethon_client(CheckUsernameRequest(username=username))
        is_free = True if result is True else False
        CHECK_CACHE[username] = (is_free, now)
        return is_free
    except Exception:
        return False

# =========================================================================
# 🎯 РАДАР
# =========================================================================
def load_radar_db():
    if os.path.exists(RADAR_DB_PATH):
        try:
            with open(RADAR_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_radar_db(db):
    try:
        with open(RADAR_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

async def radar_worker():
    while True:
        try:
            db = load_radar_db()
            if db and bot:
                for chat_id, targets in list(db.items()):
                    for username in list(targets):
                        is_free = await check_username_telethon(username, ignore_cache=True)
                        if is_free is True:
                            try:
                                await bot.send_message(
                                    chat_id=int(chat_id),
                                    text=f"🚨 РАДАР: НИК ОСВОБОДИЛСЯ!\n\nНикнейм: @{username}\nБыстрее забирай!",
                                    parse_mode="Markdown"
                                )
                                db[chat_id].remove(username)
                                save_radar_db(db)
                            except Exception:
                                pass
                        await asyncio.sleep(2)
        except Exception:
            pass
        await asyncio.sleep(10)

# =========================================================================
# ⚙️ LIFESPAN FASTAPI
# =========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("⏳ Запуск Telethon сессии...")
    await telethon_client.start()
    print("✅ Telethon сессия успешно запущена!")
    
    asyncio.create_task(radar_worker())
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))
    
    yield
    print("🛑 Остановка Telethon...")
    await telethon_client.disconnect()

app = FastAPI(title="Username Generator & Checker PRO", lifespan=lifespan)

# =========================================================================
# 🎮 ЭНДПОИНТЫ КЛИКЕРА COSMIC CORE
# =========================================================================
OFFLINE_RATES = {
    0: 0, 
    1: 500, 
    2: 1200, 
    3: 2500, 
    4: 4500, 
    5: 8000, 
    6: 14000, 
    7: 22000, 
    8: 32000, 
    9: 45000, 
    10: 60000
}

@app.get("/api/game/state")
async def get_game_state(user_id: str):
    async with DB_LOCK:
        db = load_game_db()
        user = get_user_profile(db, user_id)
        now = int(time.time())
        time_diff = now - user["last_seen"]
        offline_earned = 0
        if time_diff > 60 and user["offline_miner_lvl"] > 0:
            clamped_time = min(time_diff, 10800)  # Максимум 3 часа
            rate_per_sec = OFFLINE_RATES.get(user["offline_miner_lvl"], 500) / 3600.0
            offline_earned = int(clamped_time * rate_per_sec)
            user["coins"] += offline_earned

        user["last_seen"] = now
        save_game_db(db)
        return {"status": "ok", "profile": user, "offline_earned": offline_earned}

@app.post("/api/game/sync_tap")
async def sync_tap(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "default_guest")).strip()
    taps = int(data.get("taps", 0))
    
    async with DB_LOCK:
        db = load_game_db()
        user = get_user_profile(db, user_id)
        if taps > 0:
            actual_taps = min(taps, user["energy"])
            if actual_taps > 0:
                earned = actual_taps * user["multi_tap"]
                user["coins"] += earned
                user["energy"] = max(0, user["energy"] - actual_taps)
                user["last_seen"] = int(time.time())
                save_game_db(db)
        return {
            "status": "ok", 
            "coins": user["coins"], 
            "server_energy": user["energy"], 
            "multi_tap": user["multi_tap"]
        }

@app.post("/api/game/buy")
async def buy_item(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "default_guest")).strip()
    item_id = str(data.get("item_id", ""))
    
    async with DB_LOCK:
        db = load_game_db()
        user = get_user_profile(db, user_id)

        if item_id == "multi_tap":
            cost = int(200 * (1.8 ** (user["multi_tap"] - 1)))
            if user["coins"] >= cost and user["multi_tap"] < 20:
                user["coins"] -= cost
                user["multi_tap"] += 1
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "max_energy":
            lvl = (user["max_energy"] - 1000) // 500
            cost = int(150 * (1.6 ** lvl))
            if user["coins"] >= cost and lvl < 20:
                user["coins"] -= cost
                user["max_energy"] += 500
                user["energy"] = user["max_energy"]
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "offline_miner":
            lvl = user["offline_miner_lvl"]
            cost = 3000 if lvl == 0 else int(3000 * (2.2 ** lvl))
            if user["coins"] >= cost and lvl < 10:
                user["coins"] -= cost
                user["offline_miner_lvl"] += 1
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "radar_slot":
            if user["coins"] >= 5000:
                user["coins"] -= 5000
                user["radar_extra_slots"] += 1
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "turbo_parse":
            if user["coins"] >= 3500:
                user["coins"] -= 3500
                user["has_turbo"] = True
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "theme_cyberpunk":
            if user["coins"] >= 40000 and "cyberpunk" not in user["unlocked_themes"]:
                user["coins"] -= 40000
                user["unlocked_themes"].append("cyberpunk")
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "rank_legend":
            if user["coins"] >= 100000:
                user["coins"] -= 100000
                user["rank"] = "👑 Легендарный Ловец"
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        user["last_seen"] = int(time.time())
        save_game_db(db)
        return {"status": "ok", "profile": user}

# =========================================================================
# 🌐 РОУТЫ ГЕНЕРАТОРА И СТАТИЧЕСКИХ ДАННЫХ
# =========================================================================
@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH): 
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})

@app.get("/api/generate")
async def generate_username(
    request: Request, 
    platform: str = Query("telegram"), 
    use_filter: bool = Query(False), 
    len_mode: str = Query("5-6"), 
    use_num: bool = Query(False), 
    use_und: bool = Query(False), 
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

    for _ in range(5):
        if use_filter:
            generated, is_pure, has_und = generate_smart_username(len_mode, use_num, use_und)
        else:
            if random.random() < 0.25:
                generated = random.choice(list(TOP_BRANDS) + PURE_WORDS)
                is_pure, has_und = True, False
            else:
                generated, is_pure, has_und = generate_smart_username(len_mode, use_num, use_und)

        check_result = await check_username_telethon(generated)

        if check_result is not None:
            is_free_bool = True if check_result is True else False
            eval_data = calculate_catch_score(generated, check_result, is_pure, has_und)
            
            if is_free_bool and eval_data["score"] >= 50:
                add_to_leaderboard(
                    generated, 
                    eval_data["rank"], 
                    eval_data["status"], 
                    eval_data["score"], 
                    eval_data["color"],
                    finder_name,
                    finder_id
                )

            return {
                "status": "success",
                "generated_username": generated,
                "platform": platform,
                "is_free": is_free_bool,
                "evaluation": eval_data
            }
        
        await asyncio.sleep(0.05)

    return JSONResponse(status_code=503, content={"error": "telethon_timeout"})

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
    chat_id = str(chat_id).strip()
    if chat_id not in db: 
        db[chat_id] = []
    username = username.replace("@", "").strip().lower()
    if username and username not in db[chat_id]:
        db[chat_id].append(username)
        save_radar_db(db)
    return {"status": "ok", "targets": db[chat_id]}

@app.get("/api/radar/list")
async def radar_list(chat_id: str):
    return {"targets": load_radar_db().get(str(chat_id).strip(), [])}

@app.get("/api/radar/remove")
async def radar_remove(chat_id: str, username: str):
    db = load_radar_db()
    chat_id = str(chat_id).strip()
    username = username.replace("@", "").strip().lower()
    if chat_id in db and username in db[chat_id]:
        db[chat_id].remove(username)
        save_radar_db(db)
    return {"status": "ok", "targets": db.get(chat_id, [])}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
