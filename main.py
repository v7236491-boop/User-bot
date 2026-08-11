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

# --- 1. ТОП ЧИСТЫЕ СЛОВА ---
PURE_WORDS = [
    "apple", "world", "music", "house", "light", "dream", "space", "power", "smart",
    "stone", "water", "earth", "cloud", "storm", "river", "ocean", "flame", "shadow", "silver",
    "golden", "crystal", "magic", "spirit", "nature", "forest", "winter", "summer", "spring",
    "sunset", "sunrise", "silent", "secret", "future", "vision", "wonder", "action", "energy",
    "galaxy", "cosmic", "infinity", "legend", "hero", "master", "leader", "pioneer", "champion",
    "starlight", "moonlight", "diamond", "emerald", "sapphire", "phoenix", "dragon", "falcon",
    "freedom", "victory", "passion", "harmony", "destiny", "horizon", "paradise", "eternity",
    "velvet", "breeze", "velocity", "aurora", "solitude", "serenity", "zenith", "vortex", "nebula",
    "castle", "kingdom", "throne", "emperor", "knight", "shield", "sword", "crown", "dynasty",
    "legacy", "empire", "symbol", "beacon", "summit", "peak", "vertex", "vector", "matrix", "orbit"
]

# --- 2. БРЕНДЫ С КОНТЕКСТНЫМИ СУФФИКСАМИ ---
BRAND_CONTEXTS = {
    "sony": ["camera", "audio", "sound", "tv", "play", "music", "studio"],
    "coca": ["drink", "cola", "cold", "fresh", "ice", "glass"],
    "subway": ["sandwich", "fresh", "eat", "food"],
    "nike": ["run", "shoes", "sport", "snkrs", "air", "fit"],
    "adidas": ["original", "shoes", "sport", "run"],
    "tesla": ["car", "auto", "drive", "energy", "power", "tech"],
    "apple": ["store", "app", "tech", "dev", "pay", "mac", "ios"],
    "google": ["dev", "tech", "cloud", "search", "app", "pay"],
    "rolex": ["watch", "time", "gold", "club"],
    "ferrari": ["auto", "race", "speed", "red", "club"],
    "bmw": ["auto", "m", "power", "club", "drive"],
    "porsche": ["auto", "club", "race", "speed"],
    "samsung": ["mobile", "tech", "pay", "tv"],
    "redbull": ["racing", "energy", "drink", "air"],
    "binance": ["pay", "trade", "crypto", "app", "lab"],
    "bybit": ["trade", "crypto", "app", "pay"],
    "spotify": ["music", "sound", "app", "podcast"],
    "netflix": ["show", "tv", "movie", "app"],
    "razer": ["tech", "game", "zone", "gear"],
    "steam": ["deck", "game", "pay", "community"]
}

# --- 3. ЗНАМЕНИТОСТИ С КОНТЕКСТНЫМИ ПРИСТАВКАМИ/СУФФИКСАМИ ---
CELEB_CONTEXTS = {
    "messi": ["real", "official", "leo", "goat", "king", "ten"],
    "ronaldo": ["real", "official", "cr7", "goat", "king"],
    "jordan": ["air", "shoes", "real", "goat", "twentythree"],
    "musk": ["real", "elon", "tech", "x"],
    "drake": ["real", "official", "champagne", "music"],
    "eminem": ["real", "official", "slim", "shady"],
    "kanye": ["real", "ye", "west", "music"],
    "keanu": ["real", "reeves", "official"],
    "mrbeast": ["real", "official", "feast", "team"]
}

QUALITY_PREFIXES = ["real", "official", "iam", "the"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

# --- ИДЕАЛЬНАЯ ПРОВЕРКА (ИЗ ПРЕДЫДУЩЕЙ РАБОЧЕЙ ВЕРСИИ) ---
async def async_check_tg(username: str) -> bool:
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
            # 1. Проверка Telegram (t.me)
            url_tg = f"https://t.me/{username}"
            res_tg = await client.get(url_tg, headers=headers)
            html_tg = res_tg.text.lower()

            tg_taken_keywords = [
                "tgme_page_title", "tgme_page_extra", "send message",
                "you can contact", "subscribers", "members", "view in telegram",
                "if you have telegram, you can contact"
            ]
            if any(kw in html_tg for kw in tg_taken_keywords):
                if '<meta property="og:title"' in html_tg and 'telegram: contact' not in html_tg:
                    return False
                if "subscribers" in html_tg or "members" in html_tg or "you can contact @" in html_tg:
                    return False

            await asyncio.sleep(0.3)

            # 2. Проверка Fragment (fragment.com)
            url_frag = f"https://fragment.com/username/{username}"
            res_frag = await client.get(url_frag, headers=headers)
            html_frag = res_frag.text.lower()

            frag_taken_keywords = [
                "unavailable", "taken", "auction", "sold", "on sale",
                "minimum bid", "place bid", "owner", "buy now"
            ]
            if any(kw in html_frag for kw in frag_taken_keywords):
                return False

            return True

    except Exception:
        return False


def calculate_catch_score(username: str, is_free: bool, is_pure_word: bool, has_underscore: bool) -> dict:
    """
    Консервативная и реальная система оценки стоимости юзернеймов
    """
    if not is_free:
        return {"rank": "F", "status": "Занят ($0)", "color": "#ef4444"}

    length = len(username)

    if is_pure_word and length <= 5:
        return {"rank": "SSS+", "status": "Редкий Грааль (~$100–$500+)", "color": "#2bcf66"}

    if is_pure_word and length <= 7:
        return {"rank": "SS", "status": "Премиум улов (~$30–$100)", "color": "#eab308"}

    if not has_underscore and length <= 10:
        return {"rank": "S", "status": "Хороший ник (~$10–$30)", "color": "#a855f7"}

    if has_underscore or length > 10:
        return {"rank": "A", "status": "Обычный ник (~$2–$10)", "color": "#06b6d4"}

    return {"rank": "B", "status": "Базовый логин (~$0–$5)", "color": "#6b7280"}


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
    is_pure_word = False
    has_underscore = False

    if rand_type < 0.40:
        generated = random.choice(PURE_WORDS)
        is_pure_word = True
    elif rand_type < 0.70:
        brand, contexts = random.choice(list(BRAND_CONTEXTS.items()))
        word = random.choice(contexts)
        if random.random() < 0.35:
            generated = f"{brand}_{word}"
            has_underscore = True
        else:
            generated = f"{brand}{word}"
    else:
        celeb, contexts = random.choice(list(CELEB_CONTEXTS.items()))
        word = random.choice(contexts)
        if random.random() < 0.35:
            generated = f"{word}_{celeb}" if word in QUALITY_PREFIXES else f"{celeb}_{word}"
            has_underscore = True
        else:
            generated = f"{word}{celeb}" if word in QUALITY_PREFIXES else f"{celeb}{word}"

    if platform == "whatsapp":
        is_free = True
        link = f"https://wa.me/{generated}"
    else:
        is_free = await async_check_tg(generated)
        link = f"https://t.me/{generated}"

    catch_eval = calculate_catch_score(generated, is_free, is_pure_word, has_underscore)

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
