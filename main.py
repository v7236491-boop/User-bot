import os
import random
import urllib.request
import urllib.error
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Brands & Celebrity Telegram Generator")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

# 1. Знаменитости
CELEBRITIES = [
    "messi", "ronaldo", "neymar", "mbappe", "jordan", "kobe", "leBron",
    "musk", "jobs", "gates", "bezos", "altman", "zuck", "turing",
    "drake", "eminem", "rihanna", "bieber", "kanye", "beyonce", "shakira",
    "pitt", "depp", "reeves", "dicaprio", "zendaya", "gadot", "robbie",
    "batman", "joker", "spidey", "potter", "vader", "neo", "gandalf"
]

# 2. Известные компании, бренды и IT-гиганты
COMPANIES = [
    "apple", "google", "nike", "adidas", "gucci", "prada", "tesla",
    "sony", "steam", "roblox", "nvidia", "intel", "canon", "rolex",
    "porsche", "ferrari", "bmw", "audi", "redbull", "binance", "bybit",
    "openai", "uber", "spotify", "netflix", "tiktok", "amazon", "dior"
]

BRAND_PREFIXES = ["real", "the", "official", "get", "try", "go", "my", "app"]
BRAND_SUFFIXES = ["official", "inc", "ltd", "corp", "co", "pay", "app", "hub", "lab", "club", "vip"]

# 3. Эстетичные короткие корни и суффиксы
PREMIUM_ROOTS = [
    "aero", "alvo", "apex", "arch", "aura", "aera", "aster", "aevi",
    "bold", "byte", "cora", "crest", "cron", "cyra", "dusk", "drift",
    "elix", "echo", "enzo", "fable", "flux", "halo", "hyper", "iris",
    "kora", "koda", "lumi", "luxe", "mona", "myth", "nova", "nexus",
    "orion", "onyx", "pulse", "prism", "quill", "riva", "solis", "silk",
    "vortex", "velox", "vera", "vybe", "xenon", "zephyr", "zara", "zest"
]

PREMIUM_ENDINGS = [
    "lab", "hub", "net", "app", "dev", "io", "one", "pro",
    "mode", "zone", "wave", "vibe", "flow", "mind", "soul", "core"
]

TOP_TIER_WORDS = ["apex", "aura", "luxe", "nova", "onyx", "silk", "vortex", "hyper", "cyber"]


def calculate_catch_score(username: str, is_free: bool, is_valuable_brand: bool) -> dict:
    """
    Рассчитывает ценность улова юзернейма
    """
    if not is_free:
        return {"rank": "F", "score": 0, "status": "Занят (0$)", "color": "#718096"}

    score = 100
    length = len(username)

    # Оценка брендов и звезд
    if is_valuable_brand:
        score += 500

    # Оценка длины
    if length <= 6:
        score += 350
    elif length <= 8:
        score += 200
    elif length <= 10:
        score += 100

    # Элитные слова
    for top_word in TOP_TIER_WORDS:
        if top_word in username:
            score += 150

    if score >= 550:
        return {"rank": "SSS+", "score": score, "status": "Бренд-улов! (~500-2500+$)", "color": "#FFD700"}
    elif score >= 400:
        return {"rank": "SS", "score": score, "status": "Эпический улов! (~150-500$)", "color": "#E066FF"}
    elif score >= 250:
        return {"rank": "S", "score": score, "status": "Редкий улов (~40-150$)", "color": "#00E5FF"}
    else:
        return {"rank": "A", "score": score, "status": "Хороший ник (~10-40$)", "color": "#00FF7F"}


def check_tg_web_availability(username: str) -> bool:
    url = f"https://t.me/{username}"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode('utf-8')
            if "If you have Telegram, you can contact" not in html and "tgme_page_title" not in html:
                return True
            return False
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return True
        return False
    except Exception:
        return False


@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})


@app.get("/api/generate")
async def generate_username():
    rand_val = random.random()
    is_brand_gen = False

    # 25% Шанс сгенерировать брендовый юзернейм (Apple, Nike, Tesla)
    # 25% Шанс сгенерировать юзернейм знаменитости (Messi, Musk)
    # 50% Шанс сгенерировать премиальный абстрактный ник
    if rand_val < 0.25:
        brand = random.choice(COMPANIES)
        is_brand_gen = True
        mode = random.choice(["pure", "prefix", "suffix"])
        if mode == "pure":
            generated = brand
        elif mode == "prefix":
            generated = f"{random.choice(BRAND_PREFIXES)}{brand}"
        else:
            generated = f"{brand}{random.choice(BRAND_SUFFIXES)}"
    elif rand_val < 0.50:
        celeb = random.choice(CELEBRITIES)
        is_brand_gen = True
        mode = random.choice(["pure", "prefix", "suffix"])
        if mode == "pure":
            generated = celeb
        elif mode == "prefix":
            generated = f"{random.choice(BRAND_PREFIXES)}{celeb}"
        else:
            generated = f"{celeb}{random.choice(BRAND_SUFFIXES)}"
    else:
        root = random.choice(PREMIUM_ROOTS)
        ending = random.choice(PREMIUM_ENDINGS)
        generated = f"{root}{ending}"

    is_free = check_tg_web_availability(generated)
    catch_eval = calculate_catch_score(generated, is_free, is_brand_gen)

    return {
        "status": "success",
        "generated_username": generated,
        "is_free": is_free,
        "is_brand": is_brand_gen,
        "evaluation": catch_eval,
        "tg_link": f"https://t.me/{generated}"
    }


@app.get("/api/check")
async def check_username(username: str = Query(..., min_length=3, max_length=32)):
    clean = username.lstrip('@').lower()
    is_brand = any(b in clean for b in COMPANIES) or any(c in clean for c in CELEBRITIES)
    is_free = check_tg_web_availability(clean)
    catch_eval = calculate_catch_score(clean, is_free, is_brand)
    
    return {
        "status": "success",
        "username": clean,
        "is_free": is_free,
        "evaluation": catch_eval,
        "tg_link": f"https://t.me/{clean}"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
