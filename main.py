import os
import random
import urllib.request
import urllib.error
import json
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Multi-Platform Username Checker")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

CELEBRITIES = [
    "messi", "ronaldo", "neymar", "mbappe", "jordan", "musk", "jobs", "gates",
    "drake", "eminem", "rihanna", "bieber", "kanye", "pitt", "depp", "reeves"
]

COMPANIES = [
    "apple", "google", "nike", "adidas", "gucci", "prada", "tesla",
    "sony", "steam", "roblox", "nvidia", "rolex", "bmw", "binance"
]

PREFIXES = ["real", "the", "official", "get", "try", "go", "my", "app"]
SUFFIXES = ["official", "inc", "ltd", "corp", "co", "app", "hub", "club", "vip"]

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

def check_tg_web(username: str) -> bool:
    """Шаг 1: Быстрая веб-проверка через t.me"""
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
        return True

def check_fragment(username: str) -> bool:
    """Шаг 2: Глубокая проверка через Fragment.com"""
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
            html_res = data.get("html", "")
            if username.lower() in html_res.lower() and ("Unavailable" in html_res or "Taken" in html_res or "Sold" in html_res or "On auction" in html_res):
                return False
            return True
    except Exception:
        return True

def check_double_telegram(username: str) -> bool:
    """Двойная проверка Telegram: сначала t.me, потом Fragment"""
    if not check_tg_web(username):
        return False
    return check_fragment(username)

def calculate_catch_score(username: str, is_free: bool, is_brand: bool) -> dict:
    if not is_free:
        return {"rank": "F", "status": "Занят (0$)", "color": "#ef4444"}

    score = 100
    if is_brand:
        score += 450
    if len(username) <= 6:
        score += 350
    elif len(username) <= 8:
        score += 200

    if score >= 550:
        return {"rank": "SSS+", "status": "Бренд-улов! (~500-2500+$)", "color": "#2bcf66"}
    elif score >= 400:
        return {"rank": "SS", "status": "Эпический улов! (~150-500$)", "color": "#a855f7"}
    elif score >= 250:
        return {"rank": "S", "status": "Редкий улов (~40-150$)", "color": "#06b6d4"}
    else:
        return {"rank": "A", "status": "Хороший ник (~10-40$)", "color": "#22c55e"}

@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})

@app.get("/api/generate")
async def generate_username(platform: str = Query("telegram")):
    rand_val = random.random()
    is_brand_gen = False

    if rand_val < 0.25:
        brand = random.choice(COMPANIES)
        is_brand_gen = True
        generated = f"{brand}{random.choice(SUFFIXES)}"
    elif rand_val < 0.50:
        celeb = random.choice(CELEBRITIES)
        is_brand_gen = True
        generated = f"{random.choice(PREFIXES)}{celeb}"
    else:
        root = random.choice(PREMIUM_ROOTS)
        ending = random.choice(PREMIUM_ENDINGS)
        generated = f"{root}{ending}"

    if platform == "whatsapp":
        # Проверка для WhatsApp (открытый роут генерации)
        is_free = True
        link = f"https://wa.me/{generated}"
    else:
        # Двойная проверка Telegram (t.me -> Fragment)
        is_free = check_double_telegram(generated)
        link = f"https://t.me/{generated}"

    catch_eval = calculate_catch_score(generated, is_free, is_brand_gen)

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
