import asyncio
import os
import time
import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# ==========================================
# 1. НАСТРОЙКА БОТА И ПЕРЕМЕННЫХ
# ==========================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ВАШ_ТОКЕН_БОТА")
WEBHOOK_HOST = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "") # Railway автоматически подставляет домен
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{WEBHOOK_HOST}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ==========================================
# 2. КЭШ И ОГРАНИЧЕНИЕ ЗАПРОСОВ (ЧЕКЕР)
# ==========================================

class UsernameChecker:
    def __init__(self, cache_ttl: int = 3600, min_delay: float = 1.5):
        self.cache = {}
        self.cache_ttl = cache_ttl
        self.min_delay = min_delay
        self.user_last_request = {}

    def _clean_cache(self):
        now = time.time()
        self.cache = {k: v for k, v in self.cache.items() if now - v[1] < self.cache_ttl}

    async def apply_rate_limit(self, user_id: int):
        now = time.time()
        last_req = self.user_last_request.get(user_id, 0)
        elapsed = now - last_req
        if elapsed < self.min_delay:
            await asyncio.sleep(self.min_delay - elapsed)
        self.user_last_request[user_id] = time.time()

    async def check_telegram_web(self, session: aiohttp.ClientSession, username: str) -> bool:
        url = f"https://t.me/{username}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    text = await response.text()
                    if "tgme_page_title" in text or "tgme_action_button_new" in text:
                        return False
                    return True
                elif response.status == 404:
                    return True
                return False
        except Exception:
            return False

    async def check_fragment(self, session: aiohttp.ClientSession, username: str) -> bool:
        url = f"https://fragment.com/username/{username}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    text = await response.text()
                    if any(marker in text for marker in ["On auction", "Sold", "Unavailable", "Taken"]):
                        return False
                    return True
                elif response.status == 404:
                    return True
                return False
        except Exception:
            return False

    async def is_username_free(self, user_id: int, username: str, session: aiohttp.ClientSession) -> bool:
        username = username.lower().strip("@")
        self._clean_cache()

        if username in self.cache:
            return self.cache[username][0]

        await self.apply_rate_limit(user_id)

        tg_free, fragment_free = await asyncio.gather(
            self.check_telegram_web(session, username),
            self.check_fragment(session, username)
        )

        is_free = tg_free and fragment_free
        self.cache[username] = (is_free, time.time())
        return is_free

checker = UsernameChecker()

# ==========================================
# 3. ОБРАБОТЧИКИ КОМАНД БОТА
# ==========================================

@dp.message()
async def handle_message(message: types.Message):
    # Обязательно отвечать сразу, чтобы избежать ошибки "Приложение не ответило"
    user_id = message.from_user.id
    text = message.text.strip()
    
    if text.startswith("/start"):
        await message.answer("Привет! Отправь мне юзернейм для проверки.")
        return

    msg = await message.answer("Проверяю юзернейм...")
    
    async with aiohttp.ClientSession() as session:
        is_free = await checker.is_username_free(user_id, text, session)
        
    if is_free:
        await msg.edit_text(f"Юзернейм @{text} свободен!")
    else:
        await msg.edit_text(f"Юзернейм @{text} занят или недоступен.")

# ==========================================
# 4. ЗАПУСК ВЕБ-СЕРВЕРА С WEBHOOK
# ==========================================

async def on_startup(bot: Bot) -> None:
    # Установка Webhook при запуске
    await bot.set_webhook(WEBHOOK_URL)
    print(f"[Webhook] Установлен на {WEBHOOK_URL}")

def main():
    dp.startup.register(on_startup)

    app = web.Application()

    # Настройка обработки Webhook от Telegram
    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)

    # Дополнительный эндпоинт для проверки от Railway
    app.router.add_get("/", lambda r: web.Response(text="OK"))

    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
