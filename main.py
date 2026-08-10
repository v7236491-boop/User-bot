import os
import random
import asyncio
from typing import Optional
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Инициализация приложения FastAPI
app = FastAPI(
    title="Telegram Username Generator & Checker",
    description="Сервис для проверки и генерации свободных юзернеймов Telegram",
    version="1.0.0"
)

# Шаблонизатор настроен на ТЕКУЩУЮ папку (без папки templates)
templates = Jinja2Templates(directory=".")

# Словари для встроенной генерации
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
    """
    Отдает index.html прямо из корневой директории.
    """
    index_path = os.path.join(os.path.dirname(__file__), "index.html")
    if not os.path.exists(index_path):
        raise HTTPException(
            status_code=404, 
            detail="Файл index.html не найден в корневой папке проекта!"
        )
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/check")
async def check_username(username: str = Query(..., min_length=3, max_length=32)):
    """
    Основной эндпоинт проверки доступности юзернейма.
    """
    try:
        # Имитация паузы сети
        await asyncio.sleep(0.05)
        
        # Нормализация юзернейма (убираем @ если передали)
        clean_username = username.lstrip('@').lower()
        
        # Симуляция проверки (70% вероятность свободной клички)
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
    """
    Эндпоинт генерации случайной связки слов.
    """
    w1 = random.choice(PREFIXES)
    w2 = random.choice(SUFFIXES)
    generated = f"{w1}_{w2}"
    
    return {
        "status": "success",
        "generated_username": generated
    }

@app.get("/health")
async def health_check():
    """
    Проверка работоспособности сервера для Railway / Docker.
    """
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    # Локальный запуск
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)