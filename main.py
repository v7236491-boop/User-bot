import os
import random
import asyncio
import time
import json
import secrets
import aiohttp
from datetime import datetime, timezone, date
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import CheckUsernameRequest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import BigInteger, Integer, String, Date, Text, Boolean, select, update
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
SESSION_STRING = os.getenv("TELEGRAM_SESSION")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/namehunter")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), default="Ловец")
    coins: Mapped[int] = mapped_column(BigInteger, default=0)
    energy: Mapped[int] = mapped_column(Integer, default=1000)
    max_energy: Mapped[int] = mapped_column(Integer, default=1000)
    multi_tap: Mapped[int] = mapped_column(Integer, default=1)
    energy_regen: Mapped[int] = mapped_column(Integer, default=1)
    offline_miner_lvl: Mapped[int] = mapped_column(Integer, default=0)
    last_seen: Mapped[int] = mapped_column(BigInteger, default=0)
    planet_stage: Mapped[int] = mapped_column(Integer, default=1)
    planet_hp: Mapped[int] = mapped_column(Integer, default=100)
    rank: Mapped[str] = mapped_column(String(64), default="Ловец")
    pro_until: Mapped[int] = mapped_column(BigInteger, default=0)
    pro_warned: Mapped[bool] = mapped_column(Boolean, default=False)
    pro_expired_notified: Mapped[bool] = mapped_column(Boolean, default=True)
    radar_extra_slots: Mapped[int] = mapped_column(Integer, default=0)
    turbo_until: Mapped[int] = mapped_column(BigInteger, default=0)
    spins: Mapped[int] = mapped_column(Integer, default=1)
    referred_by: Mapped[int] = mapped_column(BigInteger, nullable=True)
    referrals_count: Mapped[int] = mapped_column(Integer, default=0)
    ref_status: Mapped[str] = mapped_column(String(16), default="none")
    gen_limit_date: Mapped[date] = mapped_column(Date, default=date.today)
    gen_count_today: Mapped[int] = mapped_column(Integer, default=0)
    unlocked_themes: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    radar_targets: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    gift_radar_active: Mapped[bool] = mapped_column(Boolean, default=False)
    gift_margin: Mapped[int] = mapped_column(Integer, default=30)
    gift_max_budget: Mapped[int] = mapped_column(Integer, default=10000)
    selected_gifts: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    history: Mapped[list] = mapped_column(JSONB, default=list)

class PromoCode(Base):
    __tablename__ = "promo_codes"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    value: Mapped[int] = mapped_column(BigInteger)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by: Mapped[int] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=0)

class Leaderboard(Base):
    __tablename__ = "leaderboard"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    rank: Mapped[str] = mapped_column(String(16))
    price: Mapped[str] = mapped_column(String(64))
    score: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String(16))
    finder_name: Mapped[str] = mapped_column(String(64))
    finder_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[int] = mapped_column(BigInteger)

CHECK_CACHE = {}
CACHE_TTL = 86400
TELETHON_AVAILABLE = False
FAILED_ATTEMPTS = {}
FREE_DAILY_LIMIT = 100

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher() if BOT_TOKEN else None

if SESSION_STRING:
    telethon_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    telethon_client = TelegramClient(os.path.join(BASE_DIR, 'checker_session'), API_ID, API_HASH)

OFFLINE_RATES = {0: 0, 1: 500, 2: 1200, 3: 2500, 4: 4500, 5: 8000, 6: 14000, 7: 22000, 8: 32000, 9: 45000, 10: 60000}
PLANET_HP_TABLE = {1: 100, 2: 300, 3: 800, 4: 2000, 5: 5000, 6: 12000, 7: 28000, 8: 65000, 9: 150000, 10: 500000}
KEY_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

def generate_secure_code(prefix: str) -> str:
    parts = ["".join(secrets.choice(KEY_CHARSET) for _ in range(4)) for _ in range(3)]
    return f"{prefix}-{parts[0]}-{parts[1]}-{parts[2]}"

def generate_secure_pro_key() -> str:
    parts = ["".join(secrets.choice(KEY_CHARSET) for _ in range(4)) for _ in range(4)]
    return f"PRO-{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}"

async def init_db_and_promos():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async with async_session() as session:
        now = int(time.time())
        tiers = [(50, 10_000, "COIN10K"), (100, 100_000, "COIN100K"), (20, 10_000_000, "COIN10M")]
        for count, val, prefix in tiers:
            res = await session.execute(select(PromoCode).where(PromoCode.type == 'coins', PromoCode.value == val))
            existing = len(res.scalars().all())
            for _ in range(count - existing):
                session.add(PromoCode(code=generate_secure_code(prefix), type='coins', value=val, created_at=now))
        
        pregen_pro = [
            ("PRO-LIFE-X9Z2-M4K7-R8W3", -1), ("PRO-LIFE-V7N3-Q5T8-Y2C6", -1),
            ("PRO-30D1-L8N4-K2X7-P9R3", 30 * 86400), ("PRO-30D2-Q5M9-T3V8-Y6C2", 30 * 86400),
            ("PRO-1D01-K9X2-M4P7-R8W3", 86400), ("PRO-1D02-J7N3-Q5T8-V2Y6", 86400)
        ]
        for p_code, secs in pregen_pro:
            exists = await session.get(PromoCode, p_code)
            if not exists:
                session.add(PromoCode(code=p_code, type='pro', value=secs, created_at=now))
        await session.commit()

async def get_or_create_user(session: AsyncSession, user_id: int, username: str = "Ловец") -> User:
    user = await session.get(User, user_id)
    now = int(time.time())
    today = datetime.now(timezone.utc).date()
    if not user:
        user = User(
            telegram_id=user_id, username=username, last_seen=now,
            gen_limit_date=today, gen_count_today=0, unlocked_themes=["default"],
            radar_targets=[], selected_gifts=[], history=[]
        )
        session.add(user)
        await session.flush()
    else:
        if user.gen_limit_date != today:
            user.gen_limit_date = today
            user.gen_count_today = 0
        if username and username != "Ловец":
            user.username = username
        time_passed = now - user.last_seen
        if time_passed > 0 and user.energy < user.max_energy:
            user.energy = min(user.max_energy, user.energy + time_passed * user.energy_regen)
        user.last_seen = now
    return user

ROULETTE_PRIZES = [
    {"type": "coins", "amount": 10000, "name": "10 000 🟡", "rarity": "gray", "icon": "🟡", "weight": 40},
    {"type": "coins", "amount": 35000, "name": "35 000 🟡", "rarity": "blue", "icon": "🟡", "weight": 25},
    {"type": "turbo", "amount": 15, "name": "⚡ X2 Турбо (15 мин)", "rarity": "purple", "icon": "⚡", "weight": 15},
    {"type": "radar_slot", "amount": 1, "name": "🎯 +1 Слот Радара", "rarity": "red", "icon": "🎯", "weight": 10},
    {"type": "pro_days", "amount": 3, "name": "👑 PRO (3 дня)", "rarity": "red", "icon": "👑", "weight": 7},
    {"type": "pro_days", "amount": 7, "name": "👑 PRO (7 дней)", "rarity": "gold", "icon": "👑", "weight": 2.5},
    {"type": "pro_days", "amount": -1, "name": "👑 PRO Навсегда", "rarity": "gold", "icon": "👑", "weight": 0.5}
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

GIFTS_CATALOG = [
    {"id": "crystal_pepe", "name": "Crystal Pepe", "type": "pepe_blue", "bg": "#1e3a5f", "number": "#2629", "floor_ton": 7000.0},
    {"id": "bronze_pepe", "name": "Bronze Pepe", "type": "pepe_bronze", "bg": "#45220c", "number": "#990", "floor_ton": 7000.0},
    {"id": "orange_pepe", "name": "Orange Pepe", "type": "pepe_orange", "bg": "#5a2d0c", "number": "#402", "floor_ton": 6999.0},
    {"id": "neon_pepe", "name": "Neon Pink Pepe", "type": "pepe_pink", "bg": "#1f4e38", "number": "#833", "floor_ton": 6900.0},
    {"id": "chrome_pepe", "name": "Chrome Pepe", "type": "pepe_chrome", "bg": "#432b4a", "number": "#984", "floor_ton": 6850.0},
    {"id": "red_pepe", "name": "Ruby Pepe", "type": "pepe_red", "bg": "#521c24", "number": "#2705", "floor_ton": 6833.0},
    {"id": "golden_flower", "name": "Golden Flower", "type": "flower_gold", "bg": "#1e241c", "number": "#49643", "floor_ton": 6753.0},
    {"id": "snoop_lowrider", "name": "Snoop Lowrider", "type": "snoop_car", "bg": "#3d2b1f", "number": "#16593", "floor_ton": 6666.0},
    {"id": "durov_cap", "name": "Telegram Cap", "type": "tg_cap", "bg": "#1e222a", "number": "#1142", "floor_ton": 6555.0},
    {"id": "magic_potion", "name": "Magic Potion", "type": "potion", "bg": "#2a1b40", "number": "#524", "floor_ton": 14.5},
    {"id": "diamond_ring", "name": "Diamond Ring", "type": "ring", "bg": "#1b3340", "number": "#891", "floor_ton": 35.0},
    {"id": "cosmic_rocket", "name": "Cosmic Rocket", "type": "rocket", "bg": "#171a36", "number": "#3420", "floor_ton": 18.0}
]

SEEN_NFT_LISTINGS = set()

async def gifts_arbitrage_worker():
    while True:
        try:
            async with async_session() as session:
                res = await session.execute(select(User).where(User.gift_radar_active == True))
                active_users = res.scalars().all()
                now_ts = int(time.time())
                
                if active_users and bot:
                    for gift in GIFTS_CATALOG:
                        if random.random() < 0.18:
                            discount = random.choice([25, 30, 35, 40, 50])
                            floor = gift["floor_ton"]
                            deal_price = round(floor * (1 - discount / 100.0), 1)
                            lot_id = f"{gift['id']}_{now_ts // 60}_{deal_price}"

                            if lot_id not in SEEN_NFT_LISTINGS:
                                SEEN_NFT_LISTINGS.add(lot_id)
                                item_num = gift["number"]
                                market_url = "https://fragment.com/gifts"

                                for u in active_users:
                                    is_pro = u.pro_until == -1 or u.pro_until > now_ts
                                    if not is_pro: continue
                                    if discount >= u.gift_margin and deal_price <= u.gift_max_budget:
                                        if not u.selected_gifts or gift["id"] in u.selected_gifts:
                                            try:
                                                kb = InlineKeyboardMarkup(
                                                    inline_keyboard=[[InlineKeyboardButton(text=f"💎 Купить за {deal_price} TON", url=market_url)]]
                                                )
                                                await bot.send_message(
                                                    chat_id=u.telegram_id,
                                                    text=(
                                                        f"🚨 **FRAGMENT СНАЙПЕР: СКИДКА {discount}%!** 🎁\n\n"
                                                        f"🖼️ **Подарок:** {gift['name']} {item_num}\n"
                                                        f"💰 **Цена лота:** `{deal_price} TON` *(Флор: {floor} TON)*\n"
                                                        f"📈 **Чистая выгода:** `+{round(floor - deal_price, 1)} TON`\n\n"
                                                        f"⚡ _Успей забрать лот на Fragment раньше других!_"
                                                    ),
                                                    parse_mode="Markdown", reply_markup=kb
                                                )
                                            except Exception: pass
        except Exception:
            pass
        await asyncio.sleep(4)

PREMIUM_PREFIXES = ["neo", "vox", "lux", "zen", "vex", "arc", "sol", "dex", "sky", "ray"]
ELITE_ROOTS = ["nova", "apex", "volt", "onyx", "flux", "aura", "lyra", "zane", "koda", "mira", "dusk", "dawn", "vibe"]
CONSONANTS_EASY = "bcdfgklmnprstvwz"
VOWELS_EASY = "aeiouy"

def generate_keyword_custom_username(keyword: str, category: str, use_und: bool = False) -> str:
    keyword = keyword.strip().lower().replace("@", "")
    affixes = AFFIX_DATABASE_20.get(category, AFFIX_DATABASE_20["superheroes"])
    affix = random.choice(affixes)
    pattern = random.choice(["kw_affix", "affix_kw"])
    if pattern == "kw_affix":
        return f"{keyword}_{affix}" if use_und else f"{keyword}{affix}"
    else:
        return f"{affix}_{keyword}" if use_und else f"{affix}{keyword}"

def generate_smart_username(len_mode: str = "5-6", use_num: bool = False, use_und: bool = False, strict_filter: bool = False) -> tuple[str, bool, bool]:
    r_val = random.random()
    if r_val < 0.45 and not strict_filter:
        root = random.choice(ELITE_ROOTS)
        pref = random.choice(PREMIUM_PREFIXES)
        res = root + random.choice(["x", "z", "r", "s", "o", "a"]) if random.random() < 0.5 else pref + root[:3]
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
    length = len(username.replace("@", "").strip())
    if length <= 5:
        return {"rank": "SSS+", "status": "🔥 Fragment (~30-90+ TON)", "color": "#29c75f", "score": 95}
    elif length == 6:
        return {"rank": "SS", "status": "💎 Редкий бренд (~10-35 TON)", "color": "#eab308", "score": 75}
    return {"rank": "A", "status": "Свободен (~1-3 TON)", "color": "#3b82f6", "score": 30}

async def check_username_telethon(username: str) -> bool:
    global TELETHON_AVAILABLE
    username = username.replace("@", "").strip().lower()
    if len(username) < 5: return False
    now = time.time()
    if username in CHECK_CACHE and now - CHECK_CACHE[username][1] < CACHE_TTL:
        return CHECK_CACHE[username][0]

    if TELETHON_AVAILABLE:
        try:
            coro = telethon_client(CheckUsernameRequest(username=username))
            res = await asyncio.wait_for(coro, timeout=1.5)
            CHECK_CACHE[username] = (bool(res is True), now)
            return bool(res is True)
        except Exception:
            pass

    try:
        url = f"https://t.me/{username}"
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=2.0)) as resp:
                text = await resp.text()
                is_free = ("tgme_action_button_new" not in text and "View in Telegram" not in text and "Send Message" not in text)
                CHECK_CACHE[username] = (is_free, now)
                return is_free
    except Exception:
        return False

TARRIFS = {
    "pro_30": {"seconds": 30 * 86400, "stars": 75, "title": "PRO Доступ (30 дней)"},
    "pro_60": {"seconds": 60 * 86400, "stars": 120, "title": "PRO Доступ (60 дней)"},
    "pro_90": {"seconds": 90 * 86400, "stars": 160, "title": "PRO Доступ (90 дней)"},
    "pro_forever": {"seconds": -1, "stars": 490, "title": "PRO Навсегда (Lifetime)"}
}

if dp and bot:
    @dp.message(CommandStart())
    async def cmd_start(message: types.Message, command: CommandObject):
        user_id = message.from_user.id
        ref_id = None
        if command.args and command.args.startswith("ref_"):
            potential = command.args.replace("ref_", "").strip()
            if potential.isdigit() and int(potential) != user_id:
                ref_id = int(potential)

        async with async_session() as session:
            user = await get_or_create_user(session, user_id, message.from_user.full_name)
            if ref_id and not user.referred_by and user.ref_status == "none":
                user.referred_by = ref_id
                user.ref_status = "pending"
            await session.commit()

        web_app_url = "https://user-bot-production-8a5d.up.railway.app"
        kb = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🚀 Запустить NameHunter PRO", web_app=WebAppInfo(url=web_app_url))]]
        )
        await message.answer(
            "👋 **Добро пожаловать в NameHunter PRO!**\n\n"
            "🎯 Парсер никнеймов (100 в день бесплатно, ∞ в PRO)\n"
            "🎡 Реферальная рулетка с накоплением PRO-дней\n"
            "🪐 3D-майнинг 10 космических тел до Чёрной Дыры",
            reply_markup=kb, parse_mode="Markdown"
        )

    @dp.pre_checkout_query()
    async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

    @dp.message(F.successful_payment)
    async def process_successful_payment(message: types.Message):
        payload = message.successful_payment.invoice_payload
        user_id = message.from_user.id
        tariff = TARRIFS.get(payload)

        if tariff:
            secs = tariff["seconds"]
            now = int(time.time())
            key_code = generate_secure_pro_key()
            
            async with async_session() as session:
                session.add(PromoCode(code=key_code, type='pro', value=secs, is_used=True, used_by=user_id, created_at=now))
                user = await get_or_create_user(session, user_id)
                if secs == -1:
                    user.pro_until = -1
                else:
                    user.pro_until = max(now, user.pro_until) + secs
                user.rank = "👑 PRO Ловец"
                await session.commit()

            duration_text = "Навсегда (Lifetime) 🌌" if secs == -1 else f"{secs // 86400} дней 📅"
            web_app_url = "https://user-bot-production-8a5d.up.railway.app"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 Открыть WebApp", web_app=WebAppInfo(url=web_app_url))]])
            await message.answer(f"🎉 **СПАСИБО ЗА ПОКУПКУ PRO!**\nСрок: {duration_text}\nКлюч: `{key_code}`", parse_mode="Markdown", reply_markup=kb)

async def pro_expiry_worker():
    while True:
        try:
            now_ts = int(time.time())
            async with async_session() as session:
                res = await session.execute(select(User).where(User.pro_until > 0))
                pro_users = res.scalars().all()
                for u in pro_users:
                    diff = u.pro_until - now_ts
                    if 0 < diff <= 180 and not u.pro_warned:
                        u.pro_warned = True
                        if bot:
                            try:
                                await bot.send_message(
                                    chat_id=u.telegram_id,
                                    text="⏳ **Внимание! Ваша PRO-подписка истекает через 3 минуты!** ⚠️"
                                )
                            except Exception: pass
                    if diff <= 0 and not u.pro_expired_notified:
                        u.pro_expired_notified = True
                        u.rank = "Ловец"
                        if bot:
                            try:
                                await bot.send_message(
                                    chat_id=u.telegram_id,
                                    text="🥺 **Ваша PRO-подписка завершилась!** 🔒"
                                )
                            except Exception: pass
                await session.commit()
        except Exception:
            pass
        await asyncio.sleep(15)

async def radar_worker():
    while True:
        try:
            async with async_session() as session:
                res = await session.execute(select(User).where(User.radar_targets != None))
                users_with_radar = res.scalars().all()
                if users_with_radar and bot and TELETHON_AVAILABLE:
                    for u in users_with_radar:
                        targets = list(u.radar_targets or [])
                        for tg_target in targets:
                            is_free = await check_username_telethon(tg_target)
                            if is_free:
                                try:
                                    await bot.send_message(
                                        chat_id=u.telegram_id,
                                        text=f"🚨 **РАДАР:** Ник `@{tg_target}` освободился!\nЗабирай скорее!"
                                    )
                                    targets.remove(tg_target)
                                    u.radar_targets = targets
                                    await session.commit()
                                except Exception: pass
                            await asyncio.sleep(2)
        except Exception:
            pass
        await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global TELETHON_AVAILABLE
    await init_db_and_promos()
    try:
        await telethon_client.connect()
        TELETHON_AVAILABLE = await telethon_client.is_user_authorized()
    except Exception:
        TELETHON_AVAILABLE = False
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(pro_expiry_worker())
    asyncio.create_task(radar_worker())
    asyncio.create_task(gifts_arbitrage_worker())
    yield
    try:
        await telethon_client.disconnect()
    except Exception:
        pass

app = FastAPI(title="Username Scanner PRO", lifespan=lifespan)

@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html", headers={"Cache-Control": "no-cache"})
    return JSONResponse(status_code=404, content={"error": "index.html not found"})

@app.post("/api/game/restore_sync")
async def restore_sync(request: Request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    if not uid.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_uid"})
    user_id = int(uid)

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        now = int(time.time())
        time_diff = now - user.last_seen
        offline_earned = 0
        offline_seconds = 0
        if time_diff > 60 and user.offline_miner_lvl > 0:
            offline_seconds = min(time_diff, 10800)
            offline_earned = int(offline_seconds * (OFFLINE_RATES.get(user.offline_miner_lvl, 500) / 3600.0))
            user.coins += offline_earned

        await session.commit()
        is_pro = user.pro_until == -1 or user.pro_until > now
        return {
            "status": "ok",
            "profile": {
                "coins": user.coins, "energy": user.energy, "max_energy": user.max_energy,
                "multi_tap": user.multi_tap, "planet_stage": user.planet_stage, "planet_hp": user.planet_hp,
                "rank": user.rank, "pro_until": user.pro_until, "spins": user.spins,
                "referrals_count": user.referrals_count, "unlocked_themes": user.unlocked_themes,
                "radar_extra_slots": user.radar_extra_slots, "offline_miner_lvl": user.offline_miner_lvl
            },
            "is_pro": is_pro,
            "pro_until": user.pro_until,
            "spins": user.spins,
            "referrals_count": user.referrals_count,
            "gens_today": user.gen_count_today,
            "daily_limit": FREE_DAILY_LIMIT,
            "offline_earned": offline_earned,
            "offline_seconds": offline_seconds,
            "max_radar_slots": (100 if is_pro else (3 + user.radar_extra_slots)),
            "planet_hp_max": PLANET_HP_TABLE.get(user.planet_stage, 100)
        }

@app.post("/api/game/collect_offline")
async def collect_offline(request: Request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    if not uid.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_uid"})
    user_id = int(uid)
    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        now = int(time.time())
        time_diff = now - user.last_seen
        earned = 0
        if time_diff > 60 and user.offline_miner_lvl > 0:
            offline_seconds = min(time_diff, 10800)
            earned = int(offline_seconds * (OFFLINE_RATES.get(user.offline_miner_lvl, 500) / 3600.0))
            user.coins += earned
            user.last_seen = now
            await session.commit()
        return {"status": "ok", "coins": user.coins, "collected": earned}

@app.post("/api/roulette/spin")
async def spin_roulette(request: Request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    if not uid.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_uid"})
    user_id = int(uid)
    pay_method = str(data.get("pay_method", "free"))

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        now = int(time.time())

        if pay_method == "free":
            if user.spins <= 0:
                return JSONResponse(status_code=400, content={"error": "no_spins", "msg": "Нет спинов! Пригласите друга."})
            user.spins -= 1
        elif pay_method == "coins_15":
            if user.coins < 15000: return JSONResponse(status_code=400, content={"error": "not_enough_coins", "msg": "Нужно 15 000 🟡"})
            user.coins -= 15000
        elif pay_method == "coins_60":
            if user.coins < 60000: return JSONResponse(status_code=400, content={"error": "not_enough_coins", "msg": "Нужно 60 000 🟡"})
            user.coins -= 60000
        elif pay_method == "coins_150":
            if user.coins < 150000: return JSONResponse(status_code=400, content={"error": "not_enough_coins", "msg": "Нужно 150 000 🟡"})
            user.coins -= 150000

        prize = random.choices(ROULETTE_PRIZES, weights=[p["weight"] for p in ROULETTE_PRIZES], k=1)[0]
        if prize["type"] == "coins":
            user.coins += prize["amount"]
        elif prize["type"] == "turbo":
            user.turbo_until = max(now, user.turbo_until) + prize["amount"] * 60
        elif prize["type"] == "radar_slot":
            user.radar_extra_slots += prize["amount"]
        elif prize["type"] == "pro_days":
            if prize["amount"] == -1:
                user.pro_until = -1
            else:
                base = max(now, user.pro_until)
                user.pro_until = base + prize["amount"] * 86400
            user.rank = "👑 PRO Ловец"

        await session.commit()
        is_pro = user.pro_until == -1 or user.pro_until > now
        return {"status": "ok", "drop": prize, "spins": user.spins, "coins": user.coins, "is_pro": is_pro, "pro_until": user.pro_until}

@app.post("/api/promo/activate")
async def activate_promo(request: Request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    code = str(data.get("code", "")).strip().upper()
    if not uid.isdigit() or not code: return JSONResponse(status_code=400, content={"error": "invalid_data"})
    user_id = int(uid)
    now = int(time.time())

    if user_id in FAILED_ATTEMPTS:
        fails, lock_time = FAILED_ATTEMPTS[user_id]
        if fails >= 5:
            if now - lock_time < 300:
                return JSONResponse(status_code=429, content={"error": f"Блокировка на {300 - (now - lock_time)} сек."})
            else:
                FAILED_ATTEMPTS[user_id] = [0, 0]

    async with async_session() as session:
        promo = await session.get(PromoCode, code)
        if not promo or promo.is_used:
            cur_fails = FAILED_ATTEMPTS.get(user_id, [0, 0])[0] + 1
            FAILED_ATTEMPTS[user_id] = [cur_fails, now]
            return JSONResponse(status_code=400, content={"error": "Промокод не существует или уже активирован!"})

        user = await get_or_create_user(session, user_id)
        promo.is_used = True
        promo.used_by = user_id

        if promo.type == 'coins':
            user.coins += promo.value
            msg = f"🎉 Начислено +{promo.value:,} 🟡 монет!"
        else:
            if promo.value == -1: user.pro_until = -1
            else: user.pro_until = max(now, user.pro_until) + promo.value
            user.rank = "👑 PRO Ловец"
            msg = "🎉 PRO подписка успешно активирована!"

        if user_id in FAILED_ATTEMPTS: del FAILED_ATTEMPTS[user_id]
        await session.commit()
        return {"status": "ok", "msg": msg, "coins": user.coins, "pro_until": user.pro_until}

@app.get("/api/generate")
async def generate_username(
    finder_id: str = Query("0"), 
    finder_name: str = Query("Аноним"), 
    custom_keyword: str = Query(""), 
    custom_category: str = Query("superheroes"), 
    use_filter: bool = Query(False), 
    len_mode: str = Query("5-6")
):
    if not finder_id.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_id"})
    user_id = int(finder_id)
    reward_ref_id = None

    async with async_session() as session:
        user = await get_or_create_user(session, user_id, finder_name)
        now = int(time.time())
        is_pro = user.pro_until == -1 or user.pro_until > now

        if not is_pro:
            if user.gen_count_today >= FREE_DAILY_LIMIT:
                return JSONResponse(status_code=429, content={"error": "limit_reached", "msg": "Дневной лимит (100) исчерпан! Оформите PRO."})
            user.gen_count_today += 1

        if user.referred_by and user.ref_status == "pending":
            user.ref_status = "completed"
            inviter = await session.get(User, user.referred_by)
            if inviter:
                inviter.referrals_count += 1
                inviter.spins += 1
                reward_ref_id = inviter.telegram_id

        await session.commit()

    if reward_ref_id and bot:
        try:
            await bot.send_message(
                chat_id=reward_ref_id,
                text=f"🎉 **Ваш реферал ({finder_name}) сделал первую генерацию!**\n🎁 Вам начислен **+1 спин** в Рулетку Фортуны!"
            )
        except Exception: pass

    if custom_keyword.strip():
        generated = generate_keyword_custom_username(custom_keyword, custom_category)
        is_pure, has_und = True, False
    else:
        generated, is_pure, has_und = generate_smart_username(len_mode=len_mode, strict_filter=use_filter)

    is_free = await check_username_telethon(generated)
    eval_data = calculate_catch_score(generated, is_free, is_pure, has_und)

    if is_free and eval_data.get("score", 0) >= 40:
        async with async_session() as session:
            res = await session.execute(select(Leaderboard).where(Leaderboard.username == generated))
            if not res.scalar_one_or_none():
                session.add(Leaderboard(
                    username=generated, rank=eval_data["rank"], price=eval_data["status"],
                    score=eval_data["score"], color=eval_data["color"], finder_name=finder_name or "Аноним",
                    finder_id=str(user_id), created_at=int(time.time())
                ))
                await session.commit()

    return {
        "status": "success", "generated_username": generated, "is_free": is_free,
        "evaluation": eval_data, "gens_left_today": -1 if is_pro else max(0, FREE_DAILY_LIMIT - user.gen_count_today)
    }

@app.post("/api/game/sync_tap")
async def sync_tap(request: Request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    if not uid.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_uid"})
    taps = int(data.get("taps", 0))

    async with async_session() as session:
        user = await get_or_create_user(session, int(uid))
        now = int(time.time())
        is_pro = user.pro_until == -1 or user.pro_until > now
        if taps > 0:
            actual = taps if is_pro else min(taps, user.energy)
            user.coins += actual * user.multi_tap
            if not is_pro: user.energy = max(0, user.energy - actual)
            user.planet_hp = max(0, user.planet_hp - taps)
            if user.planet_hp <= 0:
                user.planet_stage = min(10, user.planet_stage + 1)
                user.planet_hp = PLANET_HP_TABLE.get(user.planet_stage, 100)
                user.coins += user.planet_stage * 500
            await session.commit()
        return {"status": "ok", "coins": user.coins, "energy": user.energy, "planet_stage": user.planet_stage, "planet_hp": user.planet_hp}

@app.post("/api/game/buy")
async def buy_game_item(request: Request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    item_id = str(data.get("item_id", ""))
    if not uid.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_uid"})
    user_id = int(uid)

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        now = int(time.time())

        if item_id == "turbo_boost_15":
            if user.coins >= 65000:
                user.coins -= 65000
                user.turbo_until = max(now, user.turbo_until) + (15 * 60)
            else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "radar_slot":
            if user.coins >= 35000:
                user.coins -= 35000
                user.radar_extra_slots += 1
            else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "theme_quasar":
            themes = list(user.unlocked_themes or [])
            if "theme_quasar" in themes:
                return JSONResponse(status_code=400, content={"error": "already_owned"})
            if user.coins >= 100000:
                user.coins -= 100000
                themes.append("theme_quasar")
                user.unlocked_themes = themes
            else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "multi_tap":
            cost = int(200 * (1.8 ** (user.multi_tap - 1)))
            if user.coins >= cost and user.multi_tap < 20:
                user.coins -= cost
                user.multi_tap += 1
            else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "max_energy":
            lvl = (user.max_energy - 1000) // 500
            cost = int(150 * (1.6 ** lvl))
            if user.coins >= cost and lvl < 20:
                user.coins -= cost
                user.max_energy += 500
                user.energy = user.max_energy
            else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        elif item_id == "offline_miner":
            lvl = user.offline_miner_lvl
            cost = 3000 if lvl == 0 else int(3000 * (2.2 ** lvl))
            if user.coins >= cost and lvl < 10:
                user.coins -= cost
                user.offline_miner_lvl += 1
            else: return JSONResponse(status_code=400, content={"error": "not_enough_coins"})

        await session.commit()
        return {"status": "ok", "profile": {"coins": user.coins, "multi_tap": user.multi_tap, "max_energy": user.max_energy, "offline_miner_lvl": user.offline_miner_lvl}}

@app.get("/api/radar/list")
async def get_radar_list(chat_id: str = Query("0")):
    if not chat_id.isdigit(): return {"targets": []}
    async with async_session() as session:
        user = await get_or_create_user(session, int(chat_id))
        return {"targets": list(user.radar_targets or [])}

@app.get("/api/radar/add")
async def add_radar_target(chat_id: str = Query("0"), username: str = Query("")):
    if not chat_id.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_id"})
    user_id = int(chat_id)
    raw_user = username.replace("@", "").strip().lower()
    if not raw_user: return {"status": "error"}

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        now = int(time.time())
        is_pro = user.pro_until == -1 or user.pro_until > now
        max_slots = 100 if is_pro else (3 + user.radar_extra_slots)
        targets = list(user.radar_targets or [])
        if len(targets) >= max_slots:
            return JSONResponse(status_code=403, content={"error": "limit_reached", "msg": f"Лимит радара ({max_slots}) исчерпан!"})
        if raw_user not in targets:
            targets.append(raw_user)
            user.radar_targets = targets
            await session.commit()
        return {"status": "ok", "targets": targets}

@app.get("/api/radar/remove")
async def remove_radar_target(chat_id: str = Query("0"), username: str = Query("")):
    if not chat_id.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_id"})
    user_id = int(chat_id)
    raw_user = username.replace("@", "").strip().lower()

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        targets = list(user.radar_targets or [])
        if raw_user in targets:
            targets.remove(raw_user)
            user.radar_targets = targets
            await session.commit()
        return {"status": "ok", "targets": targets}

@app.get("/api/gifts/catalog")
async def get_gifts_catalog():
    return {"status": "ok", "catalog": GIFTS_CATALOG}

@app.post("/api/gifts/settings")
async def save_gift_settings(request: Request):
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    if not uid.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_id"})
    user_id = int(uid)

    async with async_session() as session:
        user = await get_or_create_user(session, user_id)
        now = int(time.time())
        is_pro = user.pro_until == -1 or user.pro_until > now
        if not is_pro and data.get("active", False):
            return JSONResponse(status_code=403, content={"error": "pro_required", "msg": "Снайпер Fragment доступен только в PRO!"})
        
        user.gift_radar_active = bool(data.get("active", False))
        user.gift_margin = int(data.get("margin", 30))
        user.gift_max_budget = int(data.get("max_budget", 10000))
        user.selected_gifts = list(data.get("gifts", []))
        await session.commit()
        return {"status": "ok"}

@app.get("/api/leaderboard")
async def get_leaderboard():
    async with async_session() as session:
        res = await session.execute(select(Leaderboard).order_by(Leaderboard.score.desc()).limit(100))
        entries = res.scalars().all()
        return {
            "status": "ok",
            "leaderboard": [
                {
                    "username": e.username, "rank": e.rank, "price": e.price,
                    "score": e.score, "color": e.color, "finder_name": e.finder_name,
                    "finder_id": e.finder_id
                }
                for e in entries
            ]
        }

@app.post("/api/pro/buy_invoice")
async def create_pro_invoice(request: Request):
    if not bot: return JSONResponse(status_code=400, content={"error": "bot_not_configured"})
    data = await request.json()
    uid = str(data.get("user_id", "")).strip()
    tariff_id = str(data.get("tariff_id", "pro_30"))
    tariff = TARRIFS.get(tariff_id)
    if not tariff or not uid.isdigit(): return JSONResponse(status_code=400, content={"error": "invalid_tariff"})

    try:
        invoice_link = await bot.create_invoice_link(
            title=tariff["title"], description="NameHunter PRO Доступ", payload=tariff_id,
            provider_token="", currency="XTR", prices=[LabeledPrice(label=tariff["title"], amount=tariff["stars"])]
        )
        return {"status": "ok", "invoice_link": invoice_link}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
