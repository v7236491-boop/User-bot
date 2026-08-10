import os
import random
import urllib.request
import urllib.error
import json
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Real Catch Value Username Generator")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

# 1. Знаменитости
CELEBRITIES = [
    "messi", "ronaldo", "neymar", "mbappe", "jordan", "musk", "jobs", "gates",
    "drake", "eminem", "rihanna", "bieber", "kanye", "pitt", "depp", "reeves"
]

# 2. Компании и бренды
COMPANIES = [
    "apple", "google", "nike", "adidas", "gucci", "prada", "tesla",
    "sony", "steam", "roblox", "nvidia", "rolex", "bmw", "binance"
]

OFFICIAL_PREFIXES = ["real", "iam", "the", "get", "try", "go", "my"]
OFFICIAL_SUFFIXES = ["official", "corp", "ltd", "store", "pay", "club", "vip", "lab"]

# 3. Эстетичные короткие корни
PREMIUM_ROOTS = [
    "aero", "alvo", "apex", "arch", "aura", "aera", "aster", "aevi",
    "bold", "byte", "cora", "crest", "cron", "cyra", "dusk", "drift",
    "elix", "echo", "enzo", "fable", "flux", "halo", "hyper", "iris",
    "kora", "koda", "lumi", "luxe", "mona", "myth", "nova", "nexus",
    "orion", "onyx", "pulse", "prism", "quill", "riva", "solis", "silk",
    "vortex", "velox", "vera", "vybe", "xenon", "zephyr", "zara", "zest"
]
PREMIUM_ENDINGS = ["lab", "hub", "net", "dev", "io", "one", "pro", "mode", "zone", "wave", "vibe", "flow", "mind", "soul", "core"]


def check_fragment_availability(username: str) -> bool:
    url = f"https://fragment.com/api?hash=search&query={username}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "X-Requested-With": "XMLHttpRequest"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode('utf-8'))
            html_res = data.get("html", "").lower()
            
            if username.lower() in html_res:
                if "tm-search-row" in html_res or "table-cell" in html_res:
                    return False
            return True
    except Exception:
        return True


def calculate_catch_score(username: str, is_free: bool, is_pure_brand: bool) -> dict:
    """
    Корректная объективная оценка ценности юзернейма
    """
    if not is_free:
        return {"rank": "F", "status": "Занят (0$)", "color": "#ef4444"}

    score = 0
    length = len(username)
    has_underscore = "_" in username

    # 1. Оценка длины (главный фактор ценности на рынке)
    if length <= 5:
        score += 500
    elif length == 6:
        score += 350
    elif length <= 8:
        score += 200
    elif length <= 10:
        score += 100
    else:
        score += 30

    # 2. Бонус за чистый бренд без приписок (например, чистый "tesla" или "messi")
    if is_pure_brand:
        score += 400
    elif any(b in username for b in COMPANIES + CELEBRITIES):
        score += 120  # Небольшой бонус за упоминание бренда/звезды со служебным словом

    # 3. Штраф за подчёркивание (чистые слитные слова ценятся выше)
    if has_underscore:
        score -= 80

    # Вывод ранга и корректной рыночной стоимости
    if score >= 700:
        return {"rank": "SSS+", "status": "Грааль рынка! (~1000-5000+$)", "color": "#2bcf66"}
    elif score >= 500:
        return {"rank": "SS", "status": "Премиум улов (~250-1000$)", "color": "#eab308"}
    elif score >= 350:
        return {"rank": "S", "status": "Редкий ник (~50-250$)", "color": "#a855f7"}
    elif score >= 200:
        return {"rank": "A", "status": "Хороший улов (~15-50$)", "color": "#06b6d4"}
    else:
        return {"rank": "B", "status": "Обычный логин (~5-15$)", "color": "#38bdf8"}


@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})


@app.get("/api/generate")
async def generate_username(platform: str = Query("telegram")):
    rand_val = random.random()
    is_pure_brand = False

    # 1. Генерация знаменитостей
    if rand_val < 0.30:
        celeb = random.choice(CELEBRITIES)
        fmt = random.choice(["pure", "official_under", "official_concat", "real", "prefix"])
        if fmt == "pure":
            generated = celeb
            is_pure_brand = True
        elif fmt == "official_under":
            generated = f"{celeb}_official"
        elif fmt == "official_concat":
            generated = f"{celeb}official"
        elif fmt == "real":
            generated = f"real{celeb}"
        else:
            generated = f"{random.choice(OFFICIAL_PREFIXES)}{celeb}"

    # 2. Генерация брендов и компаний
    elif rand_val < 0.60:
        brand = random.choice(COMPANIES)
        fmt = random.choice(["pure", "official_under", "official_concat", "real", "suffix"])
        if fmt == "pure":
            generated = brand
            is_pure_brand = True
        elif fmt == "official_under":
            generated = f"{brand}_official"
        elif fmt == "official_concat":
            generated = f"{brand}official"
        elif fmt == "real":
            generated = f"real{brand}"
        else:
            generated = f"{brand}_{random.choice(OFFICIAL_SUFFIXES)}"

    # 3. Абстрактные эстетичные ники
    else:
        root = random.choice(PREMIUM_ROOTS)
        ending = random.choice(PREMIUM_ENDINGS)
        generated = f"{root}{ending}"

    if platform == "whatsapp":
        is_free = True
        link = f"https://wa.me/{generated}"
    else:
        is_free = check_fragment_availability(generated)
        link = f"https://t.me/{generated}"

    catch_eval = calculate_catch_score(generated, is_free, is_pure_brand)
    return {
        "status": "success",
        "generated_username": generated,
        "platform": platform,
        "is_free": is_free,
        "evaluation": catch_eval,
        "link": link
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
