import os
import random
import asyncio
import time
import json
import secrets
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
CHECK_CACHE = {}
CACHE_TTL = 86400
TELETHON_AVAILABLE = False
FAILED_ATTEMPTS = {}

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

OFFLINE_RATES = {
    0: 0, 1: 500, 2: 1200, 3: 2500, 4: 4500,
    5: 8000, 6: 14000, 7: 22000, 8: 32000, 9: 45000, 10: 60000
}

PLANET_HP_TABLE = {
    1: 100, 2: 300, 3: 800, 4: 2000, 5: 5000,
    6: 12000, 7: 28000, 8: 65000, 9: 150000, 10: 500000
}

KEY_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

def generate_secure_pro_key() -> str:
    p1 = "".join(secrets.choice(KEY_CHARSET) for _ in range(4))
    p2 = "".join(secrets.choice(KEY_CHARSET) for _ in range(4))
    p3 = "".join(secrets.choice(KEY_CHARSET) for _ in range(4))
    p4 = "".join(secrets.choice(KEY_CHARSET) for _ in range(4))
    return f"PRO-{p1}-{p2}-{p3}-{p4}"

def load_json_file(filepath: str, default_val):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default_val
    return default_val

def save_json_atomic_sync(filepath: str, data):
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, filepath)
    except Exception:
        pass

def init_master_keys():
    keys_db = load_json_file(KEYS_DB_PATH, {})
    master_key = "PRO-9X7K-4MRW-8N2T-H5VQ"
    if master_key not in keys_db:
        keys_db[master_key] = {
            "bound_user_id": None,
            "seconds": -1,
            "created_at": int(time.time()),
            "activated_status": "unused"
        }

    test_10m_key = "PRO-TEST-10MN-8K2R-9X4Q"
    if test_10m_key not in keys_db:
        keys_db[test_10m_key] = {
            "bound_user_id": None,
            "seconds": 600,
            "created_at": int(time.time()),
            "activated_status": "unused"
        }
    save_json_atomic_sync(KEYS_DB_PATH, keys_db)

init_master_keys()

def is_user_pro(user_id: str) -> tuple[bool, int]:
    db = load_json_file(GAME_DB_PATH, {})
    user = db.get(str(user_id).strip(), {})
    pro_until = user.get("pro_until", 0)
    now = int(time.time())
    if pro_until == -1:
        return True, -1
    if pro_until > now:
        return True, pro_until
    return False, 0

def get_user_profile(db: dict, user_id: str) -> dict:
    now = int(time.time())
    user_id = str(user_id).strip()
    if user_id not in db:
        db[user_id] = {
            "coins": 0,
            "energy": 1000,
            "max_energy": 1000,
            "multi_tap": 1,
            "energy_regen": 1,
            "offline_miner_lvl": 0,
            "last_seen": now,
            "unlocked_themes": [],
            "radar_extra_slots": 0,
            "turbo_until": 0,
            "offline_pending": 0,
            "planet_stage": 1,
            "planet_hp": PLANET_HP_TABLE[1],
            "rank": "Ловец",
            "pro_until": 0,
            "pro_warned": False,
            "pro_expired_notified": True
        }
    
    user = db[user_id]
    if "pro_until" not in user: user["pro_until"] = 0
    if "unlocked_themes" not in user: user["unlocked_themes"] = []
    if "radar_extra_slots" not in user: user["radar_extra_slots"] = 0
    if "turbo_until" not in user: user["turbo_until"] = 0
    if "offline_pending" not in user: user["offline_pending"] = 0
    if "planet_stage" not in user: user["planet_stage"] = 1
    if "planet_hp" not in user: user["planet_hp"] = PLANET_HP_TABLE.get(user["planet_stage"], 100)
    if "pro_warned" not in user: user["pro_warned"] = False
    if "pro_expired_notified" not in user: user["pro_expired_notified"] = True

    time_passed = now - user.get("last_seen", now)
    if time_passed > 0 and user["energy"] < user["max_energy"]:
        regen_amount = time_passed * user.get("energy_regen", 1)
        user["energy"] = min(user["max_energy"], user["energy"] + regen_amount)

    return user

# =========================================================================
# 💎 БАЗА ЭЛИТНЫХ И БЛАГОЗВУЧНЫХ КОРНЕЙ
# =========================================================================
PREMIUM_PREFIXES = ["neo", "vox", "lux", "zen", "vex", "arc", "sol", "dex", "sky", "ray", "val", "nox"]
PREMIUM_SUFFIXES = ["ex", "ix", "on", "ar", "is", "or", "us", "ax", "ox", "io", "ia", "en"]
ELITE_ROOTS = [
    "nova", "apex", "volt", "onyx", "flux", "aura", "lyra", "zane", "koda", "mira",
    "dusk", "dawn", "vibe", "luna", "zeta", "echo", "myth", "pulse", "rift", "warp",
    "neon", "zeal", "draco", "titus", "orion", "hydra", "frost", "blaze", "cyber", "prism"
]

AFFIX_DATABASE_20 = {
    "superheroes": ["hero", "lord", "prime", "knight", "origin", "verse", "force", "core", "squad", "shadow", "iron", "bat"],
    "cinema": ["film", "cast", "media", "show", "tape", "scene", "star", "cinema", "cut", "movie", "reel", "premiere"],
    "anime": ["kun", "chan", "senpai", "sama", "ninja", "shogun", "titan", "kage", "anime", "blade", "oni", "drift"],
    "gaming": ["play", "gg", "game", "quest", "clan", "craft", "hero", "guild", "respawn", "arena", "skill", "player"],
    "esports": ["pro", "major", "cup", "apex", "frag", "aim", "lead", "tactics", "prime", "win", "rush", "ace"],
    "crypto": ["ton", "coin", "vault", "dex", "chain", "node", "pool", "mint", "drop", "capital", "dao", "pay"],
    "music": ["beat", "sound", "wave", "vibe", "records", "flow", "track", "audio", "fm", "drop", "bass", "mix"],
    "business": ["hub", "inc", "co", "store", "shop", "brand", "group", "trade", "deal", "market", "office", "capital"],
    "auto": ["drive", "speed", "garage", "custom", "track", "power", "racing", "turbo", "boost", "drift", "ride", "auto"],
    "sports": ["fit", "run", "gym", "flex", "sport", "power", "champ", "team", "lift", "league", "box", "active"],
    "it": ["dev", "code", "bot", "lab", "cloud", "stack", "tech", "net", "desk", "core", "host", "sys"],
    "luxury": ["gold", "rich", "prime", "vip", "royal", "elite", "rare", "black", "diamond", "monaco", "grand", "luxe"],
    "blog": ["vibe", "life", "daily", "one", "official", "real", "zone", "feed", "channel", "live", "blog", "space"],
    "memes": ["pepe", "sigma", "gigachad", "chad", "kek", "based", "wojak", "vibe", "stonks", "hype", "boss", "bro"],
    "twitch": ["tv", "live", "stream", "onair", "cast", "play", "room", "club", "gg", "clip", "host", "zone"],
    "art": ["art", "design", "craft", "visual", "space", "frame", "gallery", "draw", "vector", "sketch", "maker", "concept"],
    "food": ["fresh", "food", "kitchen", "cafe", "taste", "craft", "bar", "bake", "cook", "chef", "sweet", "spice"],
    "cities": ["tokyo", "paris", "london", "dubai", "miami", "rome", "nyc", "moscow", "berlin", "vegas", "la", "bali"],
    "space": ["star", "cosmic", "orbit", "solar", "astro", "nova", "luna", "void", "galaxy", "mars", "sky", "nebula"],
    "mythology": ["zeus", "thor", "odin", "ares", "hades", "titan", "hydra", "phoenix", "dragon", "valkyrie", "anubis", "chronos"]
}

CONSONANTS_EASY = "bcdfgklmnprstvwz"
VOWELS_EASY = "aeiouy"

def generate_keyword_custom_username(keyword: str, category: str, use_und: bool = False) -> str:
    keyword = keyword.strip().lower().replace("@", "")
    affixes = AFFIX_DATABASE_20.get(category, AFFIX_DATABASE_20["superheroes"])
    affix = random.choice(affixes)
    prefixes = ["iam", "the", "real", "get", "mr", "dr", "lord", "pro"]
    pattern = random.choice(["kw_affix", "affix_kw", "prefix_kw", "kw_prefix"])
    
    if pattern == "kw_affix":
        return f"{keyword}_{affix}" if use_und else f"{keyword}{affix}"
    elif pattern == "affix_kw":
        return f"{affix}_{keyword}" if use_und else f"{affix}{keyword}"
    elif pattern == "prefix_kw":
        pref = random.choice(prefixes)
        return f"{pref}_{keyword}" if use_und else f"{pref}{keyword}"
    else:
        return f"{keyword}_{affix}" if use_und else f"{keyword}{affix}"

def generate_smart_username(len_mode: str = "5-6", use_num: bool = False, use_und: bool = False, strict_filter: bool = False) -> tuple[str, bool, bool]:
    """Генерирует благозвучные, брендовые никнеймы высокой ценности."""
    r_val = random.random()
    
    # 1. Элитные брендовые связки
    if r_val < 0.45 and not strict_filter:
        root = random.choice(ELITE_ROOTS)
        if random.random() < 0.5:
            res = root + random.choice(["x", "z", "r", "s", "o", "a"])
        else:
            pref = random.choice(PREMIUM_PREFIXES)
            res = pref + root[:3]
    # 2. Фонетическая матрица CVCVC
    else:
        target_len = random.choice([5, 6]) if len_mode == "5-6" else random.choice([7, 8])
        res = ""
        start_cons = random.choice([True, False])
        for i in range(target_len):
            if (i % 2 == 0 and start_cons) or (i % 2 == 1 and not start_cons):
                res += random.choice(CONSONANTS_EASY)
            else:
                res += random.choice(VOWELS_EASY)

    if use_und and len(res) >= 5 and random.random() < 0.3:
        pos = random.randint(2, len(res) - 2)
        res = res[:pos] + "_" + res[pos+1:]

    if use_num and len(res) >= 5 and random.random() < 0.3:
        num = str(random.randint(1, 99))
        res = res[:-len(num)] + num

    return res.lower(), True, ("_" in res)

def calculate_catch_score(username: str, is_free: bool, is_pure: bool = False, has_und: bool = False):
    if not is_free:
        return {"rank": "F", "status": "Занят в Telegram", "color": "#ef4444", "score": 0}
    
    username = username.lower().replace("@", "").strip()
    length = len(username)
    vowels = set("aeiouy")
    has_num = any(char.isdigit() for char in username)
    
    if has_und or has_num or length > 8:
        return {"rank": "A", "status": "Свободен (~1-2 TON)", "color": "#3b82f6", "score": 25}

    if length == 5:
        return {"rank": "SSS+", "status": "🔥 Fragment (~30-90+ TON)", "color": "#29c75f", "score": 95}
    elif length == 6:
        return {"rank": "SS", "status": "💎 Редкий бренд (~10-35 TON)", "color": "#eab308", "score": 75}
    elif length == 7:
        return {"rank": "S", "status": "✨ Красивый актив (~4-10 TON)", "color": "#a855f7", "score": 55}
    
    return {"rank": "A", "status": "Свободен (~1-3 TON)", "color": "#29c75f", "score": 30}

async def check_username_telethon(username: str) -> bool:
    global TELETHON_AVAILABLE
    username = username.replace("@", "").strip().lower()
    if len(username) < 5: 
        return False
    now = time.time()

    if username in CHECK_CACHE:
        cached_result, cached_time = CHECK_CACHE[username]
        if now - cached_time < CACHE_TTL:
            return cached_result

    if not TELETHON_AVAILABLE:
        CHECK_CACHE[username] = (False, now)
        return False

    try:
        coro = telethon_client(CheckUsernameRequest(username=username))
        result = await asyncio.wait_for(coro, timeout=1.2)
        is_free = bool(result is True)
        CHECK_CACHE[username] = (is_free, now)
        return is_free
    except Exception:
        CHECK_CACHE[username] = (False, now)
        return False

TARRIFS = {
    "pro_30": {"seconds": 30 * 86400, "stars": 75, "title": "PRO Доступ (30 дней)", "desc": "100 слотов радара + Турбо-парсер + ∞ Энергия"},
    "pro_60": {"seconds": 60 * 86400, "stars": 120, "title": "PRO Доступ (60 дней)", "desc": "Скидка 20% + Все PRO функции"},
    "pro_90": {"seconds": 90 * 86400, "stars": 160, "title": "PRO Доступ (90 дней)", "desc": "Скидка 30% + Все PRO функции"},
    "pro_forever": {"seconds": -1, "stars": 490, "title": "PRO Навсегда (Lifetime)", "desc": "Вечный доступ ко всем возможностям"}
}

if dp and bot:
    @dp.message(F.text == "/start")
    async def cmd_start(message: types.Message):
        web_app_url = "https://user-bot-production-8a5d.up.railway.app"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Запустить NameHunter PRO", web_app=WebAppInfo(url=web_app_url))]
            ]
        )
        await message.answer(
            "👋 **Добро пожаловать в NameHunter PRO!**\n\n"
            "🎯 Мгновенный поиск редких юзернеймов\n"
            "🪐 3D-майнинг космических тел (10 этапов до Чёрной Дыры)\n"
            "👑 Радар на 100 слотов, Конструктор по 20 категориям и ∞ Энергия",
            reply_markup=kb,
            parse_mode="Markdown"
        )

    @dp.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    @dp.message(F.successful_payment)
    async def process_successful_payment(message: types.Message):
        payload = message.successful_payment.invoice_payload
        user_id = str(message.from_user.id)
        tariff = TARRIFS.get(payload)

        if tariff:
            secs = tariff["seconds"]
            now = int(time.time())
            key_code = generate_secure_pro_key()
            
            async with DB_LOCK:
                keys_db = load_json_file(KEYS_DB_PATH, {})
                keys_db[key_code] = {
                    "bound_user_id": user_id,
                    "seconds": secs,
                    "created_at": now,
                    "activated_status": "used",
                    "activated_at": now
                }
                save_json_atomic_sync(KEYS_DB_PATH, keys_db)

                game_db = load_json_file(GAME_DB_PATH, {})
                user = get_user_profile(game_db, user_id)
                if secs == -1:
                    user["pro_until"] = -1
                else:
                    cur_pro = max(now, user.get("pro_until", 0))
                    user["pro_until"] = cur_pro + secs
                user["rank"] = "👑 PRO Ловец"
                user["pro_warned"] = False
                user["pro_expired_notified"] = False
                save_json_atomic_sync(GAME_DB_PATH, game_db)

            duration_text = "Навсегда" if secs == -1 else f"{secs // 86400} дней"
            await message.answer(
                f"🎉 **Оплата {tariff['stars']} ⭐ принята!**\n\n"
                f"👑 **PRO статус активен:** {duration_text}\n"
                f"🔑 **Ваш персональный ключ:**\n`{key_code}`\n\n"
                f"_Привязан к вашему Telegram ID._",
                parse_mode="Markdown"
            )

async def pro_expiry_worker():
    while True:
        try:
            now = int(time.time())
            db = load_json_file(GAME_DB_PATH, {})
            changed = False

            if db and bot:
                for uid, user in list(db.items()):
                    if not uid.isdigit():
                        continue
                    
                    pro_until = user.get("pro_until", 0)
                    if pro_until == -1 or pro_until == 0:
                        continue
                    
                    diff = pro_until - now
                    should_warn = False
                    if diff > 600 and diff <= 86400 and not user.get("pro_warned", False):
                        should_warn = True
                    elif diff <= 180 and diff > 0 and not user.get("pro_warned", False):
                        should_warn = True

                    if should_warn:
                        user["pro_warned"] = True
                        changed = True
                        time_left_str = f"{int(diff / 3600)} ч" if diff > 3600 else f"{max(1, int(diff / 60))} мин"

                        try:
                            web_app_url = "https://user-bot-production-8a5d.up.railway.app"
                            kb = InlineKeyboardMarkup(
                                inline_keyboard=[
                                    [InlineKeyboardButton(text="⭐ Продлить PRO Доступ", web_app=WebAppInfo(url=web_app_url))]
                                ]
                            )
                            await bot.send_message(
                                chat_id=int(uid),
                                text=(
                                    "⏳ **Внимание! Ваша PRO-подписка скоро истекает!** ⚠️\n\n"
                                    f"До окончания осталось: **{time_left_str}** ⏱️\n\n"
                                    "После завершения отключатся:\n"
                                    "• 🔋 Бесконечная энергия `∞` в 3D-майнинге\n"
                                    "• 🛠️ Конструктор ников по 20 категориям\n"
                                    "• 🎯 Расширенный радар на 100 слотов\n\n"
                                    "👑 Продлите подписку, чтобы не потерять преимущества! ⭐"
                                ),
                                parse_mode="Markdown",
                                reply_markup=kb
                            )
                        except Exception:
                            pass

                    if diff <= 0 and not user.get("pro_expired_notified", False):
                        user["pro_expired_notified"] = True
                        user["rank"] = "Ловец"
                        changed = True
                        try:
                            web_app_url = "https://user-bot-production-8a5d.up.railway.app"
                            kb = InlineKeyboardMarkup(
                                inline_keyboard=[
                                    [InlineKeyboardButton(text="🚀 Восстановить PRO", web_app=WebAppInfo(url=web_app_url))]
                                ]
                            )
                            await bot.send_message(
                                chat_id=int(uid),
                                text=(
                                    "🥺 **Ваша PRO-подписка завершилась!** 🔒\n\n"
                                    "Аккаунт переведён на базовый тариф (3 слота радара, стандартная энергия) 🔋\n\n"
                                    "👑 Оформите подписку заново в любой момент, чтобы вернуть турбо-парсер и суперспособности! ⭐"
                                ),
                                parse_mode="Markdown",
                                reply_markup=kb
                            )
                        except Exception:
                            pass

            if changed:
                save_json_atomic_sync(GAME_DB_PATH, db)

        except Exception:
            pass
        await asyncio.sleep(10)

async def radar_worker():
    while True:
        try:
            db = load_json_file(RADAR_DB_PATH, {})
            if db and bot and TELETHON_AVAILABLE:
                for chat_id, targets in list(db.items()):
                    for username in list(targets):
                        is_free = await check_username_telethon(username)
                        if is_free is True:
                            try:
                                await bot.send_message(
                                    chat_id=int(chat_id),
                                    text=f"🚨 **РАДАР:** Ник `@{username}` освободился!\nЗабирай скорее!",
                                    parse_mode="Markdown"
                                )
                                db[chat_id].remove(username)
                                if not db[chat_id]:
                                    del db[chat_id]
                                save_json_atomic_sync(RADAR_DB_PATH, db)
                            except Exception:
                                pass
                        await asyncio.sleep(2)
        except Exception:
            pass
        await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global TELETHON_AVAILABLE
    try:
        await telethon_client.connect()
        TELETHON_AVAILABLE = await telethon_client.is_user_authorized()
    except Exception:
        TELETHON_AVAILABLE = False
    
    asyncio.create_task(radar_worker())
    asyncio.create_task(pro_expiry_worker())
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))
    
    yield
    try:
        await telethon_client.disconnect()
    except Exception:
        pass

app = FastAPI(title="Username Scanner PRO", lifespan=lifespan)

@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH): 
        return FileResponse(
            INDEX_PATH, 
            media_type="text/html", 
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"}
        )
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})

@app.get("/api/game/state")
async def get_game_state(user_id: str):
    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        now = int(time.time())
        time_diff = now - user["last_seen"]
        
        offline_earned = 0
        offline_seconds = 0
        if time_diff > 60 and user["offline_miner_lvl"] > 0:
            offline_seconds = min(time_diff, 10800)
            rate_per_sec = OFFLINE_RATES.get(user["offline_miner_lvl"], 500) / 3600.0
            offline_earned = int(offline_seconds * rate_per_sec)
            user["offline_pending"] = offline_earned

        user["last_seen"] = now
        save_json_atomic_sync(GAME_DB_PATH, db)
        is_pro, pro_until = is_user_pro(user_id)
        return {
            "status": "ok", 
            "profile": user, 
            "offline_earned": user.get("offline_pending", 0),
            "offline_seconds": offline_seconds,
            "is_pro": is_pro, 
            "pro_until": pro_until,
            "turbo_until": user.get("turbo_until", 0),
            "unlocked_themes": user.get("unlocked_themes", []),
            "max_radar_slots": (100 if is_pro else (3 + user.get("radar_extra_slots", 0))),
            "planet_hp_max": PLANET_HP_TABLE.get(user["planet_stage"], 100)
        }

@app.post("/api/game/collect_offline")
async def collect_offline(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        earned = user.get("offline_pending", 0)
        user["coins"] += earned
        user["offline_pending"] = 0
        save_json_atomic_sync(GAME_DB_PATH, db)
        return {"status": "ok", "coins": user["coins"], "collected": earned}

@app.post("/api/game/sync_tap")
async def sync_tap(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "default_guest")).strip()
    taps = int(data.get("taps", 0))
    damage = int(data.get("damage", 0))
    
    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        is_pro, _ = is_user_pro(user_id)
        
        if taps > 0:
            actual_taps = taps if is_pro else min(taps, user["energy"])
            if actual_taps > 0:
                earned = actual_taps * user["multi_tap"]
                user["coins"] += earned
                if not is_pro:
                    user["energy"] = max(0, user["energy"] - actual_taps)
                
                user["planet_hp"] = max(0, user["planet_hp"] - damage)
                if user["planet_hp"] <= 0:
                    if user["planet_stage"] < 10:
                        user["planet_stage"] += 1
                        user["planet_hp"] = PLANET_HP_TABLE.get(user["planet_stage"], 100)
                        user["coins"] += user["planet_stage"] * 500
                    else:
                        user["planet_hp"] = PLANET_HP_TABLE[10]
                
                user["last_seen"] = int(time.time())
                save_json_atomic_sync(GAME_DB_PATH, db)
        return {
            "status": "ok", 
            "coins": user["coins"], 
            "server_energy": user["energy"], 
            "planet_stage": user["planet_stage"], 
            "planet_hp": user["planet_hp"],
            "planet_hp_max": PLANET_HP_TABLE.get(user["planet_stage"], 100),
            "is_pro": is_pro
        }

@app.post("/api/game/buy")
async def buy_game_item(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "default_guest")).strip()
    item_id = str(data.get("item_id", ""))
    
    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        now = int(time.time())

        # ⚡ СТЕКИНГ ТУРБО-СКОРОСТИ (65 000 МОНЕТ)
        if item_id == "turbo_boost_15":
            if user["coins"] >= 65000:
                user["coins"] -= 65000
                cur_turbo = max(now, user.get("turbo_until", 0))
                user["turbo_until"] = cur_turbo + (15 * 60) # Аккуратное продление времени (+15 мин)
            else: 
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        # 🎯 +1 СЛОТ В РАДАРЕ (35 000 МОНЕТ)
        elif item_id == "radar_slot":
            if user["coins"] >= 35000:
                user["coins"] -= 35000
                user["radar_extra_slots"] += 1
            else: 
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        # 🌌 КАСТОМНАЯ ТЕМА «НЕОНОВЫЙ КВАЗАР» (100 000 МОНЕТ)
        elif item_id == "theme_quasar":
            if "theme_quasar" in user.get("unlocked_themes", []):
                return JSONResponse(status_code=400, content={"error": "already_owned"})
            if user["coins"] >= 100000:
                user["coins"] -= 100000
                if "unlocked_themes" not in user:
                    user["unlocked_themes"] = []
                user["unlocked_themes"].append("theme_quasar")
            else:
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "multi_tap":
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

        user["last_seen"] = now
        save_json_atomic_sync(GAME_DB_PATH, db)
        return {"status": "ok", "profile": user}

@app.post("/api/pro/buy_invoice")
async def create_pro_invoice(request: Request):
    if not bot:
        return JSONResponse(status_code=400, content={"error": "Bot token not configured"})
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    tariff_id = str(data.get("tariff_id", "pro_30"))

    tariff = TARRIFS.get(tariff_id)
    if not tariff or not user_id.isdigit():
        return JSONResponse(status_code=400, content={"error": "Invalid tariff or user_id"})

    try:
        invoice_link = await bot.create_invoice_link(
            title=tariff["title"],
            description=tariff["desc"],
            payload=tariff_id,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=tariff["title"], amount=tariff["stars"])]
        )
        return {"status": "ok", "invoice_link": invoice_link}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/pro/activate_key")
async def activate_pro_key(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    key_code = str(data.get("key", "")).strip().upper()
    now = int(time.time())

    if user_id in FAILED_ATTEMPTS:
        fails, lock_time = FAILED_ATTEMPTS[user_id]
        if fails >= 5:
            if now - lock_time < 300:
                wait_sec = 300 - (now - lock_time)
                return JSONResponse(status_code=429, content={"error": f"Слишком много попыток. Подождите {wait_sec} сек."})
            else:
                FAILED_ATTEMPTS[user_id] = [0, 0]

    async with DB_LOCK:
        keys_db = load_json_file(KEYS_DB_PATH, {})
        if key_code not in keys_db or keys_db[key_code].get("activated_status") == "used":
            cur_fails = FAILED_ATTEMPTS.get(user_id, [0, 0])[0] + 1
            FAILED_ATTEMPTS[user_id] = [cur_fails, now]
            return JSONResponse(status_code=400, content={"error": "Ключ не существует или уже активирован!"})
        
        k_data = keys_db[key_code]
        if k_data.get("bound_user_id") and k_data["bound_user_id"] != user_id:
            return JSONResponse(status_code=403, content={"error": "Этот ключ привязан к другому Telegram ID!"})

        secs = k_data.get("seconds", 30 * 86400)
        k_data["bound_user_id"] = user_id
        k_data["activated_status"] = "used"
        k_data["activated_at"] = now
        save_json_atomic_sync(KEYS_DB_PATH, keys_db)

        game_db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(game_db, user_id)
        if secs == -1:
            user["pro_until"] = -1
        else:
            cur_pro = max(now, user.get("pro_until", 0))
            user["pro_until"] = cur_pro + secs
        user["rank"] = "👑 PRO Ловец"
        user["pro_warned"] = False
        user["pro_expired_notified"] = False
        save_json_atomic_sync(GAME_DB_PATH, game_db)

        if user_id in FAILED_ATTEMPTS:
            del FAILED_ATTEMPTS[user_id]

        return {"status": "ok", "pro_until": user["pro_until"]}

@app.get("/api/generate")
async def generate_username(
    request: Request, 
    platform: str = Query("telegram"), 
    use_filter: bool = Query(False), 
    len_mode: str = Query("5-6"), 
    use_num: bool = Query(False), 
    use_und: bool = Query(False), 
    custom_keyword: str = Query(""),
    custom_category: str = Query("superheroes"),
    finder_name: str = Query("Аноним"), 
    finder_id: str = Query("0") 
):
    is_pro, _ = is_user_pro(finder_id)
    generated = ""
    is_free = False
    eval_data = {}

    for _ in range(12):
        if custom_keyword.strip():
            if not is_pro:
                return JSONResponse(status_code=403, content={"error": "pro_required", "msg": "Конструктор по 20 категориям доступен только в PRO!"})
            generated = generate_keyword_custom_username(custom_keyword, custom_category, use_und)
            is_pure = True
            has_und = ("_" in generated)
        else:
            generated, is_pure, has_und = generate_smart_username(len_mode, use_num, use_und, strict_filter=use_filter)

        is_free = await check_username_telethon(generated)
        eval_data = calculate_catch_score(generated, is_free, is_pure, has_und)
        if is_free:
            break

    if is_free and eval_data.get("score", 0) >= 40:
        lb = load_json_file(LEADERBOARD_PATH, [])
        if not any(item["username"].lower() == generated.lower() for item in lb):
            lb.append({
                "username": generated,
                "rank": eval_data["rank"],
                "price": eval_data["status"],
                "score": eval_data["score"],
                "color": eval_data["color"],
                "finder_name": finder_name or "Аноним",
                "finder_id": finder_id or "0",
                "timestamp": int(time.time())
            })
            lb = sorted(lb, key=lambda x: x.get("score", 0), reverse=True)[:1000]
            save_json_atomic_sync(LEADERBOARD_PATH, lb)

    return {
        "status": "success",
        "generated_username": generated,
        "platform": platform,
        "is_free": is_free,
        "evaluation": eval_data
    }

@app.get("/api/radar/add")
async def radar_add(chat_id: str, username: str):
    chat_id = str(chat_id).strip()
    is_pro, _ = is_user_pro(chat_id)

    db = load_json_file(RADAR_DB_PATH, {})
    user_targets = db.get(chat_id, [])
    game_db = load_json_file(GAME_DB_PATH, {})
    profile = get_user_profile(game_db, chat_id)
    max_slots = 100 if is_pro else (3 + profile.get("radar_extra_slots", 0))

    if len(user_targets) >= max_slots:
        return JSONResponse(status_code=403, content={"error": "limit_reached", "msg": f"Достигнут лимит ({max_slots} слотов). Оформите PRO или купите слот в магазине!"})

    if chat_id not in db: 
        db[chat_id] = []
    username = username.replace("@", "").strip().lower()
    if username and username not in db[chat_id]:
        db[chat_id].append(username)
        save_json_atomic_sync(RADAR_DB_PATH, db)
    return {"status": "ok", "targets": db[chat_id]}

@app.get("/api/radar/list")
async def radar_list(chat_id: str):
    return {"targets": load_json_file(RADAR_DB_PATH, {}).get(str(chat_id).strip(), [])}

@app.get("/api/radar/remove")
async def radar_remove(chat_id: str, username: str):
    db = load_json_file(RADAR_DB_PATH, {})
    chat_id = str(chat_id).strip()
    username = username.replace("@", "").strip().lower()
    if chat_id in db and username in db[chat_id]:
        db[chat_id].remove(username)
        if not db[chat_id]:
            del db[chat_id]
        save_json_atomic_sync(RADAR_DB_PATH, db)
    return {"status": "ok", "targets": db.get(chat_id, [])}

@app.get("/api/leaderboard")
async def get_leaderboard(period: str = Query("all")):
    lb = load_json_file(LEADERBOARD_PATH, [])
    return {"status": "ok", "leaderboard": lb[:1000]}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
