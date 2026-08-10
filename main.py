import asyncio
import aiohttp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ограничения по длине для площадок
CONSTRAINTS = {
    'telegram': {'min': 5, 'max': 32},
    'github': {'min': 1, 'max': 39},
    'whatsapp': {'min': 1, 'max': 25}
}

class UsernameRequest(BaseModel):
    username: str

async def check_github(session: aiohttp.ClientSession, username: str) -> str:
    if not (CONSTRAINTS['github']['min'] <= len(username) <= CONSTRAINTS['github']['max']):
        return "Недопустимая длина"
    
    url = f"https://api.github.com/users/{username}"
    try:
        async with session.get(url) as response:
            return "Свободен" if response.status == 404 else "Занят"
    except Exception:
        return "Ошибка соединения"

async def check_telegram(session: aiohttp.ClientSession, username: str) -> str:
    if not (CONSTRAINTS['telegram']['min'] <= len(username) <= CONSTRAINTS['telegram']['max']):
        return "Недопустимая длина"
    
    url = f"https://t.me/{username}"
    try:
        async with session.get(url) as response:
            text = await response.text()
            return "Свободен" if 'tgme_page_title' not in text else "Занят"
    except Exception:
        return "Ошибка соединения"

async def check_whatsapp(username: str) -> str:
    # Заглушка. Требуется интеграция WhatsApp Business API или Playwright
    await asyncio.sleep(0.5) 
    return "Требуется API интеграция"

"/api/check"
async def check_username_api(request: UsernameRequest):
    username = request.username.lower().strip()
    
    if not username:
        raise HTTPException(status_code=400, detail="Юзернейм не может быть пустым")

    async with aiohttp.ClientSession() as session:
        tasks = {
            "Telegram": check_telegram(session, username),
            "GitHub": check_github(session, username),
            "WhatsApp": check_whatsapp(username)
        }
        
        results = await asyncio.gather(*tasks.values())
        return {"username": username, "results": dict(zip(tasks.keys(), results))}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)