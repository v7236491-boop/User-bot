import os
import random
import asyncio
import time
import httpx
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import uvicorn

app = FastAPI(title="TG Username Generator & Checker")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

# --- НАСТРОЙКА TELEGRAM БОТА ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher() if BOT_TOKEN else None

if dp:
    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        await message.answer("Привет! Генератор юзернеймов работает. Заходи на сайт через браузер!")

# --- СИСТЕМА КУЛДАУНА (RATE LIMITING) ---
USER_COOLDOWNS = {}
COOLDOWN_SECONDS = 1.5

# --- СЛОВАРНЫЕ БАЗЫ ---
DICTIONARY_WORDS = [
    "apple", "world", "music", "house", "light", "dream", "space", "power", "angel", "smart",
    "stone", "water", "earth", "cloud", "storm", "river", "ocean", "flame", "shadow", "silver",
    "golden", "crystal", "magic", "spirit", "nature", "forest", "winter", "summer", "spring", "autumn",
    "sunset", "sunrise", "silent", "secret", "future", "vision", "wonder", "action", "energy", "planet",
    "galaxy", "cosmic", "infinity", "legend", "hero", "master", "leader", "pioneer", "champion", "winner",
    "starlight", "moonlight", "diamond", "emerald", "sapphire", "phoenix", "dragon", "tiger", "falcon", "eagle",
    "freedom", "victory", "passion", "harmony", "destiny", "horizon", "paradise", "eternity", "miracle", "treasure",
    "velvet", "breeze", "velocity", "aurora", "solitude", "serenity", "zenith", "vortex", "nebula", "element",
    "castle", "kingdom", "throne", "emperor", "knight", "shield", "sword", "crown", "monarch", "dynasty",
    "legacy", "empire", "symbol", "beacon", "summit", "peak", "vertex", "vector", "matrix", "orbit"
]

COMPANIES = [
    "apple", "google", "nike", "adidas", "gucci", "prada", "tesla", "sony",
    "steam", "roblox", "nvidia", "intel", "canon", "rolex", "porsche", "ferrari",
    "bmw", "audi", "redbull", "binance", "bybit", "openai", "uber", "spotify",
    "netflix", "tiktok", "amazon", "dior", "samsung", "puma", "microsoft",
    "meta", "toyota", "honda", "mercedes", "volkswagen", "ford",
    "chevrolet", "nissan", "hyundai", "kia", "lexus", "bentley", "lamborghini", "bugatti",
    "mclaren", "aston", "chanel", "louisvuitton", "hermes", "versace", "armani", "balenciaga",
    "burberry", "fendi", "omega", "cartier", "seiko", "casio", "pepsi",
    "cocacola", "monster", "starbucks", "mcdonalds", "kfc", "subway", "burgerking",
    "twitch", "discord", "youtube", "telegram", "whatsapp", "instagram", "twitter", "reddit",
    "snapchat", "pinterest", "linkedin", "shazam", "tinder", "airbnb", "booking",
    "stripe", "paypal", "revolut", "wise", "coinbase", "kraken", "okx", "kucoin",
    "asus", "msi", "gigabyte", "razer", "logitech", "corsair", "hyperx", "steelseries"
]

CELEBRITIES = [
    "messi", "ronaldo", "neymar", "mbappe", "jordan", "kobe", "lebron", "musk",
    "jobs", "gates", "bezos", "altman", "zuck", "drake", "eminem", "rihanna",
    "bieber", "kanye", "beyonce", "shakira", "pitt", "depp", "reeves", "dicaprio",
    "zendaya", "gadot", "robbie", "batman", "joker", "spidey", "haaland", "vinicius",
    "bellingham", "modric", "kroos", "benzema", "lewandowski", "salah", "debruyne", "kane",
    "curry", "durant", "giannis", "doncic", "jokic", "federer", "nadal", "djokovic",
    "hamilton", "verstappen", "snoop", "fiftycent", "jayz", "weeknd", "postmalone", "travis",
    "brunomars", "edsheeran", "adele", "taylor", "dualipa", "billie", "gomez", "grande",
    "tomcruise", "rock", "statham", "keanu", "rdj", "hemsworth", "evans", "holland",
    "chalamet", "ramsey", "pascal", "jenna", "sydney", "ana", "scarlett",
    "margot", "pewdiepie", "mrbeast", "ispeed", "ksi", "logan", "jake",
    "xqc", "kai", "ninja", "shroud", "pokimane", "rubius", "ibai", "grefg"
]

MODIFIERS = [
    "official", "real", "original", "true", "pro", "vip", "club", "live", "app", "dev",
    "io", "hub", "lab", "labs", "net", "mode", "zone", "vibe", "flow", "space", "craft",
    "base", "sync", "link", "desk", "box", "drop", "nest", "forge", "site", "web", "cloud",
    "group", "studio", "tech", "soft", "ai", "media", "agency", "team", "crew", "house",
    "world", "verse", "realm", "spot", "node", "loop", "line", "gate"
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]


async def async_check_tg(username: str) -> bool:
    """
    Точная проверка свободен ли username в Telegram и на Fragment
    """
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            # 1. Проверка через t.me
            url_tg = f"https://t.me/{username}"
            res_tg = await client.get(url_tg, headers=headers)
            html_tg = res_tg.text.lower()

            # Точные индикаторы занятого канала/профиля/бота
            if "tgme_page_title" in html_tg:
                # Если есть заголовок страницы с именем, логин точно занят
                return False
            if "you can contact @" in html_tg or "extra_state" in html_tg:
                return False

            await asyncio.sleep(0.2)

            # 2. Проверка через Fragment
            url_frag = f"https://fragment.com/username/{username}"
            res_frag = await client.get(url_frag, headers=headers)
            html_frag = res_frag.text.lower()

            # Если на Fragment написано, что ник был продан или находится на аукционе
            if "status-taken" in html_frag or "status-sold" in html_frag or "status-bidding" in html_frag:
                return False
            if "unclaimed" in html_frag or "available" in html_frag:
                return True

            return True

    except Exception:
        # В случае таймаута пропускаем статус как потенциально свободный
        return True


def calculate_catch_score(username: str, is_free: bool) -> dict:
    if not is_free:
        return {"rank": "F", "status": "Занят (0$)", "color": "#ef4444"}

    length = len(username)
    score = 100

    if length <= 6:
        score += 450
    elif length <= 8:
        score += 250
    elif length <= 10:
        score += 100

    if score >= 500:
        return {"rank": "SSS+", "status": "Редкий Грааль! (~300-1000+$)", "color": "#2bcf66"}
    elif score >= 350:
        return {"rank": "SS", "status": "Премиум улов (~100-300$)", "color": "#eab308"}
    elif score >= 200:
        return {"rank": "S", "status": "Хороший ник (~30-100$)", "color": "#a855f7"}
    else:
        return {"rank": "A", "status": "Достойный логин (~10-30$)", "color": "#06b6d4"}


@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})


@app.get("/api/generate")
async def generate_username(request: Request, platform: str = Query("telegram")):
    client_ip = request.client.host if request.client else "global"
    now = time.time()

    if client_ip in USER_COOLDOWNS:
        elapsed = now - USER_COOLDOWNS[client_ip]
        if elapsed < COOLDOWN_SECONDS:
            await asyncio.sleep(COOLDOWN_SECONDS - elapsed)

    USER_COOLDOWNS[client_ip] = time.time()

    rand_type = random.random()

    if rand_type < 0.35:
        generated = random.choice(DICTIONARY_WORDS)
    elif rand_type < 0.65:
        brand = random.choice(COMPANIES)
        mod = random.choice(MODIFIERS)
        use_underscore = random.random() < 0.4
        sep = "_" if use_underscore else ""
        generated = f"{brand}{sep}{mod}" if random.random() < 0.5 else f"{mod}{sep}{brand}"
    else:
        celeb = random.choice(CELEBRITIES)
        mod = random.choice(MODIFIERS)
        use_underscore = random.random() < 0.4
        sep = "_" if use_underscore else ""
        generated = f"{celeb}{sep}{mod}" if random.random() < 0.5 else f"{mod}{sep}{celeb}"

    if platform == "whatsapp":
        is_free = True
        link = f"https://wa.me/{generated}"
    else:
        is_free = await async_check_tg(generated)
        link = f"https://t.me/{generated}"

    catch_eval = calculate_catch_score(generated, is_free)

    return {
        "status": "success",
        "generated_username": generated,
        "platform": platform,
        "is_free": is_free,
        "evaluation": catch_eval,
        "link": link
    }


@app.on_event("startup")
async def on_startup():
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
