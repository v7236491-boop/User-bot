import os
import random
import asyncio
import time
import json
import secrets
import aiohttp
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import CommandStart, CommandObject
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import CheckUsernameRequest
from telethon.errors import FloodWaitError
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
RADAR_DB_PATH = os.path.join(BASE_DIR, "radar_db.json")
LEADERBOARD_PATH = os.path.join(BASE_DIR, "leaderboard_db.json")
GAME_DB_PATH = os.path.join(BASE_DIR, "game_data.json")
KEYS_DB_PATH = os.path.join(BASE_DIR, "pro_keys.json")
PROMOS_DB_PATH = os.path.join(BASE_DIR, "promocodes_db.json")
GIFTS_DB_PATH = os.path.join(BASE_DIR, "gifts_settings.json")
REFERRALS_DB_PATH = os.path.join(BASE_DIR, "referrals_db.json")

DB_LOCK = asyncio.Lock()
CHECK_CACHE = {}
CACHE_TTL = 1800
TELETHON_AVAILABLE = False
FAILED_ATTEMPTS = {}

FREE_DAILY_LIMIT = 100

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "38162572"))
API_HASH = os.getenv("API_HASH", "71b8ecb44bddc1ae0a802f4a0f6628ba")
SESSION_STRING = os.getenv("TELEGRAM_SESSION")
TONAPI_KEY = os.getenv("TONAPI_KEY", "AE2FSP66DNLCCBQAAAALQQ6U7TIDRZ2SZNZ46HCSCMJNFQHALEBM4Z4C4UEDMCJYBUG55CI")

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

def generate_secure_code(prefix: str) -> str:
    p1 = "".join(secrets.choice(KEY_CHARSET) for _ in range(4))
    p2 = "".join(secrets.choice(KEY_CHARSET) for _ in range(4))
    p3 = "".join(secrets.choice(KEY_CHARSET) for _ in range(4))
    return f"{prefix}-{p1}-{p2}-{p3}"

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

PREGENERATED_KEYS_1DAY = [
    "PRO-1D01-K9X2-M4P7-R8W3", "PRO-1D02-J7N3-Q5T8-V2Y6", "PRO-1D03-B4H9-C6M2-L8Z5",
    "PRO-1D04-F3S8-X9D2-G7K4", "PRO-1D05-T6W1-Y4L7-N9C3", "PRO-1D06-H8Q5-V2B9-Z4M7",
    "PRO-1D07-C3J7-P9X4-R2T8", "PRO-1D08-M6L2-S8F5-W3Y9", "PRO-1D09-N4D7-K2Z8-G9H3",
    "PRO-1D10-X7T3-B5V9-Q8C4"
]

PREGENERATED_KEYS_1MONTH = [
    "PRO-30D1-L8N4-K2X7-P9R3", "PRO-30D2-Q5M9-T3V8-Y6C2", "PRO-30D3-Z7B2-W4H9-F8S5",
    "PRO-30D4-G9K3-D6L2-X4N8", "PRO-30D5-C2Y7-R8P4-M3T9", "PRO-30D6-V6S3-H9Z5-B2W8",
    "PRO-30D7-N8F4-J3X9-Q7L2", "PRO-30D8-T4C8-M2K7-Y9D3", "PRO-30D9-X6P2-V8R5-H3S9",
    "PRO-3010-W9L4-Z7N3-G5C8", "PRO-3011-K3T8-B9Y2-M4F7", "PRO-3012-P7X5-Q2S9-R6H3",
    "PRO-3013-D4N8-L6W3-Z9K2", "PRO-3014-H2C7-T9M4-Y3V8", "PRO-3015-S8G5-X3L9-F7P2",
    "PRO-3016-B6R2-N8K4-C9D7", "PRO-3017-M9T3-Z4S8-W2Y6", "PRO-3018-Y7F5-H2P9-Q8X3",
    "PRO-3019-L3K8-C6N2-V9M7", "PRO-3020-R9Z4-T7W3-S5D8", "PRO-3021-X2M7-G9H4-K3C8",
    "PRO-3022-P8D5-F2L9-Y7N3", "PRO-3023-W4S9-Q6T2-Z8B5", "PRO-3024-N7Y3-K9C8-M2R4",
    "PRO-3025-C5H8-V3X7-P9L2", "PRO-3026-T9K2-D4N8-S6F3", "PRO-3027-Z3R7-M8W5-Y2Q9",
    "PRO-3028-F8P4-X6C2-H9T5", "PRO-3029-L2S9-B7K3-W4M8", "PRO-3030-Q6N3-Y8Z5-R2D7",
    "PRO-3031-G4T8-C9L2-M7X3", "PRO-3032-V9F2-H4S7-P8W5", "PRO-3033-K7M5-Z2N9-T6B3",
    "PRO-3034-X3D8-R7Y4-Q9C2", "PRO-3035-S5W2-L9P6-H3K8", "PRO-3036-N2C9-F8T4-Z7M3",
    "PRO-3037-Y6L3-M4X8-D9S2", "PRO-3038-P9Z7-W2R5-C8F4", "PRO-3039-B4H2-T6K9-Y3N7",
    "PRO-3040-M8S6-Q3C7-L9X2", "PRO-3041-R3F9-Z8D4-W7P5", "PRO-3042-C7T2-K9M5-H2Y8",
    "PRO-3043-X9W4-S3L8-B6N2", "PRO-3044-T2P7-F9Z3-M8K5", "PRO-3045-L6D3-Y7R9-C2X8",
    "PRO-3046-H8K5-N4T2-W9S7", "PRO-3047-Q2Z8-M6F4-P3C9", "PRO-3048-W7N3-D9Y5-R4L2",
    "PRO-3049-F5X9-S2K7-T8M3", "PRO-3050-Z4C2-P8H6-Y9W5"
]

PREGENERATED_KEYS_LIFETIME = [
    "PRO-LIFE-X9Z2-M4K7-R8W3", "PRO-LIFE-V7N3-Q5T8-Y2C6", "PRO-LIFE-B4H9-C6M2-L8Z5",
    "PRO-LIFE-F3S8-X9D2-G7K4", "PRO-LIFE-T6W1-Y4L7-N9C3", "PRO-LIFE-H8Q5-V2B9-Z4M7",
    "PRO-LIFE-C3J7-P9X4-R2T8", "PRO-LIFE-M6L2-S8F5-W3Y9", "PRO-LIFE-N4D7-K2Z8-G9H3",
    "PRO-LIFE-9X7K-4MRW-8N2T-H5VQ"
]

def init_master_keys():
    keys_db = load_json_file(KEYS_DB_PATH, {})
    now = int(time.time())

    for k in PREGENERATED_KEYS_1DAY:
        if k not in keys_db:
            keys_db[k] = {"bound_user_id": None, "seconds": 86400, "created_at": now, "activated_status": "unused"}

    for k in PREGENERATED_KEYS_1MONTH:
        if k not in keys_db:
            keys_db[k] = {"bound_user_id": None, "seconds": 30 * 86400, "created_at": now, "activated_status": "unused"}

    for k in PREGENERATED_KEYS_LIFETIME:
        if k not in keys_db:
            keys_db[k] = {"bound_user_id": None, "seconds": -1, "created_at": now, "activated_status": "unused"}

    save_json_atomic_sync(KEYS_DB_PATH, keys_db)

init_master_keys()

def init_master_promos():
    promos = load_json_file(PROMOS_DB_PATH, {})
    now = int(time.time())
    
    current_10k = [k for k, v in promos.items() if v.get("coins") == 10000]
    while len(current_10k) < 50:
        code = generate_secure_code("COIN10K")
        if code not in promos:
            promos[code] = {"coins": 10000, "created_at": now, "used_by": None, "used_at": 0}
            current_10k.append(code)

    current_100k = [k for k, v in promos.items() if v.get("coins") == 100000]
    while len(current_100k) < 300:
        code = generate_secure_code("COIN100K")
        if code not in promos:
            promos[code] = {"coins": 100000, "created_at": now, "used_by": None, "used_at": 0}
            current_100k.append(code)

    current_10m = [k for k, v in promos.items() if v.get("coins") == 10000000]
    while len(current_10m) < 10:
        code = generate_secure_code("COIN10M")
        if code not in promos:
            promos[code] = {"coins": 10000000, "created_at": now, "used_by": None, "used_at": 0}
            current_10m.append(code)

    save_json_atomic_sync(PROMOS_DB_PATH, promos)

init_master_promos()

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

def get_current_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")

def get_user_profile(db: dict, user_id: str) -> dict:
    now = int(time.time())
    user_id = str(user_id).strip()
    today_str = get_current_date_str()
    
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
            "pro_expired_notified": True,
            "daily_gens_count": 0,
            "daily_gens_date": today_str,
            "gens_total_count": 0,
            "referred_by": None,
            "referral_reward_claimed": False,
            "referrals_count": 0,
            "last_free_case_time": 0,
            "cases_opened_total": 0,
            "client_history": [],
            "client_achievements": [],
            "custom_theme_style": "",
            "custom_fog_rgb": "41, 199, 95",
            "custom_filter_settings": {}
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
    if "daily_gens_count" not in user: user["daily_gens_count"] = 0
    if "daily_gens_date" not in user: user["daily_gens_date"] = today_str
    if "gens_total_count" not in user: user["gens_total_count"] = 0
    if "referred_by" not in user: user["referred_by"] = None
    if "referral_reward_claimed" not in user: user["referral_reward_claimed"] = False
    if "referrals_count" not in user: user["referrals_count"] = 0
    if "last_free_case_time" not in user: user["last_free_case_time"] = 0
    if "cases_opened_total" not in user: user["cases_opened_total"] = 0
    if "client_history" not in user: user["client_history"] = []
    if "client_achievements" not in user: user["client_achievements"] = []
    if "custom_theme_style" not in user: user["custom_theme_style"] = ""
    if "custom_fog_rgb" not in user: user["custom_fog_rgb"] = "41, 199, 95"
    if "custom_filter_settings" not in user: user["custom_filter_settings"] = {}

    if user.get("daily_gens_date") != today_str:
        user["daily_gens_count"] = 0
        user["daily_gens_date"] = today_str

    time_passed = now - user.get("last_seen", now)
    if time_passed > 0 and user["energy"] < user["max_energy"]:
        regen_amount = time_passed * user.get("energy_regen", 1)
        user["energy"] = min(user["max_energy"], user["energy"] + regen_amount)

    return user

BASE_GIFT_TYPES = [
    {"base_id": "pepe", "name": "Plush Pepe", "icon": "🐸", "base_price": 14.5, "slug": "plush-pepe"},
    {"base_id": "cap", "name": "Durov's Cap", "icon": "🧢", "base_price": 24.0, "slug": "durovs-cap"},
    {"base_id": "potion", "name": "Magic Potion", "icon": "🧪", "base_price": 8.2, "slug": "magic-potion"},
    {"base_id": "star", "name": "Golden Star", "icon": "⭐", "base_price": 4.5, "slug": "golden-star"},
    {"base_id": "ring", "name": "Diamond Ring", "icon": "💍", "base_price": 35.0, "slug": "diamond-ring"},
    {"base_id": "rocket", "name": "Cosmic Rocket", "icon": "🚀", "base_price": 18.0, "slug": "cosmic-rocket"},
    {"base_id": "cake", "name": "Party Cake", "icon": "🎂", "base_price": 3.2, "slug": "party-cake"},
    {"base_id": "heart", "name": "Cyber Heart", "icon": "💖", "base_price": 6.8, "slug": "cyber-heart"},
    {"base_id": "snoop", "name": "Snoop Lowrider", "icon": "🏎️", "base_price": 65.0, "slug": "snoop-lowrider"},
    {"base_id": "flower", "name": "Sun Flower", "icon": "🌻", "base_price": 12.0, "slug": "sun-flower"},
    {"base_id": "duck", "name": "Lucky Duck", "icon": "🦆", "base_price": 7.5, "slug": "lucky-duck"},
    {"base_id": "crown", "name": "Royal Crown", "icon": "👑", "base_price": 42.0, "slug": "royal-crown"},
    {"base_id": "rose", "name": "Eternal Rose", "icon": "🌹", "base_price": 5.0, "slug": "eternal-rose"},
    {"base_id": "gem", "name": "Crystal Gem", "icon": "💎", "base_price": 28.0, "slug": "crystal-gem"},
    {"base_id": "helmet", "name": "Astro Helmet", "icon": "👨‍🚀", "base_price": 21.0, "slug": "astro-helmet"},
    {"base_id": "wine", "name": "Vintage Wine", "icon": "🍾", "base_price": 9.5, "slug": "vintage-wine"},
    {"base_id": "carpet", "name": "Magic Carpet", "icon": "🧞", "base_price": 33.0, "slug": "magic-carpet"},
    {"base_id": "trophy", "name": "Cup of Fame", "icon": "🏆", "base_price": 50.0, "slug": "cup-of-fame"},
    {"base_id": "skull", "name": "Cyber Skull", "icon": "💀", "base_price": 15.0, "slug": "cyber-skull"},
    {"base_id": "ghost", "name": "Friendly Ghost", "icon": "👻", "base_price": 11.5, "slug": "friendly-ghost"}
]

GIFTS_CATALOG = []
for i in range(1, 1001):
    base = BASE_GIFT_TYPES[(i - 1) % len(BASE_GIFT_TYPES)]
    edition_num = 1000 + i * 7
    multiplier = 0.85 + ((i * 17) % 70) / 100.0
    price = round(base["base_price"] * multiplier, 1)
    GIFTS_CATALOG.append({
        "id": f"{base['base_id']}_{i}",
        "name": f"{base['name']} #{edition_num}",
        "icon": base["icon"],
        "floor_ton": price,
        "slug": base["slug"],
        "num": edition_num
    })

SEEN_NFT_LISTINGS = set()

async def gifts_arbitrage_worker():
    while True:
        try:
            gifts_settings = load_json_file(GIFTS_DB_PATH, {})
            if gifts_settings and bot:
                for _ in range(3):
                    gift = random.choice(GIFTS_CATALOG)
                    discount = random.choice([25, 30, 35, 40, 50])
                    floor = gift["floor_ton"]
                    deal_price = round(floor * (1 - discount / 100.0), 1)
                    lot_id = f"{gift['id']}_{deal_price}_{int(time.time() // 120)}"

                    if lot_id not in SEEN_NFT_LISTINGS:
                        SEEN_NFT_LISTINGS.add(lot_id)
                        direct_buy_url = f"https://fragment.com/gifts?query={gift['slug']}"

                        for user_id, u_cfg in list(gifts_settings.items()):
                            if not u_cfg.get("active", False):
                                continue
                            
                            is_pro, _ = is_user_pro(user_id)
                            if not is_pro:
                                continue

                            min_margin = u_cfg.get("margin", 30)
                            max_budget = u_cfg.get("max_budget", 1000)
                            selected_gifts = u_cfg.get("gifts", [])

                            if discount >= min_margin and deal_price <= max_budget:
                                if not selected_gifts or gift["id"] in selected_gifts:
                                    try:
                                        kb = InlineKeyboardMarkup(
                                            inline_keyboard=[
                                                [InlineKeyboardButton(text=f"💎 Купить за {deal_price} TON на Fragment", url=direct_buy_url)]
                                            ]
                                        )
                                        await bot.send_message(
                                            chat_id=int(user_id),
                                            text=(
                                                f"🚨 **FRAGMENT СНАЙПЕР: СКИДКА {discount}%!** 🎁\n\n"
                                                f"{gift['icon']} **Подарок:** {gift['name']}\n"
                                                f"💰 **Цена со скидкой:** `{deal_price} TON` *(Флор: {floor} TON)*\n"
                                                f"📈 **Чистая выгода:** `+{round(floor - deal_price, 1)} TON`\n\n"
                                                f"⚡ _Прямая ссылка для моментального выкупа:_"
                                            ),
                                            parse_mode="Markdown",
                                            reply_markup=kb
                                        )
                                    except Exception:
                                        pass
                await asyncio.sleep(3)
        except Exception:
            pass
        await asyncio.sleep(4)

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
                                    "• 🎁 Снайпер скидок на Telegram Подарки\n"
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
                                    "Аккаунт переведён на базовый тариф (3 слота радара, лимит 100 поисков в день) 🔋\n\n"
                                    "👑 Оформите подписку заново в любой момент, чтобы вернуть все суперспособности! ⭐"
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

PREMIUM_PREFIXES = ["neo", "vox", "lux", "zen", "vex", "arc", "sol", "dex", "sky", "ray", "val", "nox"]
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
    r_val = random.random()
    if r_val < 0.45 and not strict_filter:
        root = random.choice(ELITE_ROOTS)
        if random.random() < 0.5:
            res = root + random.choice(["x", "z", "r", "s", "o", "a"])
        else:
            pref = random.choice(PREMIUM_PREFIXES)
            res = pref + root[:3]
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

    if TELETHON_AVAILABLE:
        try:
            coro = telethon_client(CheckUsernameRequest(username=username))
            result = await asyncio.wait_for(coro, timeout=1.5)
            is_free = bool(result is True)
            CHECK_CACHE[username] = (is_free, now)
            return is_free
        except FloodWaitError:
            pass
        except Exception:
            pass

    try:
        url = f"https://t.me/{username}"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                text = await resp.text()
                if '<div class="tgme_page_title' not in text and '<a class="tgme_action_button_new' not in text:
                    CHECK_CACHE[username] = (True, now)
                    return True
                CHECK_CACHE[username] = (False, now)
                return False
    except Exception:
        return False

# ВСЕ ТАРИФЫ СО СКИДКАМИ + КЕЙСЫ STARS
TARRIFS = {
    "pro_30": {"seconds": 30 * 86400, "stars": 75, "title": "PRO Доступ (30 дней)", "desc": "100 слотов радара + Снайпер Подарков + ∞ Энергия"},
    "pro_60": {"seconds": 60 * 86400, "stars": 120, "title": "PRO Доступ (60 дней)", "desc": "Скидка 20% + Все PRO функции"},
    "pro_90": {"seconds": 90 * 86400, "stars": 160, "title": "PRO Доступ (90 дней)", "desc": "Скидка 30% + Все PRO функции"},
    "pro_forever": {"seconds": -1, "stars": 490, "title": "PRO Навсегда (Lifetime)", "desc": "Вечный доступ ко всем возможностям"},
    "case_elite": {"seconds": 0, "stars": 10, "title": "Элитный Кейс", "desc": "15-25k монет, PRO 3-7 дней, слоты радара"},
    "case_quantum": {"seconds": 0, "stars": 25, "title": "Квантовый Кейс", "desc": "30-50k монет, PRO 7-30 дней, скин Квантум"}
}

if dp and bot:
    @dp.message(CommandStart())
    async def cmd_start(message: types.Message, command: CommandObject):
        user_id = str(message.from_user.id)
        ref_referrer = None

        if command.args and command.args.startswith("ref_"):
            potential_referrer = command.args.replace("ref_", "").strip()
            if potential_referrer.isdigit() and potential_referrer != user_id:
                ref_referrer = potential_referrer

        async with DB_LOCK:
            game_db = load_json_file(GAME_DB_PATH, {})
            user = get_user_profile(game_db, user_id)
            
            if ref_referrer and not user.get("referred_by") and user.get("gens_total_count", 0) == 0:
                user["referred_by"] = ref_referrer
                ref_db = load_json_file(REFERRALS_DB_PATH, {})
                if ref_referrer not in ref_db:
                    ref_db[ref_referrer] = []
                if user_id not in ref_db[ref_referrer]:
                    ref_db[ref_referrer].append(user_id)
                save_json_atomic_sync(REFERRALS_DB_PATH, ref_db)
                save_json_atomic_sync(GAME_DB_PATH, game_db)

        web_app_url = "https://user-bot-production-8a5d.up.railway.app"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🚀 Запустить NameHunter PRO", web_app=WebAppInfo(url=web_app_url))]
            ]
        )
        await message.answer(
            "👋 **Добро пожаловать в NameHunter PRO!**\n\n"
            "🎯 Мгновенный поиск редких юзернеймов\n"
            "🎁 Снайпер скидок на Telegram Подарки (Fragment)\n"
            "🎰 Квантовая рулетка кейсов с гарантией наград\n"
            "🪐 3D-майнинг космических тел (10 этапов до Чёрной Дыры)\n"
            "👥 Приглашай друзей и получай **+1 день PRO** за каждого!",
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

        if tariff and tariff["seconds"] != 0:
            secs = tariff["seconds"]
            now = int(time.time())
            key_code = generate_secure_code("PRO")
            
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
                
                # 🛡️ Сохранение Lifetime и суммирование сроков
                if user.get("pro_until") != -1:
                    if secs == -1:
                        user["pro_until"] = -1
                    else:
                        cur_pro = max(now, user.get("pro_until", 0))
                        user["pro_until"] = cur_pro + secs
                
                user["rank"] = "👑 PRO Ловец"
                user["pro_warned"] = False
                user["pro_expired_notified"] = False
                save_json_atomic_sync(GAME_DB_PATH, game_db)

            duration_text = "Навсегда (Lifetime) 🌌" if secs == -1 else f"{secs // 86400} дней 📅"
            web_app_url = "https://user-bot-production-8a5d.up.railway.app"
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🚀 Открыть NameHunter PRO", web_app=WebAppInfo(url=web_app_url))]
                ]
            )

            await message.answer(
                f"🎉 **СПАСИБО ЗА ПОКУПКУ PRO ПОДПИСКИ!** 👑\n\n"
                f"🌟 **Ваш статус:** АКТИВЕН\n"
                f"⏳ **Срок действия:** {duration_text}\n\n"
                f"🔑 **Ваш персональный ключ:**\n"
                f"`{key_code}`\n\n"
                f"_(Нажмите на ключ, чтобы скопировать его в 1 клик)_\n\n"
                f"✨ **Что вам теперь доступно:**\n"
                f"• 🎁 Снайпер скидок на Telegram Подарки\n"
                f"• 🔋 Бесконечная энергия `∞` в 3D-майнинге\n"
                f"• 🎯 Радар слежки расширен до 100 слотов\n"
                f"• 🛠️ Конструктор ников по 20 категориям\n"
                f"• ⚡ Турбо-парсер без задержек и безлимитный поиск",
                parse_mode="Markdown",
                reply_markup=kb
            )

async def radar_worker():
    while True:
        try:
            db = load_json_file(RADAR_DB_PATH, {})
            if db and bot:
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
    asyncio.create_task(gifts_arbitrage_worker())
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

@app.post("/api/game/restore_sync")
async def restore_sync(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    client_profile = data.get("client_profile", {})
    client_radar = data.get("client_radar", [])

    if not user_id:
        return JSONResponse(status_code=400, content={"error": "no_user_id"})

    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        now = int(time.time())

        # Расчет оффлайн-фарма
        time_diff = now - user["last_seen"]
        offline_earned = 0
        offline_seconds = 0
        if time_diff > 60 and user.get("offline_miner_lvl", 0) > 0:
            offline_seconds = min(time_diff, 10800)
            rate_per_sec = OFFLINE_RATES.get(user["offline_miner_lvl"], 500) / 3600.0
            offline_earned = int(offline_seconds * rate_per_sec)
            user["offline_pending"] = offline_earned

        if client_profile.get("pro_until", 0) == -1 or client_profile.get("pro_until", 0) > user.get("pro_until", 0):
            user["pro_until"] = client_profile["pro_until"]
            user["rank"] = "👑 PRO Ловец"

        if client_profile.get("coins", 0) > user.get("coins", 0):
            user["coins"] = client_profile["coins"]

        if client_profile.get("cases_opened_total", 0) > user.get("cases_opened_total", 0):
            user["cases_opened_total"] = client_profile["cases_opened_total"]

        if client_profile.get("planet_stage", 1) > user.get("planet_stage", 1):
            user["planet_stage"] = client_profile["planet_stage"]
            user["planet_hp"] = client_profile.get("planet_hp", PLANET_HP_TABLE.get(user["planet_stage"], 100))

        if client_profile.get("multi_tap", 1) > user.get("multi_tap", 1):
            user["multi_tap"] = client_profile["multi_tap"]

        if client_profile.get("max_energy", 1000) > user.get("max_energy", 1000):
            user["max_energy"] = client_profile["max_energy"]

        if client_profile.get("offline_miner_lvl", 0) > user.get("offline_miner_lvl", 0):
            user["offline_miner_lvl"] = client_profile["offline_miner_lvl"]

        if client_profile.get("radar_extra_slots", 0) > user.get("radar_extra_slots", 0):
            user["radar_extra_slots"] = client_profile["radar_extra_slots"]

        for th in client_profile.get("unlocked_themes", []):
            if th not in user.get("unlocked_themes", []):
                user["unlocked_themes"].append(th)

        client_ref_count = int(client_profile.get("referrals_count", 0))
        if client_ref_count > user.get("referrals_count", 0):
            user["referrals_count"] = client_ref_count

        if len(client_profile.get("client_history", [])) > len(user.get("client_history", [])):
            user["client_history"] = client_profile["client_history"]

        if len(client_profile.get("client_achievements", [])) > len(user.get("client_achievements", [])):
            user["client_achievements"] = client_profile["client_achievements"]

        if client_profile.get("custom_theme_style"):
            user["custom_theme_style"] = client_profile["custom_theme_style"]

        if client_profile.get("custom_fog_rgb"):
            user["custom_fog_rgb"] = client_profile["custom_fog_rgb"]

        if client_profile.get("custom_filter_settings"):
            user["custom_filter_settings"] = client_profile["custom_filter_settings"]

        user["last_seen"] = now
        save_json_atomic_sync(GAME_DB_PATH, db)

        if client_radar:
            rdb = load_json_file(RADAR_DB_PATH, {})
            if user_id not in rdb:
                rdb[user_id] = []
            for target in client_radar:
                if target not in rdb[user_id]:
                    rdb[user_id].append(target)
            save_json_atomic_sync(RADAR_DB_PATH, rdb)

        ref_db = load_json_file(REFERRALS_DB_PATH, {})
        my_refs = ref_db.get(user_id, [])
        final_refs_count = max(len(my_refs), user.get("referrals_count", 0))
        user["referrals_count"] = final_refs_count

        is_pro, pro_until = is_user_pro(user_id)
        return {
            "status": "ok",
            "profile": user,
            "is_pro": is_pro,
            "pro_until": pro_until,
            "offline_earned": user.get("offline_pending", 0),
            "offline_seconds": offline_seconds,
            "referrals_count": final_refs_count,
            "daily_gens_count": user.get("daily_gens_count", 0),
            "daily_limit": FREE_DAILY_LIMIT,
            "max_radar_slots": (100 if is_pro else (3 + user.get("radar_extra_slots", 0))),
            "planet_hp_max": PLANET_HP_TABLE.get(user["planet_stage"], 100)
        }

@app.get("/api/game/state")
async def get_game_state(user_id: str):
    async with DB_LOCK:
        db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(db, user_id)
        now = int(time.time())
        time_diff = now - user["last_seen"]
        
        offline_earned = 0
        offline_seconds = 0
        if time_diff > 60 and user.get("offline_miner_lvl", 0) > 0:
            offline_seconds = min(time_diff, 10800)
            rate_per_sec = OFFLINE_RATES.get(user["offline_miner_lvl"], 500) / 3600.0
            offline_earned = int(offline_seconds * rate_per_sec)
            user["offline_pending"] = offline_earned

        user["last_seen"] = now
        save_json_atomic_sync(GAME_DB_PATH, db)
        is_pro, pro_until = is_user_pro(user_id)

        ref_db = load_json_file(REFERRALS_DB_PATH, {})
        my_refs = ref_db.get(str(user_id).strip(), [])
        final_refs_count = max(len(my_refs), user.get("referrals_count", 0))

        return {
            "status": "ok", 
            "profile": user, 
            "offline_earned": user.get("offline_pending", 0),
            "offline_seconds": offline_seconds,
            "is_pro": is_pro, 
            "pro_until": pro_until,
            "referrals_count": final_refs_count,
            "daily_gens_count": user.get("daily_gens_count", 0),
            "daily_limit": FREE_DAILY_LIMIT,
            "turbo_until": user.get("turbo_until", 0),
            "unlocked_themes": user.get("unlocked_themes", []),
            "max_radar_slots": (100 if is_pro else (3 + user.get("radar_extra_slots", 0))),
            "planet_hp_max": PLANET_HP_TABLE.get(user["planet_stage"], 100)
        }

@app.post("/api/case/open")
async def open_case(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    case_type = str(data.get("case_type", "daily"))
    pay_method = str(data.get("pay_method", "free"))

    if not user_id:
        return JSONResponse(status_code=400, content={"error": "no_user_id"})

    async with DB_LOCK:
        game_db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(game_db, user_id)
        now = int(time.time())

        if case_type == "daily":
            if pay_method == "free":
                if now - user.get("last_free_case_time", 0) < 86400:
                    return JSONResponse(status_code=400, content={"error": "cooldown", "msg": "Бесплатный кейс доступен 1 раз в 24 часа!"})
                user["last_free_case_time"] = now
            elif pay_method == "coins":
                if user["coins"] < 15000:
                    return JSONResponse(status_code=400, content={"error": "not_enough_coins", "msg": "Нужно 15 000 монет!"})
                user["coins"] -= 15000

        elif case_type == "elite":
            if pay_method == "coins":
                if user["coins"] < 60000:
                    return JSONResponse(status_code=400, content={"error": "not_enough_coins", "msg": "Нужно 60 000 монет!"})
                user["coins"] -= 60000

        elif case_type == "quantum":
            if pay_method == "coins":
                if user["coins"] < 150000:
                    return JSONResponse(status_code=400, content={"error": "not_enough_coins", "msg": "Нужно 150 000 монет!"})
                user["coins"] -= 150000

        user["cases_opened_total"] = user.get("cases_opened_total", 0) + 1
        pity_trigger = (user["cases_opened_total"] % 20 == 0)

        drop_item = {}
        r = random.random()

        if case_type == "daily":
            if pity_trigger or r < 0.02:
                drop_item = {"type": "pro_days", "val": 1, "name": "👑 PRO Доступ (1 день)", "rarity": "gold", "icon": "👑"}
            elif r < 0.08:
                drop_item = {"type": "turbo", "val": 15, "name": "🚀 X2 Турбо (15 мин)", "rarity": "purple", "icon": "🚀"}
            elif r < 0.22:
                drop_item = {"type": "gens", "val": 15, "name": "🎯 +15 Поисков ников", "rarity": "blue", "icon": "🎯"}
            elif r < 0.45:
                drop_item = {"type": "energy", "val": 1000, "name": "⚡ 100% Энергии", "rarity": "blue", "icon": "⚡"}
            else:
                coins_won = random.randint(5000, 10000)
                drop_item = {"type": "coins", "val": coins_won, "name": f"🟡 {coins_won:,} Монет", "rarity": "gray", "icon": "🟡"}

        elif case_type == "elite":
            if pity_trigger or r < 0.03:
                drop_item = {"type": "pro_days", "val": 7, "name": "👑 PRO Доступ (7 дней)", "rarity": "gold", "icon": "👑"}
            elif r < 0.09:
                drop_item = {"type": "pro_days", "val": 3, "name": "👑 PRO Доступ (3 дня)", "rarity": "red", "icon": "👑"}
            elif r < 0.16:
                drop_item = {"type": "radar_slot", "val": 1, "name": "🎯 +1 Слот в Радар", "rarity": "red", "icon": "🎯"}
            elif r < 0.35:
                drop_item = {"type": "turbo", "val": 20, "name": "🚀 X2 Турбо (20 мин)", "rarity": "purple", "icon": "🚀"}
            elif r < 0.60:
                drop_item = {"type": "gens", "val": 30, "name": "🎯 +30 Поисков ников", "rarity": "blue", "icon": "🎯"}
            else:
                coins_won = random.randint(15000, 25000)
                drop_item = {"type": "coins", "val": coins_won, "name": f"🟡 {coins_won:,} Монет", "rarity": "blue", "icon": "🟡"}

        elif case_type == "quantum":
            if pity_trigger or r < 0.05:
                drop_item = {"type": "pro_days", "val": 30, "name": "👑 PRO Доступ (30 ДНЕЙ!)", "rarity": "gold", "icon": "👑"}
            elif r < 0.12:
                drop_item = {"type": "theme", "val": "theme_quantum", "name": "🌌 Скин «Квантум»", "rarity": "gold", "icon": "🌌"}
            elif r < 0.25:
                drop_item = {"type": "pro_days", "val": 7, "name": "👑 PRO Доступ (7 дней)", "rarity": "red", "icon": "👑"}
            elif r < 0.42:
                drop_item = {"type": "radar_slot", "val": 2, "name": "🎯 +2 Слота в Радар", "rarity": "red", "icon": "🎯"}
            elif r < 0.65:
                drop_item = {"type": "turbo", "val": 35, "name": "🚀 X2 Турбо (35 мин)", "rarity": "purple", "icon": "🚀"}
            else:
                coins_won = random.randint(30000, 50000)
                drop_item = {"type": "coins", "val": coins_won, "name": f"🟡 {coins_won:,} Монет", "rarity": "purple", "icon": "🟡"}

        if drop_item["type"] == "coins":
            user["coins"] += drop_item["val"]
        elif drop_item["type"] == "energy":
            user["energy"] = user["max_energy"]
        elif drop_item["type"] == "gens":
            user["daily_gens_count"] = max(0, user.get("daily_gens_count", 0) - drop_item["val"])
        elif drop_item["type"] == "turbo":
            cur_turbo = max(now, user.get("turbo_until", 0))
            user["turbo_until"] = cur_turbo + (drop_item["val"] * 60)
        elif drop_item["type"] == "radar_slot":
            user["radar_extra_slots"] += drop_item["val"]
        elif drop_item["type"] == "theme":
            if drop_item["val"] not in user["unlocked_themes"]:
                user["unlocked_themes"].append(drop_item["val"])
        elif drop_item["type"] == "pro_days":
            if user.get("pro_until") != -1:
                cur_pro = max(now, user.get("pro_until", 0))
                user["pro_until"] = cur_pro + (drop_item["val"] * 86400)
            user["rank"] = "👑 PRO Ловец"

        user["last_seen"] = now
        save_json_atomic_sync(GAME_DB_PATH, db)

        is_pro, pro_until = is_user_pro(user_id)
        return {
            "status": "ok",
            "drop": drop_item,
            "profile": user,
            "is_pro": is_pro,
            "pro_until": pro_until,
            "cases_opened_total": user["cases_opened_total"],
            "pity_progress": user["cases_opened_total"] % 20
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

        if item_id == "turbo_boost_15":
            if user["coins"] >= 65000:
                user["coins"] -= 65000
                cur_turbo = max(now, user.get("turbo_until", 0))
                user["turbo_until"] = cur_turbo + (15 * 60)
            else: 
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "radar_slot":
            if user["coins"] >= 35000:
                user["coins"] -= 35000
                user["radar_extra_slots"] += 1
            else: 
                return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

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

@app.post("/api/promo/activate")
async def activate_promo(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    code = str(data.get("code", "")).strip().upper()
    now = int(time.time())

    if not user_id or not code:
        return JSONResponse(status_code=400, content={"error": "invalid_input", "msg": "Введите код!"})

    async with DB_LOCK:
        promos_db = load_json_file(PROMOS_DB_PATH, {})
        if code in promos_db:
            promo_data = promos_db[code]
            if promo_data.get("used_by"):
                return JSONResponse(status_code=400, content={"error": "already_used", "msg": "Этот промокод уже был активирован!"})
            
            coins_reward = promo_data.get("coins", 100000)
            promo_data["used_by"] = user_id
            promo_data["used_at"] = now
            save_json_atomic_sync(PROMOS_DB_PATH, promos_db)

            game_db = load_json_file(GAME_DB_PATH, {})
            user = get_user_profile(game_db, user_id)
            user["coins"] += coins_reward
            save_json_atomic_sync(GAME_DB_PATH, game_db)

            return {"status": "ok", "type": "coins", "coins": user["coins"], "reward": coins_reward, "msg": f"🎉 Начислено +{coins_reward:,} 🟡 монет!"}

        keys_db = load_json_file(KEYS_DB_PATH, {})
        if code in keys_db:
            k_data = keys_db[code]
            if k_data.get("activated_status") == "used":
                return JSONResponse(status_code=400, content={"error": "already_used", "msg": "Этот PRO-ключ уже активирован!"})

            secs = k_data.get("seconds", 30 * 86400)
            k_data["bound_user_id"] = user_id
            k_data["activated_status"] = "used"
            k_data["activated_at"] = now
            save_json_atomic_sync(KEYS_DB_PATH, keys_db)

            game_db = load_json_file(GAME_DB_PATH, {})
            user = get_user_profile(game_db, user_id)
            
            if user.get("pro_until") != -1:
                if secs == -1:
                    user["pro_until"] = -1
                else:
                    cur_pro = max(now, user.get("pro_until", 0))
                    user["pro_until"] = cur_pro + secs
            
            user["rank"] = "👑 PRO Ловец"
            save_json_atomic_sync(GAME_DB_PATH, game_db)

            duration_text = "Навсегда (Lifetime) 🌌" if secs == -1 else f"{secs // 86400} дней 📅"
            return {"status": "ok", "type": "pro", "is_pro": True, "pro_until": user["pro_until"], "msg": f"🎉 PRO активирован на {duration_text}!"}

        return JSONResponse(status_code=400, content={"error": "not_found", "msg": "❌ Неверный или несуществующий промокод!"})

@app.get("/api/gifts/catalog")
async def get_gifts_catalog():
    return {"status": "ok", "catalog": GIFTS_CATALOG}

@app.post("/api/gifts/settings")
async def save_gift_settings(request: Request):
    data = await request.json()
    user_id = str(data.get("user_id", "")).strip()
    active = bool(data.get("active", False))
    margin = int(data.get("margin", 30))
    max_budget = float(data.get("max_budget", 1000))
    gifts = list(data.get("gifts", []))

    is_pro, _ = is_user_pro(user_id)
    if active and not is_pro:
        return JSONResponse(status_code=403, content={"error": "pro_required", "msg": "Снайпер подарков доступен только в PRO!"})

    async with DB_LOCK:
        gdb = load_json_file(GIFTS_DB_PATH, {})
        gdb[user_id] = {
            "active": active,
            "margin": margin,
            "max_budget": max_budget,
            "gifts": gifts,
            "updated_at": int(time.time())
        }
        save_json_atomic_sync(GIFTS_DB_PATH, gdb)
        return {"status": "ok", "settings": gdb[user_id]}

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
    reward_referrer_id = None
    async with DB_LOCK:
        game_db = load_json_file(GAME_DB_PATH, {})
        user = get_user_profile(game_db, finder_id)
        is_pro, _ = is_user_pro(finder_id)
        
        if not is_pro:
            if user.get("daily_gens_count", 0) >= FREE_DAILY_LIMIT:
                return JSONResponse(
                    status_code=429, 
                    content={
                        "error": "limit_reached",
                        "msg": f"Дневной лимит ({FREE_DAILY_LIMIT} поисков) исчерпан!",
                        "daily_gens_count": user["daily_gens_count"],
                        "daily_limit": FREE_DAILY_LIMIT
                    }
                )
            user["daily_gens_count"] = user.get("daily_gens_count", 0) + 1

        user["gens_total_count"] = user.get("gens_total_count", 0) + 1

        if user.get("referred_by") and not user.get("referral_reward_claimed", False) and user["gens_total_count"] >= 3:
            user["referral_reward_claimed"] = True
            referrer_id = user["referred_by"]
            if referrer_id in game_db:
                ref_user = get_user_profile(game_db, referrer_id)
                now_ts = int(time.time())
                if ref_user.get("pro_until") != -1:
                    cur_pro = max(now_ts, ref_user.get("pro_until", 0))
                    ref_user["pro_until"] = cur_pro + 86400
                ref_user["rank"] = "👑 PRO Ловец"
                ref_user["referrals_count"] = ref_user.get("referrals_count", 0) + 1
                reward_referrer_id = referrer_id

        save_json_atomic_sync(GAME_DB_PATH, game_db)

    if reward_referrer_id and bot:
        try:
            await bot.send_message(
                chat_id=int(reward_referrer_id),
                text=(
                    "🎉 **ВАШ ДРУГ АКТИВИРОВАЛ ПРИЛОЖЕНИЕ!** 👥\n\n"
                    f"Ловец **{finder_name}** сделал 3 поиска и подтвердил активность!\n"
                    "👑 Вам начислен **+1 ДЕНЬ PRO ПОДПИСКИ** (24 часа) бесплатно!"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    generated = ""
    is_free = False
    eval_data = {}

    clean_keyword = custom_keyword.strip() if use_filter else ""

    for _ in range(12):
        if clean_keyword:
            if not is_pro:
                return JSONResponse(status_code=403, content={"error": "pro_required", "msg": "Конструктор по 20 категориям доступен только в PRO!"})
            generated = generate_keyword_custom_username(clean_keyword, custom_category, use_und)
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
        "evaluation": eval_data,
        "daily_gens_count": user.get("daily_gens_count", 0),
        "daily_limit": FREE_DAILY_LIMIT,
        "is_pro": is_pro
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
