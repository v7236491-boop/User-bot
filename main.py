import os
import random
import urllib.request
import urllib.error
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Premium Telegram Username Generator")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

# Элитные короткие префиксы и суффиксы для сборки эстетичных юзернеймов
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

def check_tg_web_availability(username: str) -> bool:
    """
    Проверка занятости юзернейма через открытые сервера Telegram (t.me).
    Если Telegram возвращает 404 — юзернейм гарантированно свободен.
    """
    url = f"https://t.me/{username}"
    req = urllib.request.Request(
        url, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode('utf-8')
            # Если на странице есть упоминания о несуществующем аккаунте
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
    # Генерируем слитный, чистый юзернейм без цифр и подчёркиваний
    root = random.choice(PREMIUM_ROOTS)
    ending = random.choice(PREMIUM_ENDINGS)
    generated = f"{root}{ending}"

    # Проверяем реальную доступность в Telegram
    is_free = check_tg_web_availability(generated)

    return {
        "status": "success",
        "generated_username": generated,
        "is_free": is_free,
        "tg_link": f"https://t.me/{generated}"
    }


@app.get("/api/check")
async def check_username(username: str = Query(..., min_length=5, max_length=32)):
    clean = username.lstrip('@').lower()
    is_free = check_tg_web_availability(clean)
    return {
        "status": "success",
        "username": clean,
        "is_free": is_free,
        "tg_link": f"https://t.me/{clean}"
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
