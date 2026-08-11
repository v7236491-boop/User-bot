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

# --- 1. ТОП ЧИСТЫЕ СЛОВА (БЕЗ ПРИСТАВОК И СИМВОЛОВ) ---
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

# --- 2. БРЕНДЫ С КОНТЕКСТНЫМИ СУФФИКСАМИ (СМЫСЛОВЫЕ СВЯЗКИ) ---
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
    "eminem", ["real", "official", "slim", "shady"],
    "kanye": ["real", "ye", "west", "music"],
    "keanu": ["real", "reeves", "official"],
    "mrbeast": ["real", "official", "feast", "team"]
}

# Дополнительные нейтральные префиксы высокого качества
QUALITY_PREFIXES = ["real", "official", "iam", "the"]


async def async_check_tg(username: str) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=3.0, follow_redirects=True) as client:
            url_tg = f"https://t.me/{username}"
            res_tg = await client.get(url_tg, headers=headers)
            html_tg = res_tg.text.lower()

            if "tgme_page_title" in html_tg or "you can contact @" in html_tg or "extra_state" in html_tg:
                return False

            await asyncio.sleep(0.2)

            url_frag = f"https://fragment.com/username/{username}"
            res_frag = await client.get(url_frag, headers=headers)
            html_frag = res_frag.text.lower()

            if "status-taken" in html_frag or "status-sold" in html_frag or "status-bidding" in html_frag:
                return False

            return True
    except Exception:
        return True


def calculate_catch_score(username: str, is_free: bool, is_pure_word: bool, has_underscore: bool) -> dict:
    """
    Консервативная и реальная система оценки стоимости юзернеймов
    """
    if not is_free:
        return {"rank": "F", "status": "Занят ($0)", "color": "#ef4444"}

    length = len(username)

    # 1. Топовые короткие чистые слова без символов (Редчайшие)
    if is_pure_word and length <= 5:
        return {"rank": "SSS+", "status": "Редкий Грааль (~$100–$500+)", "color": "#2bcf66"}

    # 2. Чистые слова или очень короткие комбинации без подчёркиваний
    if is_pure_word and length <= 7:
        return {"rank": "SS", "status": "Премиум улов (~$30–$100)", "color": "#eab308"}

    # 3. Осмысленные комбинации без подчёркиваний
    if not has_underscore and length <= 10:
        return {"rank": "S", "status": "Хороший ник (~$10–$30)", "color": "#a855f7"}

    # 4. Все комбинации с подчёркиваниями или длинные имена
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
        # 1. Чистые красивые слова (Самый высокий шанс получить ценный ник)
        generated = random.choice(PURE_WORDS)
        is_pure_word = True
    elif rand_type < 0.70:
        # 2. Бренды с осмысленными контекстными словами (e.g. sony_camera)
        brand, contexts = random.choice(list(BRAND_CONTEXTS.items()))
        word = random.choice(contexts)
        
        if random.random() < 0.35:
            generated = f"{brand}_{word}"
            has_underscore = True
        else:
            generated = f"{brand}{word}"
    else:
        # 3. Знаменитости с контекстными префиксами/суффиксами (e.g. real_messi)
        celeb, contexts = random.choice(list(CELEBRITIES_CONTEXTS.items() if 'CELEBRITIES_CONTEXTS' in globals() else CELEB_CONTEXTS.items()))
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
