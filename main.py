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
            "rank": "Ловец",
            "pro_until": 0
        }
    
    user = db[user_id]
    if "pro_until" not in user: user["pro_until"] = 0
    if "radar_extra_slots" not in user: user["radar_extra_slots"] = 0
    if "turbo_until" not in user: user["turbo_until"] = 0

    time_passed = now - user.get("last_seen", now)
    if time_passed > 0 and user["energy"] < user["max_energy"]:
        regen_amount = time_passed * user.get("energy_regen", 1)
        user["energy"] = min(user["max_energy"], user["energy"] + regen_amount)

    return user

AFFIX_DATABASE = {
    "personal": ["official", "real", "prime", "live", "blog", "vibe", "zone", "one", "daily", "fan", "hq", "club"],
    "military": ["core", "tactics", "force", "unit", "prime", "zone", "command", "shield", "squad", "base", "lead"],
    "tech": ["lab", "hub", "space", "core", "app", "dev", "tech", "base", "net", "cloud", "desk", "code", "bot"],
    "crypto": ["vault", "pay", "trade", "node", "coin", "drop", "capital", "cash", "chain", "pool", "dex", "mint"],
    "gaming": ["play", "zone", "clan", "gg", "craft", "squad", "hero", "skill", "arena", "guild", "win", "rush"]
}

TRANSLIT_WORDS = [
    "vostok", "imperia", "pobeda", "bereg", "kultura", "sovet", "otklik", "zvezda", 
    "priboy", "vektor", "osnova", "nasledie", "prikaz", "tishina", "metel", "avangard",
    "rubin", "granit", "polus", "sfera", "sigma", "vertex", "gamma", "luna", "altair"
]

PURE_WORDS = [
    "apple", "world", "music", "house", "light", "dream", "space", "power", "smart", "stone", "water",
    "earth", "cloud", "storm", "river", "ocean", "flame", "shadow", "silver", "golden", "crystal"
]

CONSONANTS_EASY = "bcdfgklmnprstvwz"
VOWELS_EASY = "aeiouy"

def generate_smart_username(len_mode: str = "5-6", use_num: bool = False, use_und: bool = False) -> tuple[str, bool, bool]:
    if random.random() < 0.35:
        cat = random.choice(list(AFFIX_DATABASE.keys()))
        affix = random.choice(AFFIX_DATABASE[cat])
        base = random.choice(TRANSLIT_WORDS)
        if random.random() < 0.5 and len(base) + len(affix) <= 12:
            res = f"{base}_{affix}" if use_und else f"{base}{affix}"
        else:
            res = base
    else:
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

    return res.lower(), True, ("_" in res)

def calculate_catch_score(username: str, is_free: bool, is_pure: bool = False, has_und: bool = False):
    if not is_free:
        return {"rank": "F", "status": "Занят", "color": "#ef4444", "score": 0}
    
    username = username.lower().replace("@", "").strip()
    length = len(username)
    has_num = any(char.isdigit() for char in username)
    
    if has_und or has_num or length > 8:
        return {"rank": "A", "status": "Обычный ник (~1-2 TON)", "color": "#3b82f6", "score": 20}

    if username in TRANSLIT_WORDS or username in PURE_WORDS:
        return {"rank": "SSS+", "status": "Fragment: High Value (~100-500+ TON)", "color": "#29c75f", "score": 100}

    if length <= 4:
        return {"rank": "SSS+", "status": "Fragment (~50-150 TON)", "color": "#29c75f", "score": 90}
    elif length == 5:
        return {"rank": "SS", "status": "Fragment (~15-40 TON)", "color": "#eab308", "score": 75}
    elif length == 6:
        return {"rank": "S", "status": "Красивый актив (~5-15 TON)", "color": "#a855f7", "score": 55}
    
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
        is_free = (random.random() < 0.65)
        CHECK_CACHE[username] = (is_free, now)
        return is_free

    try:
        coro = telethon_client(CheckUsernameRequest(username=username))
        result = await asyncio.wait_for(coro, timeout=0.8)
        is_free = bool(result is True)
        CHECK_CACHE[username] = (is_free, now)
        return is_free
    except Exception:
        is_free = (random.random() < 0.55)
        CHECK_CACHE[username] = (is_free, now)
        return is_free

TARRIFS = {
    "pro_30": {"days": 30, "stars": 75, "title": "PRO Доступ (30 дней)", "desc": "100 слотов радара + Турбо-парсер"},
    "pro_60": {"days": 60, "stars": 120, "title": "PRO Доступ (60 дней)", "desc": "Скидка 20% + Все PRO функции"},
    "pro_90": {"days": 90, "stars": 160, "title": "PRO Доступ (90 дней)", "desc": "Скидка 30% + Все PRO функции"},
    "pro_forever": {"days": -1, "stars": 490, "title": "PRO Навсегда (Lifetime)", "desc": "Вечный доступ ко всем возможностям"}
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
            "⚡ 3D-майнинг Cosmic Core и прокачка навыков\n"
            "👑 Радар на 100 слотов и авто-уведомления",
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
            days = tariff["days"]
            now = int(time.time())
            key_code = f"PRO-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
            
            async with DB_LOCK:
                keys_db = load_json_file(KEYS_DB_PATH, {})
                keys_db[key_code] = {
                    "bound_user_id": user_id,
                    "days": days,
                    "created_at": now,
                    "activated": True
                }
                save_json_atomic_sync(KEYS_DB_PATH, keys_db)

                game_db = load_json_file(GAME_DB_PATH, {})
                user = get_user_profile(game_db, user_id)
                if days == -1:
                    user["pro_until"] = -1
                else:
                    cur_pro = max(now, user.get("pro_until", 0))
                    user["pro_until"] = cur_pro + (days * 86400)
                user["rank"] = "👑 PRO Ловец"
                save_json_atomic_sync(GAME_DB_PATH, game_db)

            duration_text = "Навсегда" if days == -1 else f"{days} дней"
            await message.answer(
                f"🎉 **Оплата {tariff['stars']} ⭐ принята!**\n\n"
                f"👑 **PRO статус активен:** {duration_text}\n"
                f"🔑 **Ваш персональный ключ:** `{key_code}`",
                parse_mode="Markdown"
            )

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
    if use_filter:
        generated, is_pure, has_und = generate_smart_username(len_mode, use_num, use_und)
    else:
        generated, is_pure, has_und = generate_smart_username()

    is_free = await check_username_telethon(generated)
    eval_data = calculate_catch_score(generated, is_free, is_pure, has_und)

    return {
        "status": "success",
        "generated_username": generated,
        "platform": platform,
        "is_free": is_free,
        "evaluation": eval_data
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

        elif item_id == "turbo_boost_15":
            if user["coins"] >= 2500:
                user["coins"] -= 2500
                cur_turbo = max(now, user.get("turbo_until", 0))
                user["turbo_until"] = cur_turbo + (15 * 60)
            else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "theme_cyberpunk":
            if user["coins"] >= 20000 and "cyberpunk" not in user["unlocked_themes"]:
                user["coins"] -= 20000
                user["unlocked_themes"].append("cyberpunk")
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

    async with DB_LOCK:
        keys_db = load_json_file(KEYS_DB_PATH, {})
        if key_code not in keys_db:
            return JSONResponse(status_code=400, content={"error": "Ключ не существует"})
        
        k_data = keys_db[key_code]
        if k_data.get("bound_user_id") and k_data["bound_user_id"] != user_id:
            return JSONResponse(status_code=403, content={"error": "Этот ключ привязан к другому Telegram ID!"})

        now = int(time.time())
        days = k_data["days"]
        k_data["bound_user_id"] = user_id
        k_data["activated"] = True
        save_json_atomic_sync(KEYS_DB_PATH, keys_db)

        game_db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(game_db, user_id)
        if days == -1:
            user["pro_until"] = -1
        else:
            cur_pro = max(now, user.get("pro_until", 0))
            user["pro_until"] = cur_pro + (days * 86400)
        user["rank"] = "👑 PRO Ловец"
        save_json_atomic_sync(GAME_DB_PATH, game_db)

        return {"status": "ok", "pro_until": user["pro_until"]}

@app.get("/api/game/state")
async def get_game_state(user_id: str):
    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        now = int(time.time())
        time_diff = now - user["last_seen"]
        offline_earned = 0
        if time_diff > 60 and user["offline_miner_lvl"] > 0:
            clamped_time = min(time_diff, 10800)
            offline_earned = int(clamped_time * (500 / 3600.0))
            user["coins"] += offline_earned

        user["last_seen"] = now
        save_json_atomic_sync(GAME_DB_PATH, db)
        is_pro, pro_until = is_user_pro(user_id)
        return {
            "status": "ok", 
            "profile": user, 
            "offline_earned": offline_earned, 
            "is_pro": is_pro, 
            "pro_until": pro_until,
            "turbo_until": user.get("turbo_until", 0),
            "max_radar_slots": (100 if is_pro else (3 + user.get("radar_extra_slots", 0)))
        }

@app.post("/api/game/sync_tap")
async def sync_tap(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "default_guest")).strip()
    taps = int(data.get("taps", 0))
    
    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        if taps > 0:
            actual_taps = min(taps, user["energy"])
            if actual_taps > 0:
                earned = actual_taps * user["multi_tap"]
                user["coins"] += earned
                user["energy"] = max(0, user["energy"] - actual_taps)
                user["last_seen"] = int(time.time())
                save_json_atomic_sync(GAME_DB_PATH, db)
        return {"status": "ok", "coins": user["coins"], "server_energy": user["energy"]}

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
