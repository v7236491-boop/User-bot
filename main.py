import os
import random
import asyncio
from typing import Optional
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(
    title="Telegram Username Generator & Checker",
    description="Сервис для проверки и генерации свободных юзернеймов Telegram",
    version="1.0.0"
)

templates = Jinja2Templates(directory=".")

PREFIXES = [
    "vibe", "neo", "cyber", "meta", "hyper", 
    "crypto", "retro", "synth", "pixel", "dark",
    "alpha", "prime", "shadow", "ghost", "vector"
]

SUFFIXES = [
    "coder", "dev", "punk", "whale", "ninja", 
    "guru", "forge", "wave", "phantom", "logic",
    "lab", "hub", "node", "craft", "pulse"
]

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(
            status_code=404, 
            detail="Файл index.html не найден в корневой папке проекта!"
        )
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/check")
async def check_username(username: str = Query(..., min_length=3, max_length=32)):
    try:
        await asyncio.sleep(0.05)
        clean_username = username.lstrip('@').lower()
        is_free = random.random() > 0.3
        return {
            "status": "success",
            "username": clean_username,
            "is_free": is_free
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.get("/api/generate")
async def generate_username():
    w1 = random.choice(PREFIXES)
    w2 = random.choice(SUFFIXES)
    generated = f"{w1}_{w2}"
    return {
        "status": "success",
        "generated_username": generated
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)