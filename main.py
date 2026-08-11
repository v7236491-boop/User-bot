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

app = FastAPI(title="Username Generator & Checker")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")

# --- НАСТРОЙКА TELEGRAM БОТА ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher() if BOT_TOKEN else None

if dp:
    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        await message.answer("Привет! Генератор работает.")

USER_COOLDOWNS = {}
COOLDOWN_SECONDS = 1.0

# --- БАЗЫ ДАННЫХ ---
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

BRAND_CATEGORIES = {
    "tech": {"names": ["apple", "google", "microsoft", "sony", "samsung", "intel", "amd", "nvidia"], "contexts": ["tech", "app", "dev", "pay", "cloud"]},
    "auto": {"names": ["toyota", "volkswagen", "ford", "honda", "bmw", "mercedes", "audi", "porsche"], "contexts": ["auto", "drive", "car", "club", "race"]},
    "fashion": {"names": ["nike", "adidas", "puma", "gucci", "prada", "dior", "chanel"], "contexts": ["style", "wear", "fit", "run", "shoes"]},
    "food": {"names": ["cocacola", "pepsi", "mcdonalds", "starbucks", "subway"], "contexts": ["drink", "food", "fresh", "eat", "cold"]},
    "crypto": {"names": ["binance", "coinbase", "kraken", "bybit", "tether", "solana"], "contexts": ["pay", "trade", "crypto", "app"]}
}

CELEB_CATEGORIES = {
    "sport": {"names": ["messi", "ronaldo", "neymar", "mbappe", "jordan", "kobe", "lebron"], "contexts": ["real", "official", "goat", "king", "champ"]},
    "music": {"names": ["eminem", "drake", "kanye", "taylor", "beyonce", "rihanna", "bieber"], "contexts": ["music", "real", "official", "sound", "live"]},
    "movies": {"names": ["cruise", "pitt", "depp", "dicaprio", "reeves", "downey", "holland"], "contexts": ["real", "official", "actor", "film", "star"]}
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
]

# --- ДВОЙНАЯ ПРОВЕРКА TELEGRAM ---
async def async_check_tg(username: str):
    # МЕТОД 1: Bot API
    if BOT_TOKEN:
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                res = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChat?chat_id=@{username}")
                if res.status_code == 200 and res.json().get("ok"):
                    return False
        except Exception:
            pass

    # МЕТОД 2: t.me
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
            res = await client.get(f"https://t.me/{username}", headers=headers)
            if res.status_code in [429, 403, 500, 502, 503]:
                return None
            if res.status_code == 200:
                html = res.text.lower()
                taken_indicators = ['<meta property="og:title"', 'tgme_page_title', 'tgme_page_extra', 'subscribers', 'members']
                for ind in taken_indicators:
                    if ind in html:
                        if f'telegram: contact @{username}' in html and 'tgme_page_title' not in html:
                            continue
                        return False
                return True
            return None
    except Exception:
        return None

# --- ДВОЙНАЯ ПРОВЕРКА WHATSAPP ---
async def async_check_wa(username: str):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    # МЕТОД 1: Проверка через wa.me
    try:
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
            url_wa = f"https://wa.me/{username}"
            res_wa = await client.get(url_wa, headers=headers)

            if res_wa.status_code == 200:
                html = res_wa.text.lower()

                # Если сработал блок Cloudflare / капча
                if "just a moment..." in html or "cf-challenge" in html or "attention required!" in html:
                    pass # Пробуем метод 2
                else:
                    invalid_indicators = [
                        "url is invalid", "invalid url", "page not found", 
                        "страница не найдена", "недействительный адрес"
                    ]
                    if any(ind in html for ind in invalid_indicators):
                        return True # Свободен

                    taken_indicators = [
                        "action_button", "send_message", "continue to chat", 
                        "перейти в чат", "chat on whatsapp"
                    ]
                    if any(ind in html for ind in taken_indicators):
                        return False # Занят

            if res_wa.status_code == 404:
                return True
    except Exception:
        pass

    # МЕТОД 2: Резервная проверка через api.whatsapp.com
    try:
        async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
            url_api = f"https://api.whatsapp.com/send/?phone={username}&text&type=phone_number&app_absent=0"
            res_api = await client.get(url_api, headers=headers)

            if res_api.status_code == 200:
                html_api = res_api.text.lower()
                
                if "phone number shared via url is invalid" in html_api or "invalid" in html_api:
                    return True # Свободен
                if "action_button" in html_api or "continue to chat" in html_api:
                    return False # Занят

            if res_api.status_code == 404:
                return True
    except Exception:
        pass

    # Если оба метода не смогли дать точный ответ из-за ошибок/лимитов
    return None

def calculate_catch_score(username: str, check_result, is_pure: bool, has_und: bool):
    if check_result is None:
        return {"rank": "ERR", "status": "Лимит запросов", "color": "#f97316"}
    if check_result is False:
        return {"rank": "F", "status": "Занят ($0)", "color": "#ef4444"}

    length = len(username)
    if is_pure and length <= 6:
        return {"rank": "SSS+", "status": "Грааль (~$100+)", "color": "#2bcf66"}
    if is_pure and length <= 9:
        return {"rank": "SS", "status": "Премиум (~$30+)", "color": "#eab308"}
    return {"rank": "S", "status": "Хороший ник (~$5+)", "color": "#a855f7"}

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
    is_pure, has_und = False, False

    if rand_type < 0.20:
        generated = random.choice(PURE_WORDS)
        is_pure = True
    elif rand_type < 0.60:
        cat = random.choice(list(BRAND_CATEGORIES.values()))
        b, c = random.choice(cat["names"]), random.choice(cat["contexts"])
        generated = f"{b}_{c}" if random.random() < 0.5 else f"{b}{c}"
        has_und = "_" in generated
    else:
        cat = random.choice(list(CELEB_CATEGORIES.values()))
        c, w = random.choice(cat["names"]), random.choice(cat["contexts"])
        generated = f"{c}_{w}" if random.random() < 0.5 else f"{c}{w}"
        has_und = "_" in generated

    if platform == "whatsapp":
        check_result = await async_check_wa(generated)
        link = f"https://wa.me/{generated}"
    else:
        check_result = await async_check_tg(generated)
        link = f"https://t.me/{generated}"

    is_free_bool = True if check_result is True else False

    return {
        "status": "success",
        "generated_username": generated,
        "platform": platform,
        "is_free": is_free_bool,
        "evaluation": calculate_catch_score(generated, check_result, is_pure, has_und),
        "link": link
    }

@app.on_event("startup")
async def on_startup():
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
