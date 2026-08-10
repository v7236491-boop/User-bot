import os
import random
import asyncio
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Telegram Username Generator")

# Определяем точный абсолютный путь к index.html
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")


@app.get("/")
async def read_root():
    # Отдаем файл напрямую без сторонних шаблонизаторов
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(
        status_code=404,
        content={"error": f"Файл index.html не найден по пути: {INDEX_PATH}"}
    )


@app.get("/api/check")
async def check_username(username: str = Query(..., min_length=3, max_length=32)):
    await asyncio.sleep(0.05)
    clean_username = username.lstrip('@').lower()
    is_free = random.random() > 0.3
    return {"status": "success", "username": clean_username, "is_free": is_free}


@app.get("/api/generate")
async def generate_username():
    prefixes = ["vibe", "neo", "cyber", "meta", "hyper", "crypto", "retro", "synth"]
    suffixes = ["coder", "dev", "punk", "whale", "ninja", "guru", "forge", "wave"]
    generated = f"{random.choice(prefixes)}_{random.choice(suffixes)}"
    return {"status": "success", "generated_username": generated}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
