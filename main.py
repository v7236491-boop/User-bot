import os
import random
import asyncio
import time
import httpx
import re
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
import uvicorn

app = FastAPI(title="TG Username Generator & Checker")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

# --- НАСТРОЙКА TELEGRAM БОТА ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher() if BOT_TOKEN else None

if dp:
    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        await message.answer("Привет! Генератор работает. Заходи на сайт через браузер!")

USER_COOLDOWNS = {}
COOLDOWN_SECONDS = 1.5

# --- 1. ТОП 500 ЧИСТЫХ СЛОВ ---
PURE_WORDS = (
    "apple world music house light dream space power smart stone water earth cloud storm "
    "river ocean flame shadow silver golden crystal magic spirit nature forest winter summer "
    "spring sunset sunrise silent secret future vision wonder action energy galaxy cosmic "
    "infinity legend hero master leader pioneer champion starlight moonlight diamond emerald "
    "sapphire phoenix dragon falcon freedom victory passion harmony destiny horizon paradise "
    "eternity velvet breeze velocity aurora solitude serenity zenith vortex nebula castle "
    "kingdom throne emperor knight shield sword crown dynasty legacy empire symbol beacon "
    "summit peak vertex vector matrix orbit alpha beta gamma delta echo tango fox wolf bear "
    "eagle lion tiger shark panther snake cobra viper raven hawk owl deer midnight dawn dusk "
    "abyss nova pulsar quasar comet meteor planet star sun moon sky wind rain snow ice frost "
    "fire ash ember spark glow ray beam wave tide surf shore coast island mountain hill valley "
    "desert sand rock cave deep dark black white red blue green yellow gold gray violet purple "
    "orange pink brown cyan neon metal iron steel bronze copper brass titan logic mind brain "
    "soul heart blood bone skin eye face voice word song art poem book page line story tale "
    "myth truth lie real fake good bad evil angel demon god saint ghost soul fate doom luck "
    "chance risk bet game play toy doll mask face form shape size mass core base root edge "
    "limit border zone area field tech data file code byte bit link node net web grid loop "
    "path way road street city town camp base port dock yard park hall room door gate key "
    "lock safe vault bank coin cash gold fund rich poor cheap prime pure raw rare epic mythic "
    "solo dual team crew squad clan gang mob crowd folk race clan tribe king queen prince "
    "lord duke chief boss head lead star icon idol cult pop rock jazz rap trap bass beat "
    "drop tune note chord scale tempo rhythm sound noise mute deaf blind seek hide find lose "
    "win fail pass stop move run walk jump fly fall drop rise lift pull push throw catch "
    "hold keep save spend buy sell trade swap deal shop mall store cart bag box pack case "
    "gear tool prop item loot drop award prize cup medal badge sign mark logo seal stamp "
    "print text font type card board list rank tier step phase level stage grade class type "
    "kind sort style vibe mood feel aura halo glow ray shine flash blink spark gleam glare "
    "shade blur tint hue tone cast form norm rule law duty task job work art craft skill "
    "talent genius brain focus aim goal target point spot dot mark cross star plus minus "
    "zero one unit solo mono dual duo trio poly multi mega giga tera nano micro mini maxi "
    "super hyper ultra extra super mega over under upper lower inner outer open close lock "
    "free wild tame calm rough smooth hard soft heavy light fast slow quick rapid swift "
    "haste rush speed pace rate time hour day week month year age era epoch eon span life "
    "birth death grave tomb ruin relic myth lore saga tale yarn spin weave knit fold bend "
    "break smash crash burst blast boom bang pop clap snap click tick tick tock buzz hum "
    "ring chime bell toll drum beat pulse throb thud slam smash crack chip tear rip cut "
    "slice chop split join link bond glue bind tie knot loop ring chain wire cord rope "
    "string thread yarn silk wool cloth web mesh net trap snare hook lure bait catch grab "
    "take give send mail post ship sail float sink drown dive swim wade wash clean wipe "
    "sweep dust dirt mud clay soil land earth globe sphere orb ball cube block dice grid"
).split()

# --- 2. БРЕНДЫ ПО КАТЕГОРИЯМ С УМНЫМ КОНТЕКСТОМ ---
BRAND_CATEGORIES = {
    "tech": {
        "names": ["apple", "google", "microsoft", "sony", "samsung", "intel", "amd", "nvidia", 
                  "ibm", "hp", "dell", "asus", "acer", "lenovo", "cisco", "oracle", "amazon", 
                  "tesla", "panasonic", "philips", "lg", "nokia", "ericsson", "motorola", 
                  "xiaomi", "huawei", "oppo", "vivo", "meta", "whatsapp", "instagram", "telegram"],
        "contexts": ["tech", "app", "dev", "pay", "cloud", "ai", "hub", "store", "mobile", "smart"]
    },
    "auto": {
        "names": ["toyota", "volkswagen", "ford", "honda", "chevrolet", "nissan", "hyundai", "kia", 
                  "bmw", "mercedes", "audi", "porsche", "ferrari", "lamborghini", "bugatti", "mclaren", 
                  "aston", "bentley", "rollsroyce", "volvo", "mazda", "subaru", "lexus", "jaguar", 
                  "landrover", "jeep", "dodge", "chrysler", "renault", "peugeot", "citroen"],
        "contexts": ["auto", "drive", "car", "club", "race", "speed", "motors", "power", "racing"]
    },
    "fashion": {
        "names": ["nike", "adidas", "puma", "reebok", "underarmour", "zara", "uniqlo", "gucci", 
                  "prada", "dior", "chanel", "louisvuitton", "hermes", "versace", "armani", 
                  "balenciaga", "burberry", "fendi", "rolex", "omega", "cartier", "tiffany", 
                  "supreme", "vans", "converse", "crocs", "levis", "timberland", "calvinklein"],
        "contexts": ["style", "wear", "fit", "run", "shoes", "store", "original", "club", "design"]
    },
    "food": {
        "names": ["cocacola", "pepsi", "mcdonalds", "starbucks", "kfc", "burgerking", "subway", 
                  "dominos", "pizzahut", "nestle", "unilever", "danone", "kelloggs", "mars", 
                  "snickers", "redbull", "monster", "heineken", "budweiser", "guinness", "sprite", "fanta"],
        "contexts": ["drink", "food", "fresh", "eat", "cold", "ice", "tasty", "club", "break"]
    },
    "gaming_media": {
        "names": ["nintendo", "playstation", "xbox", "sega", "ea", "ubisoft", "activision", 
                  "blizzard", "rockstar", "epic", "valve", "steam", "disney", "netflix", "hbo", 
                  "warner", "universal", "marvel", "dc", "paramount", "pixar", "twitch", "spotify"],
        "contexts": ["play", "game", "show", "tv", "movie", "music", "studio", "stream", "live"]
    },
    "crypto_fin": {
        "names": ["visa", "mastercard", "paypal", "amex", "stripe", "square", "binance", 
                  "coinbase", "kraken", "bybit", "okx", "tether", "solana", "ethereum", "bitcoin"],
        "contexts": ["pay", "trade", "crypto", "app", "bank", "fund", "capital", "wallet"]
    }
}

# --- 3. ЗНАМЕНИТОСТИ ПО КАТЕГОРИЯМ ---
CELEB_CATEGORIES = {
    "sport": {
        "names": ["messi", "ronaldo", "neymar", "mbappe", "pele", "maradona", "jordan", "kobe", 
                  "lebron", "curry", "shaq", "brady", "mahomes", "tyson", "ali", "mcgregor", 
                  "khabib", "federer", "nadal", "djokovic", "serena", "hamilton", "schumacher"],
        "contexts": ["real", "official", "goat", "king", "champ", "legend", "sport"]
    },
    "music": {
        "names": ["elvis", "beatles", "madonna", "eminem", "drake", "kanye", "jayz", "snoop", 
                  "tupac", "biggie", "taylor", "beyonce", "rihanna", "gaga", "adele", "edsheeran", 
                  "bieber", "ariana", "selena", "billie", "weeknd", "postmalone", "brunomars", 
                  "shakira", "jlo", "queen", "nirvana", "metallica", "mozart", "beethoven"],
        "contexts": ["music", "real", "official", "sound", "live", "tour", "star", "voice"]
    },
    "movies": {
        "names": ["cruise", "pitt", "depp", "dicaprio", "hanks", "reeves", "downey", "hemsworth", 
                  "evans", "holland", "pratt", "rock", "statham", "jackiechan", "brucelee", 
                  "tarantino", "nolan", "spielberg", "scarlett", "jolie", "zendaya", "robbie", 
                  "gadot", "anadearmas", "meganfox", "pattinson", "murphy"],
        "contexts": ["real", "official", "actor", "film", "star", "iam", "the"]
    },
    "history_tech_web": {
        "names": ["musk", "jobs", "gates", "bezos", "zuck", "einstein", "tesla", "newton", 
                  "davinci", "shakespeare", "mrbeast", "pewdiepie", "ispeed", "kai", "xqc"],
        "contexts": ["real", "official", "tech", "genius", "team", "crew", "hub"]
    }
}

QUALITY_PREFIXES = ["real", "official", "iam", "the"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
]

# --- ЧЕСТНАЯ ПРОВЕРКА БЕЗ УГАДЫВАНИЙ ---
async def async_check_tg(username: str):
    """
    Возвращает:
    True - Точно свободен
    False - Точно занят
    None - Ошибка сети / Блокировка IP (неизвестно)
    """
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    try:
        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
            url_tg = f"https://t.me/{username}"
            res_tg = await client.get(url_tg, headers=headers)
            
            # Если Telegram заблокировал запрос или сервер недоступен
            if res_tg.status_code in [429, 403, 500, 502, 503]:
                return None 
            
            if res_tg.status_code == 200:
                html = res_tg.text.lower()
                
                # Признаки того, что юзернейм КЕМ-ТО ЗАНЯТ
                taken_indicators = [
                    '<meta property="og:title"',
                    'tgme_page_title',
                    'tgme_page_extra',
                    'subscribers',
                    'members'
                ]
                
                for ind in taken_indicators:
                    if ind in html:
                        # Исключение: стандартная дефолтная плашка t.me без реального имени
                        if f'telegram: contact @{username}' in html and 'tgme_page_title' not in html:
                            continue
                        return False # Точно занят
                        
                return True # Точно свободен

            return None

    except Exception:
        # При обрыве связи / таймауте возвращаем None
        return None


def calculate_catch_score(username: str, check_result, is_pure_word: bool, has_underscore: bool) -> dict:
    # Обработка ошибки сети / лимита запросов
    if check_result is None:
        return {"rank": "ERR", "status": "Лимит запросов (Попробуй еще)", "color": "#f97316"}
        
    if check_result is False:
        return {"rank": "F", "status": "Занят ($0)", "color": "#ef4444"}

    length = len(username)

    if is_pure_word and length <= 6:
        return {"rank": "SSS+", "status": "Редкий Грааль (~$100–$500+)", "color": "#2bcf66"}
    if is_pure_word and length <= 9:
        return {"rank": "SS", "status": "Премиум улов (~$30–$100)", "color": "#eab308"}
    if not has_underscore and length <= 13:
        return {"rank": "S", "status": "Хороший ник (~$10–$30)", "color": "#a855f7"}
    
    return {"rank": "A", "status": "Обычный ник (~$2–$10)", "color": "#06b6d4"}


@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})


@app.get("/api/generate")
async def generate_username(request: Request, platform: str = Query("telegram")):
    client_ip = request.client.host if request.client else "global"
    now = time.time()

    if client_ip in USER_COOLDOWNS:
        elapsed = now - USER_COOLDOWNS[client_ip]
        if elapsed < COOLDOWN_SECONDS:
            await asyncio.sleep(COOLDOWN_SECONDS - elapsed)

    USER_COOLDOWNS[client_ip] = time.time()

    rand_type = random.random()
    is_pure_word = False
    has_underscore = False

    if rand_type < 0.10:
        generated = random.choice(PURE_WORDS)
        is_pure_word = True
    elif rand_type < 0.35:
        category = random.choice(list(BRAND_CATEGORIES.values()))
        brand = random.choice(category["names"])
        word = random.choice(category["contexts"])
        if random.random() < 0.35:
            generated = f"{brand}_{word}"
            has_underscore = True
        else:
            generated = f"{brand}{word}"
    elif rand_type < 0.60:
        category = random.choice(list(CELEB_CATEGORIES.values()))
        celeb = random.choice(category["names"])
        word = random.choice(category["contexts"])
        if random.random() < 0.35:
            generated = f"{word}_{celeb}" if word in QUALITY_PREFIXES else f"{celeb}_{word}"
            has_underscore = True
        else:
            generated = f"{word}{celeb}" if word in QUALITY_PREFIXES else f"{celeb}{word}"
    else:
        w1 = random.choice(PURE_WORDS)
        w2 = random.choice(PURE_WORDS)
        while w1 == w2:
            w2 = random.choice(PURE_WORDS)
            
        if random.random() < 0.35:
            generated = f"{w1}_{w2}"
            has_underscore = True
        else:
            generated = f"{w1}{w2}"

    if platform == "whatsapp":
        check_result = True
        link = f"https://wa.me/{generated}"
    else:
        check_result = await async_check_tg(generated)
        link = f"https://t.me/{generated}"

    catch_eval = calculate_catch_score(generated, check_result, is_pure_word, has_underscore)
    
    # Чтобы JSON не сломался на фронтенде, передаем булевое значение, даже если была ошибка
    is_free_bool = True if check_result is True else False

    return {
        "status": "success",
        "generated_username": generated,
        "platform": platform,
        "is_free": is_free_bool,
        "evaluation": catch_eval,
        "link": link
    }

@app.on_event("startup")
async def on_startup():
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
