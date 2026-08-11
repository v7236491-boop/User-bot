import asyncio
import re
import time
import aiohttp

# ==========================================
# 1. СЛОВАРИ И БАЗЫ ДАННЫХ
# ==========================================

# Словарные популярные слова (проверяются strictly без приписок и без '_')
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
    "coca-cola", "pepsi", "redbull", "nestle", "starbucks", "mcdonalds", "kfc", "subway",
    "visa", "mastercard", "paypal", "stripe", "revolut", "binance", "bybit", "tether",
    "steam", "playstation", "xbox", "nintendo", "roblox", "epicgames", "twitch", "discord",
    "spotify", "netflix", "youtube", "tiktok", "instagram", "telegram", "reddit", "x",
    "openai", "anthropic", "uber", "airbnb", "booking", "amazon", "ebay", "shopify"
]

# 50 Смысловых приставок/суффиксов (для имен и брендов)
AFFIXES = [
    "official", "real", "the", "iam", "is", "original", "daily", "live", "news",
    "club", "team", "fan", "hub", "zone", "net", "app", "dev", "media", "studio",
    "lab", "world", "space", "life", "vibe", "tv", "page", "blog", "feed", "channel",
    "press", "hq", "corp", "inc", "group", "pro", "master", "vip", "top", "prime",
    "star", "one", "go", "now", "me", "io", "ai", "tech", "box", "spot"
]


# ==========================================
# 2. КЭШ И ОГРАНИЧЕНИЕ ЗАПРОСОВ (RATE LIMIT)
# ==========================================

class UsernameChecker:
    def __init__(self, cache_ttl: int = 3600, min_delay: float = 1.5):
        self.cache = {}  # {username: (is_free, timestamp)}
        self.cache_ttl = cache_ttl
        self.min_delay = min_delay
        self.user_last_request = {}  # {user_id: timestamp}

    def _clean_cache(self):
        now = time.time()
        self.cache = {
            k: v for k, v in self.cache.items()
            if now - v[1] < self.cache_ttl
        }

    async def apply_rate_limit(self, user_id: int):
        """Индивидуальная задержка для каждого пользователя."""
        now = time.time()
        last_req = self.user_last_request.get(user_id, 0)
        elapsed = now - last_req
        if elapsed < self.min_delay:
            await asyncio.sleep(self.min_delay - elapsed)
        self.user_last_request[user_id] = time.time()


# ==========================================
# 3. АСИНХРОННАЯ ПРОВЕРКА (t.me + Fragment)
# ==========================================

    async def check_telegram_web(self, session: aiohttp.ClientSession, username: str) -> bool:
        """
        Проверка через t.me.
        Возвращает True, если ник СВОБОДЕН.
        """
        url = f"https://t.me/{username}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    text = await response.text()
                    # Если на странице есть заголовок профиля/канала или кнопка открытия - он занят
                    if "tgme_page_title" in text or "tgme_action_button_new" in text:
                        return False
                    # Если перенаправляет на специфический инфо-блок — свободен
                    if "If you have Telegram, you can contact" in text or "extra_small" in text:
                        return True
                    return True
                elif response.status == 404:
                    return True
                return False
        except Exception:
            return False

    async def check_fragment(self, session: aiohttp.ClientSession, username: str) -> bool:
        """
        Проверка через Fragment.
        Возвращает True, если ник СВОБОДЕН (не продается, не куплен, не на аукционе).
        """
        url = f"https://fragment.com/username/{username}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            async with session.get(url, headers=headers, timeout=5) as response:
                if response.status == 200:
                    text = await response.text()
                    # Маркеры занятости на Fragment: аукцион, продан, зарезервирован
                    if "On auction" in text or "Sold" in text or "Unavailable" in text or "Taken" in text:
                        return False
                    return True
                elif response.status == 404:
                    return True
                return False
        except Exception:
            return False

    async def is_username_free(self, user_id: int, username: str, session: aiohttp.ClientSession) -> bool:
        """Комплексная проверка с кэшем, задержкой и запросами."""
        username = username.lower().strip("@")
        self._clean_cache()

        # Проверка кэша
        if username in self.cache:
            return self.cache[username][0]

        # Применение задержки пользователя
        await self.apply_rate_limit(user_id)

        # Параллельный запрос к t.me и Fragment
        tg_free, fragment_free = await asyncio.gather(
            self.check_telegram_web(session, username),
            self.check_fragment(session, username)
        )

        is_free = tg_free and fragment_free

        # Запись результата в кэш
        self.cache[username] = (is_free, time.time())
        return is_free


# ==========================================
# 4. ОЦЕНКА ЦЕННОСТИ (SCORING)
# ==========================================

def calculate_username_value(username: str, category: str) -> dict:
    """
    Рассчитывает ориентировочную стоимость и ценность юзернейма.
    """
    clean_name = username.lower().replace("_", "")
    length = len(clean_name)
    has_underscore = "_" in username
    
    score = 100
    
    # Категория словарного слова ценится максимально
    if category == "dictionary":
        score += 500
        estimated_price = "$500 - $5,000+"
    elif category == "celebrity" or category == "brand":
        score += 200
        estimated_price = "$100 - $1,500"
    else:
        estimated_price = "$20 - $200"

    # Штрафы за длину и подчёркивания
    if length <= 4:
        score += 300
    elif length <= 6:
        score += 100
    else:
        score -= (length - 6) * 10

    if has_underscore:
        score -= 50

    score = max(score, 10)
    
    return {
        "username": username,
        "score": score,
        "estimated_value": estimated_price,
        "has_underscore": has_underscore,
        "length": length
    }


# ==========================================
# 5. ГЕНЕРАЦИЯ ВАРИАНТОВ ЮЗЕРНЕЙМОВ
# ==========================================

def generate_username_candidates() -> list:
    """
    Генерирует список кандидатов:
    - Словарные слова: только чистые имена.
    - Знаменитости и бренды: чистые имена + осмысленные приставки.
    """
    candidates = []

    # 1. Словарные слова (Strictly без приставок и подчёркиваний)
    for word in DICTIONARY_WORDS:
        candidates.append((word, "dictionary"))

    # 2. Знаменитости
    for celeb in CELEBRITIES:
        candidates.append((celeb, "celebrity"))
        for affix in AFFIXES:
            candidates.append((f"{affix}_{celeb}", "celebrity_affix"))
            candidates.append((f"{celeb}_{affix}", "celebrity_affix"))
            candidates.append((f"{affix}{celeb}", "celebrity_affix"))

    # 3. Бренды
    for brand in BRANDS:
        candidates.append((brand, "brand"))
        for affix in AFFIXES:
            candidates.append((f"{affix}_{brand}", "brand_affix"))
            candidates.append((f"{brand}_{affix}", "brand_affix"))
            candidates.append((f"{brand}{affix}", "brand_affix"))

    return candidates
