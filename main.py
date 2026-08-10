import os
import random
import asyncio
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Telegram Username Generator")

# Ищем шаблоны прямо в текущей папке
templates = Jinja2Templates(directory=".")

PREFIXES = ["vibe", "neo", "cyber", "meta", "hyper", "crypto", "retro", "synth"]
SUFFIXES = ["coder", "dev", "punk", "whale", "ninja", "guru", "forge", "wave"]

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Просто отдаем index.html из корня
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/check")
async def check_username(username: str = Query(..., min_length=3, max_length=32)):
    await asyncio.sleep(0.05)
    clean_username = username.lstrip('@').lower()
    is_free = random.random() > 0.3
    return {"status": "success", "username": clean_username, "is_free": is_free}

@app.get("/api/generate")
async def generate_username():
    generated = f"{random.choice(PREFIXES)}_{random.choice(SUFFIXES)}"
    return {"status": "success", "generated_username": generated}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)