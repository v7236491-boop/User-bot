import os
import random
import asyncio
import httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Fast & Non-Blocking Telegram Username Generator")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

RARE_PREFIXES = [
    "aero", "alvo", "apex", "arch", "aura", "aera", "aster", "aevi",
    "bold", "byte", "cora", "crest", "cron", "cyra", "dusk", "drift",
    "elix", "echo", "enzo", "fable", "flux", "halo", "hyper", "iris",
    "kora", "koda", "lumi", "luxe", "mona", "myth", "nova", "nexus",
    "orion", "onyx", "pulse", "prism", "quill", "riva", "solis", "silk",
    "vortex", "velox", "vera", "vybe", "xenon", "zephyr", "zara", "zest"
]

RARE_SUFFIXES = [
    "lab", "hub", "net", "dev", "io", "one", "pro", "mode",
    "zone", "wave", "vibe", "flow", "mind", "soul", "core"
]

BRANDS = ["nike", "adidas", "gucci", "prada", "tesla", "sony", "rolex", "bmw", "binance", "messi", "drake"]
BRAND_MODS = ["hub", "club", "zone", "wave", "flow", "core"]


async def async_check_tg(username: str) -> bool:
    """
    Асинхронная неблокирующая проверка через httpx.
    Исключает падения сервера в 502 Bad Gateway.
    """
    url = f"https://t.me/{username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        async with httpx.AsyncClient(timeout=1.5, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            html = response.text.lower()
            
            # Признаки того, что аккаунт/канал зарегистрирован
            if "tgme_page_title" in html or "tgme_page_extra" in html or "send message" in html:
                if "you can contact @" in html or "subscribers" in html or "members" in html:
                    return False
                if '<meta property="og:title"' in html:
                    return False
            return True

    except Exception:
        # При таймауте или ошибке сети возвращаем False (безопасный режим без падения 502)
        return False


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

    if any(b in username for b in BRANDS):
        score += 150

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
async def generate_username(platform: str = Query("telegram")):
    rand_val = random.random()

    if rand_val < 0.85:
        prefix = random.choice(RARE_PREFIXES)
        suffix = random.choice(RARE_SUFFIXES)
        generated = f"{prefix}{suffix}"
    else:
        brand = random.choice(BRANDS)
        mod = random.choice(BRAND_MODS)
        generated = f"{brand}_{mod}"

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
