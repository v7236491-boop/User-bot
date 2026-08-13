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
GAME_DB_PATH = os.path.join(BASE_DIR, "game_data.json")

# --- ГЛОБАЛЬНАЯ ПАМЯТЬ СЕРВЕРА ---
GENERATED_HISTORY = set()
MAX_HISTORY_SIZE = 25000

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
# 💾 ИГРОВАЯ БАЗА ДАННЫХ И ОФФЛАЙН-ФАРМ
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
    if user_id not in db:
        db[user_id] = {
            "coins": 0,
            "energy": 1000,
            "max_energy": 1000,
            "multi_tap": 1,
            "energy_regen": 1, # Жесткий баланс: 1 энергия в секунду
            "offline_miner_lvl": 0,
            "last_seen": now,
            "unlocked_themes": [],
            "radar_extra_slots": 0,
            "has_turbo": False,
            "rank": "Ловец"
        }
    
    user = db[user_id]
    time_passed = now - user.get("last_seen", now)
    # Восстанавливаем энергию за время отсутствия
    if time_passed > 0 and user["energy"] < user["max_energy"]:
        regen_amount = time_passed * user.get("energy_regen", 1)
        user["energy"] = min(user["max_energy"], user["energy"] + regen_amount)

    return user

# =========================================================================
# 📚 ПОЛНАЯ БАЗА ТЕМАТИЧЕСКИХ АФФИКСОВ
# =========================================================================
AFFIX_DATABASE = {
    "personal": ["official", "real", "prime", "live", "blog", "vibe", "zone", "one", "daily", "fan", "hq", "club"],
    "military": ["core", "tactics", "force", "unit", "prime", "zone", "command", "shield", "squad", "base", "lead"],
    "media": ["media", "universe", "zone", "hero", "studio", "space", "channel", "feed", "vision", "press", "cast"],
    "tech": ["lab", "hub", "space", "core", "app", "dev", "tech", "base", "net", "cloud", "desk", "code", "bot"],
    "crypto": ["vault", "pay", "trade", "node", "coin", "drop", "capital", "cash", "chain", "pool", "dex", "mint"],
    "gaming": ["play", "zone", "clan", "gg", "craft", "squad", "hero", "skill", "arena", "guild", "win", "rush"],
    "sports": ["fit", "run", "pro", "team", "cup", "champ", "sport", "gym", "league", "arena", "flex", "power"],
    "business": ["store", "shop", "brand", "market", "line", "boutique", "supply", "group", "co", "outlet", "style"],
    "auto": ["drive", "garage", "motors", "auto", "speed", "custom", "track", "power", "racing", "club"],
    "design": ["art", "studio", "design", "space", "lab", "craft", "visual", "frame", "gallery", "concept"],
    "food": ["fresh", "food", "cafe", "kitchen", "supply", "lounge", "taste", "craft", "market", "bar"],
    "music": ["sound", "beat", "wave", "records", "fm", "audio", "track", "vibe", "studio", "label"],
    "education": ["academy", "study", "hub", "mind", "center", "pioneer", "lab", "learn", "skill", "base"],
    "estate": ["estate", "realty", "place", "loft", "space", "house", "group", "park", "point", "living"],
    "auto_detect": ["my", "get", "go", "hq", "one", "vibe", "space", "zone", "core", "hub", "lab", "pro"]
}

TRANSLIT_WORDS = ["vostok", "imperia", "pobeda", "bereg", "kultura", "sovet", "otklik", "zvezda", "priboy", "vektor", "osnova", "sokol", "buran"]
TRANSLIT_AFFIXES = ["space", "lab", "vibe", "club", "one", "media", "hub", "zone", "core", "hq"]
BRAND_ROOTS = ["aeth", "chron", "sol", "vort", "lum", "phos", "zeph", "celest", "aeg", "crest", "val", "kism", "ast", "spect"]
BRAND_SUFFIXES = ["is", "ex", "or", "um", "on", "us", "ia", "ix", "ar", "al", "io", "ora", "eth"]

def generate_prefix_master(user_input: str, category: str = "auto_detect", position: str = "mix") -> str:
    clean_input = user_input.lower().strip().replace("@", "")
    affixes = AFFIX_DATABASE.get(category, AFFIX_DATABASE["auto_detect"])
    chosen_affix = random.choice(affixes)
    if position == "prefix": return f"{chosen_affix}{clean_input}"
    elif position == "suffix": return f"{clean_input}{chosen_affix}"
    else: return f"{clean_input}{chosen_affix}" if random.random() < 0.6 else f"{chosen_affix}{clean_input}"

def generate_translit_brand() -> str:
    base_word = random.choice(TRANSLIT_WORDS)
    if random.random() < 0.35: return f"{base_word}{random.choice(TRANSLIT_AFFIXES)}"
    return base_word

def generate_standard_brand(len_mode: str = "5-6") -> str:
    root = random.choice(BRAND_ROOTS)
    suf = random.choice(BRAND_SUFFIXES)
    candidate = (root + suf).replace("nn", "n").replace("ss", "s").replace("rr", "r")
    if len_mode == "5-6" and len(candidate) > 6: candidate = candidate[:6]
    return candidate

def load_leaderboard():
    if os.path.exists(LEADERBOARD_PATH):
        try:
            with open(LEADERBOARD_PATH, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: return []
    return []

def save_leaderboard(data):
    try:
        data = sorted(data, key=lambda x: x.get("score", 0), reverse=True)[:1000]
        with open(LEADERBOARD_PATH, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception: pass

def add_to_leaderboard(username, rank, price, score, color, finder_name, finder_id):
    lb = load_leaderboard()
    if any(item["username"].lower() == username.lower() for item in lb): return
    lb.append({
        "username": username, "rank": rank, "price": price, "score": score,
        "color": color, "finder_name": finder_name or "Аноним",
        "finder_id": finder_id or "0", "timestamp": int(time.time())
    })
    save_leaderboard(lb)

def calculate_catch_score(username: str, is_free: bool):
    if not is_free: return {"rank": "F", "status": "Занят", "color": "#ef4444", "score": 0}
    username = username.lower().replace("@", "").strip()
    length = len(username)
    if length < 5: return {"rank": "F", "status": "Меньше 5 символов", "color": "#ef4444", "score": 0}
    if any(char.isdigit() or char == "_" for char in username): return {"rank": "F", "status": "Символы/Цифры", "color": "#ef4444", "score": 0}

    is_trash = False
    vowels = set("aeiouy")
    cons_streak = 0
    for char in username:
        if char not in vowels:
            cons_streak += 1
            if cons_streak >= 3: is_trash = True
        else: cons_streak = 0

    if length == 5 and not is_trash: return {"rank": "SSS+", "status": "Эксклюзив (~200-800+ TON)", "color": "#29c75f", "score": 100}
    if length == 6 and not is_trash: return {"rank": "SS", "status": "Редкий ник (~50-200 TON)", "color": "#eab308", "score": 85}
    if length == 7 and not is_trash: return {"rank": "S", "status": "Премиум бренд (~15-50 TON)", "color": "#a855f7", "score": 65}
    if length <= 10 and not is_trash: return {"rank": "A", "status": "Красивый ник (~3-15 TON)", "color": "#3b82f6", "score": 40}
    return {"rank": "B", "status": "Для себя (~1 TON)", "color": "#64748b", "score": 20}

async def check_username_telethon(username: str) -> bool:
    username = username.replace("@", "").strip().lower()
    if len(username) < 5: return False
    try:
        result = await telethon_client(CheckUsernameRequest(username=username))
        return True if result is True else False
    except Exception: return False

def load_radar_db() -> dict:
    if os.path.exists(RADAR_DB_PATH):
        try:
            with open(RADAR_DB_PATH, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: return {}
    return {}

def save_radar_db(db: dict):
    try:
        with open(RADAR_DB_PATH, "w", encoding="utf-8") as f: json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception: pass

async def radar_worker():
    while True:
        try:
            db = load_radar_db()
            if db and bot:
                all_targets = set()
                for chat_id, targets in db.items():
                    for target in targets: all_targets.add(target.lower())

                for username in list(all_targets):
                    if await check_username_telethon(username):
                        for chat_id, targets in list(db.items()):
                            if username in [t.lower() for t in targets]:
                                try: await bot.send_message(chat_id=int(chat_id), text=f"🚨 **РАДАР:** Ник `@{username}` свободен!", parse_mode="Markdown")
                                except Exception: pass
                        for chat_id in list(db.keys()):
                            db[chat_id] = [t for t in db[chat_id] if t.lower() != username]
                            if not db[chat_id]: del db[chat_id]
                        save_radar_db(db)
                    await asyncio.sleep(1.5)
        except Exception: pass
        await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await telethon_client.start()
    asyncio.create_task(radar_worker())
    if bot and dp: asyncio.create_task(dp.start_polling(bot))
    yield
    await telethon_client.disconnect()

app = FastAPI(title="Username Scanner PRO", lifespan=lifespan)

# =========================================================================
# 🎮 ЭНДПОИНТЫ КЛИКЕРА И ЭКОНОМИКИ
# =========================================================================
OFFLINE_RATES = {0: 0, 1: 500, 2: 1200, 3: 2500, 4: 4500, 5: 8000, 6: 14000, 7: 22000, 8: 32000, 9: 45000, 10: 60000}

@app.get("/api/game/state")
async def get_game_state(user_id: str):
    db = load_game_db()
    user = get_user_profile(db, user_id)
    now = int(time.time())
    
    time_diff = now - user["last_seen"]
    offline_earned = 0
    if time_diff > 60 and user["offline_miner_lvl"] > 0:
        clamped_time = min(time_diff, 10800) # Максимум 3 часа
        rate_per_sec = OFFLINE_RATES.get(user["offline_miner_lvl"], 500) / 3600.0
        offline_earned = int(clamped_time * rate_per_sec)
        user["coins"] += offline_earned

    user["last_seen"] = now
    save_game_db(db)
    
    return {
        "status": "ok",
        "profile": user,
        "offline_earned": offline_earned
    }

# 🟢 ИДЕАЛЬНЫЙ СИНК ТАПОВ: Больше НИКАКИХ списаний монет!
@app.post("/api/game/sync_tap")
async def sync_tap(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "0"))
    taps = int(data.get("taps", 0))
    
    db = load_game_db()
    user = get_user_profile(db, user_id)
    
    if taps > 0:
        actual_taps = min(taps, user["energy"]) # Снимаем энергию, только если она есть
        if actual_taps > 0:
            earned = actual_taps * user["multi_tap"]
            user["coins"] += earned
            user["energy"] = max(0, user["energy"] - actual_taps)
            user["last_seen"] = int(time.time())
            save_game_db(db)
        
    # Мы возвращаем только серверную энергию, клиент сам ведет монеты, чтобы не было визуальных сбросов
    return {"status": "ok", "server_energy": user["energy"]}

@app.post("/api/game/buy")
async def buy_item(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "0"))
    item_id = str(data.get("item_id", ""))
    
    db = load_game_db()
    user = get_user_profile(db, user_id)
    
    if item_id == "multi_tap":
        cost = int(200 * (1.8 ** (user["multi_tap"] - 1)))
        if user["coins"] >= cost and user["multi_tap"] < 20:
            user["coins"] -= cost
            user["multi_tap"] += 1
        else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

    elif item_id == "max_energy":
        lvl = (user["max_energy"] - 1000) // 500
        cost = int(150 * (1.6 ** lvl))
        if user["coins"] >= cost and lvl < 20:
            user["coins"] -= cost
            user["max_energy"] += 500
            user["energy"] = user["max_energy"]
        else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

    elif item_id == "offline_miner":
        lvl = user["offline_miner_lvl"]
        cost = 3000 if lvl == 0 else int(3000 * (2.2 ** lvl))
        if user["coins"] >= cost and lvl < 10:
            user["coins"] -= cost
            user["offline_miner_lvl"] += 1
        else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

    elif item_id == "radar_slot":
        if user["coins"] >= 5000:
            user["coins"] -= 5000
            user["radar_extra_slots"] += 1
        else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

    elif item_id == "turbo_parse":
        if user["coins"] >= 3500:
            user["coins"] -= 3500
            user["has_turbo"] = True
        else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

    elif item_id == "theme_cyberpunk":
        if user["coins"] >= 40000 and "cyberpunk" not in user["unlocked_themes"]:
            user["coins"] -= 40000
            user["unlocked_themes"].append("cyberpunk")
        else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

    elif item_id == "rank_legend":
        if user["coins"] >= 100000:
            user["coins"] -= 100000
            user["rank"] = "👑 Легендарный Ловец"
        else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

    user["last_seen"] = int(time.time())
    save_game_db(db)
    return {"status": "ok", "profile": user}

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
    mode: str = Query("standard"),
    user_input: str = Query(""),
    category: str = Query("auto_detect"),
    position: str = Query("mix"),
    finder_name: str = Query("Аноним"),
    finder_id: str = Query("0")
):
    if len(GENERATED_HISTORY) > MAX_HISTORY_SIZE: GENERATED_HISTORY.clear()

    for _ in range(15):
        if mode == "prefix_master" and user_input.strip(): generated = generate_prefix_master(user_input, category, position)
        elif mode == "translit": generated = generate_translit_brand()
        else: generated = generate_standard_brand(len_mode)

        if generated not in GENERATED_HISTORY and len(generated) >= 5:
            is_free = await check_username_telethon(generated)
            if is_free:
                GENERATED_HISTORY.add(generated)
                eval_data = calculate_catch_score(generated, True)
                if eval_data["score"] >= 40:
                    add_to_leaderboard(generated, eval_data["rank"], eval_data["status"], eval_data["score"], eval_data["color"], finder_name, finder_id)
                return {"status": "success", "generated_username": generated, "platform": platform, "is_free": True, "evaluation": eval_data}
            await asyncio.sleep(0.08)

    fallback_nick = generate_standard_brand(len_mode)
    is_free_fallback = await check_username_telethon(fallback_nick)
    eval_data = calculate_catch_score(fallback_nick, is_free_fallback)
    return {"status": "success", "generated_username": fallback_nick, "platform": platform, "is_free": is_free_fallback, "evaluation": eval_data}

@app.get("/api/leaderboard")
async def get_leaderboard(period: str = Query("all")):
    lb = load_leaderboard()
    return {"status": "ok", "leaderboard": lb[:1000]}

@app.get("/api/radar/add")
async def radar_add(chat_id: str, username: str):
    db = load_radar_db()
    chat_id, username = str(chat_id).strip(), username.replace("@", "").strip().lower()
    if not username: return {"status": "error", "message": "Пустой юзернейм"}
    if chat_id not in db: db[chat_id] = []
    if username not in db[chat_id]: db[chat_id].append(username); save_radar_db(db)
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
        if not db[chat_id]: del db[chat_id]
        save_radar_db(db)
    return {"status": "ok", "targets": db.get(chat_id, [])}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
