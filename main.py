import asyncio
import os
import re
import time
import aiohttp
from aiohttp import web

# ==========================================
# 1. СЛОВАРИ И БАЗЫ ДАННЫХ (Расширенные)
# ==========================================

# Словарные популярные слова (проверяются строго без приписок)
DICTIONARY_WORDS = [
    "sun", "cat", "hello", "love", "sky", "time", "fire", "ice", "star", "moon",
    "king", "boss", "gold", "hero", "soul", "mind", "life", "word", "music", "game",
    "play", "code", "tech", "data", "web", "chat", "bot", "app", "dev", "soft",
    "core", "net", "link", "node", "fast", "cool", "top", "best", "super", "mega",
    "pro", "master", "vip", "club", "team", "group", "shop", "store", "deal", "cash",
    "coin", "bank", "pay", "trade", "work", "job", "space", "earth", "world", "city",
    "town", "road", "park", "home", "room", "desk", "book", "card", "note", "file",
    "view", "look", "site", "page", "news", "post", "blog", "feed", "live", "stream",
    "flow", "wave", "vibe", "zone", "spot", "base", "hub", "lab", "box", "drop"
]

# 100 Знаменитостей / Известных личностей
CELEBRITIES = [
    "cristiano", "ronaldo", "messi", "neymar", "mbappe", "haaland", "lebron", "curry",
    "jordan", "kobe", "tyson", "ali", "mcgregor", "khabib", "federer", "nadal",
    "musk", "jobs", "gates", "bezos", "zuckerberg", "buffett", "altman", "durov",
    "drake", "eminem", "kanye", "beyonce", "rihanna", "taylor", "gomez", "bieber",
    "theweeknd", "shakira", "adele", "bruno", "edward", "pitt", "dicaprio", "depp",
    "tomcruise", "keanu", "rock", "downey", "johansson", "zendaya", "robbie", "holland",
    "chalamet", "ramsay", "mrbeast", "pewdiepie", "khaby", "sergey", "pavel", "ilong",
    "obama", "trump", "biden", "putin", "xi", "modi", "macron", "scholz", "schwarzenegger",
    "stallone", "chan", "jetli", "statham", "reeves", "gosling", "hardy", "bale",
    "cavanill", "hemsworth", "hiddleston", "cumberbatch", "pattinson", "affleck", "cavill",
    "pratt", "evans", "gadot", "olsen", "pugh", "taylorjoy", "stone", "lawrence",
    "portman", "hatheway", "blunt", "theron", "berry", "jolie", "fox", "sweeney"
]

# 100 Популярных брендов
BRANDS = [
    "apple", "google", "microsoft", "amazon", "meta", "tesla", "spacex", "nvidia",
    "intel", "amd", "samsung", "sony", "lg", "huawei", "xiaomi", "asus", "acer",
    "dell", "hp", "lenovo", "nike", "adidas", "puma", "reebok", "jordan", "gucci",
    "louisvuitton", "chanel", "prada", "dior", "hermes", "rolex", "zara", "uniqlo",
    "bmw", "mercedes", "audi", "porsche", "ferrari", "lamborghini", "toyota", "honda",
    "ford", "chevrolet", "nissan", "hyundai", "kia", "volvo", "bentley", "bugatti",
    "cocacola", "pepsi", "redbull", "nestle", "starbucks", "mcdonalds", "kfc", "subway",
    "visa", "mastercard", "paypal", "stripe", "revolut", "binance", "bybit", "tether",
    "steam", "playstation", "xbox", "nintendo", "roblox", "epicgames", "twitch", "discord",
    "spotify", "netflix", "youtube", "tiktok", "instagram", "telegram", "reddit", "x",
    "openai", "anthropic", "uber", "airbnb", "booking", "amazon", "ebay", "shopify"
]

# 50 Смысловых приставок/суффиксов
AFFIXES = [
    "official", "real", "the", "iam", "is", "original", "daily", "live", "news",
    "club", "team", "fan", "hub", "zone", "net", "app", "dev", "media", "studio",
    "lab", "world", "space", "life", "vibe", "tv", "page", "blog", "feed", "channel",
    "press", "hq", "corp", "inc", "group", "pro", "master", "vip", "top", "prime",
    "star", "one", "go", "now", "me", "io", "ai", "tech", "box", "spot"
]

# ==========================================
# 2. КЭШ, ОГРАНИЧЕНИЕ ЗАПРОСОВ И ПРОВЕРКИ
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

# ==========================================
# 3. ФИКС ОШИБКИ PORT НА RAILWAY
# ==========================================

async def handle_ping(request):
    """Эндпоинт для проверки работоспособности серверами Railway."""
    return web.Response(text="Bot is running smoothly!", status=200)

async def start_healthcheck_server():
    """Фоновый сервер, слушающий порт PORT от Railway."""
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_get('/health', handle_ping)
    
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    print(f"[Railway] Healthcheck server started on port {port}")

# ==========================================
# 4. ОСНОВНАЯ ТОЧКА ВХОДА
# ==========================================

async def main():
    # 1. Запуск веб-сервера для Railway
    await start_healthcheck_server()
    
    # 2. Инициализация объекта проверки
    checker = UsernameChecker()
    
    print("[System] Checker initialized. Starting main task loop...")
    
    # Здесь подключается запуск вашего бота (например, dp.start_polling) 
    # или выполнение тестов логики:
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
