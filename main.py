import os
import random
import urllib.request
import urllib.error
import json
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Real Fragment & TG Username Checker")

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
    "aero", "alvo", "apex", "arch", "aura", "aster", "byte", "cora",
    "crest", "dusk", "drift", "elix", "echo", "flux", "halo", "hyper",
    "lumi", "luxe", "nova", "nexus", "orion", "onyx", "pulse", "prism",
    "vortex", "velox", "xenon", "zephyr"
]

PREMIUM_ENDINGS = ["lab", "hub", "net", "app", "dev", "io", "one", "pro", "mode", "zone", "wave", "vibe"]

def check_fragment_availability(username: str) -> bool:
    """
    Точная проверка доступности юзернейма через поиск Fragment.com (официальный сервис Telegram)
    """
    url = f"https://fragment.com/api?hash=search&query={username}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Requested-With": "XMLHttpRequest"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode('utf-8'))
            # Если в ответе есть таблицы/строки с занятыми или продающимися юзернеймами — он занят
            html_res = data.get("html", "")
            if username.lower() in html_res.lower() and ("Unavailable" in html_res or "Taken" in html_res or "Sold" in html_res or "On auction" in html_res):
                return False
            # Если Fragment ничего не нашел или отдал пустой результат — имя не зарегистрировано
            return True
    except Exception:
        # Резервная проверка через прямой веб t.me с точным заголовком
        try:
            tg_url = f"https://t.me/{username}"
            tg_req = urllib.request.Request(tg_url, headers={"User-Agent": "TelegramBot (like TwitterBot)"})
            with urllib.request.urlopen(tg_req, timeout=3) as res:
                page = res.read().decode('utf-8')
                if "tgme_page_title" in page or "extra_info" in page:
                    return False
                return True
        except Exception:
            return False

def calculate_catch_score(username: str, is_free: bool, is_brand: bool) -> dict:
    if not is_free:
        return {"rank": "F", "status": "Занят в Telegram (0$)", "color": "#ef4444"}

    score = 100
    if is_brand:
        score += 450
    if len(username) <= 6:
        score += 350
    elif len(username) <= 8:
        score += 200

    if score >= 550:
        return {"rank": "SSS+", "status": "Бренд / Редкий улов! (~500-2000+$)", "color": "#eab308"}
    elif score >= 400:
        return {"rank": "SS", "status": "Эпический улов! (~100-500$)", "color": "#a855f7"}
    elif score >= 250:
        return {"rank": "S", "status": "Редкий улов (~30-100$)", "color": "#06b6d4"}
    else:
        return {"rank": "A", "status": "Хороший ник (~10-30$)", "color": "#22c55e"}

@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})

@app.get("/api/generate")
async def generate_username():
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
        generated = f"{random.choice(PREMIUM_ROOTS)}{random.choice(PREMIUM_ENDINGS)}"

    is_free = check_fragment_availability(generated)
    catch_eval = calculate_catch_score(generated, is_free, is_brand_gen)

    return {
        "status": "success",
        "generated_username": generated,
        "is_free": is_free,
        "evaluation": catch_eval,
        "tg_link": f"https://t.me/{generated}"
    }

@app.get("/api/check")
async def check_username(username: str = Query(..., min_length=3, max_length=32)):
    clean = username.lstrip('@').lower()
    is_brand = any(b in clean for b in COMPANIES) or any(c in clean for c in CELEBRITIES)
    is_free = check_fragment_availability(clean)
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
