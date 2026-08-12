import os
import random
import asyncio
import time
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from aiogram import Bot, Dispatcher
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import RPCError, FloodWaitError
from telethon.tl.functions.account import CheckUsernameRequest
import uvicorn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
RADAR_DB_PATH = os.path.join(BASE_DIR, "radar_db.json")

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID", "38162572"))
API_HASH = os.getenv("API_HASH", "71b8ecb44bddc1ae0a802f4a0f6628ba")
SESSION_STRING = os.getenv("TELEGRAM_SESSION")

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None
dp = Dispatcher() if BOT_TOKEN else None

if SESSION_STRING:
    telethon_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    telethon_client = TelegramClient('checker_session', API_ID, API_HASH)

USER_COOLDOWNS = {}
COOLDOWN_SECONDS = 0.3

# --- LIFESPAN MANAGER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("⏳ Запуск Telethon сессии...")
    await telethon_client.start()
    print("✅ Telethon сессия успешно запущена!")
    
    asyncio.create_task(radar_worker())
    if bot and dp:
        asyncio.create_task(dp.start_polling(bot))
    
    yield
    
    print("🛑 Остановка Telethon...")
    await telethon_client.disconnect()

app = FastAPI(title="Username Generator & Checker PRO", lifespan=lifespan)

# --- РАДАР ОПЕРАЦИИ ---
def load_radar_db():
    if os.path.exists(RADAR_DB_PATH):
        try:
            with open(RADAR_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_radar_db(db):
    try:
        with open(RADAR_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

async def radar_worker():
    while True:
        try:
            db = load_radar_db()
            if not db or not bot:
                await asyncio.sleep(10)
                continue

            for chat_id, targets in list(db.items()):
                for username in targets:
                    is_free = await check_username_telethon(username)
                    if is_free is True:
                        try:
                            await bot.send_message(
                                chat_id=int(chat_id),
                                text=f"🚨 **РАДАР: НИК ОСВОБОДИЛСЯ!**\n\nНикнейм: `@{username}`\nБыстрее забирай его!",
                                parse_mode="Markdown"
                            )
                            db[chat_id].remove(username)
                            save_radar_db(db)
                        except Exception as e:
                            print(f"Ошибка отправки радара: {e}")
                    await asyncio.sleep(3)
        except Exception as e:
            print(f"Ошибка воркера радара: {e}")
        await asyncio.sleep(10)

# --- ПРОВЕРКА TELETHON ---
async def check_username_telethon(username: str):
    username = username.replace("@", "").strip().lower()
    if len(username) < 5:
        return False

    try:
        result = await telethon_client(CheckUsernameRequest(username=username))
        return result
    except FloodWaitError as e:
        print(f"FloodWait: ждем {e.seconds} сек.")
        return None
    except RPCError as e:
        print(f"RPC Ошибка: {e}")
        return False
    except Exception as e:
        print(f"Ошибка проверки {username}: {e}")
        return None

# --- СЛОВАРЬ И БРЕНДЫ ДЛЯ СТАНДАРТНОГО РЕЖИМА ---
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
    "fashion": {"names": ["nike", "adidas", "puma", "gucci", "prada", "dior", "chanel"], "contexts": ["style", "wear", "fit", "run", "shoes"]}
}

# --- БАЗА КРАСИВЫХ И ЗВУЧНЫХ СЛОГОВ ДЛЯ УМНОГО ФИЛЬТРА ---
EASY_SYLLABLES = [
    "ma", "re", "ki", "so", "lu", "ta", "ve", "zi", "no", "pa", "ro", "mi", "da", "bu",
    "ne", "ly", "xo", "fa", "gi", "ka", "lo", "mu", "na", "ra", "se", "ti", "vo", "za",
    "art", "ox", "ice", "sky", "pro", "zen", "neo", "fly", "lex", "vibe", "pulse", "crest",
    "fay", "sol", "lum", "dex", "rix", "vaz", "miz", "zor", "vol", "xir", "val", "cor"
]

CONSONANTS_EASY = "bcdfgklmnprstvwz"
VOWELS_EASY = "aeiouy"

# --- УМНЫЙ ГЕНЕРАТОР ЧИТАЕМЫХ НИКНЕЙМОВ ---
def generate_smart_username(len_mode: str, use_num: bool, use_und: bool) -> tuple[str, bool, bool]:
    # Установка целевой длины
    if len_mode == "5-6":
        target_len = random.choice([5, 6])
    elif len_mode == "7-8":
        target_len = random.choice([7, 8])
    else:
        target_len = random.choice([5, 6, 7])

    # 70% случаев — генерация из бренд-слогов, 30% — паттерн CVCVC (чередование)
    if random.random() < 0.7:
        res = ""
        while len(res) < target_len:
            syl = random.choice(EASY_SYLLABLES)
            if len(res) + len(syl) <= target_len + 1:
                res += syl
            else:
                break
        while len(res) < target_len:
            res += random.choice(VOWELS_EASY if len(res) % 2 == 1 else CONSONANTS_EASY)
    else:
        res = ""
        start_with_consonant = random.choice([True, False])
        for i in range(target_len):
            if (i % 2 == 0 and start_with_consonant) or (i % 2 == 1 and not start_with_consonant):
                res += random.choice(CONSONANTS_EASY)
            else:
                res += random.choice(VOWELS_EASY)

    res = res[:target_len]

    # Добавление разделителей или цифр (если включено пользователем)
    if use_und and len(res) >= 5:
        pos = random.randint(2, len(res) - 2)
        res = res[:pos] + "_" + res[pos+1:]

    if use_num and len(res) >= 5:
        num = str(random.randint(1, 99))
        res = res[:-len(num)] + num

    return res, True, use_und

# --- ТОЧНАЯ ОЦЕНКА ЦЕННОСТИ НИКА ---
def calculate_catch_score(username: str, check_result, is_pure: bool, has_und: bool):
    if check_result is None: 
        return {"rank": "ERR", "status": "Лимит", "color": "#f97316", "score": 0}
    if check_result is False: 
        return {"rank": "F", "status": "Занят", "color": "#ef4444", "score": 0}
    
    username = username.lower().replace("@", "").strip()
    length = len(username)
    vowels = set("aeiouy")
    
    has_num = any(char.isdigit() for char in username)
    vowel_count = sum(1 for c in username if c in vowels)
    vowel_ratio = vowel_count / length if length > 0 else 0
    
    score = 50
    if length <= 4: score += 45
    elif length == 5: score += 30
    elif length == 6: score += 15
    
    if is_pure: score += 20
    if not has_und and not has_num: score += 15
    if 0.3 <= vowel_ratio <= 0.6: score += 10  # Оптимальная читаемость
    
    if has_num: score -= 20
    if has_und: score -= 15

    if score >= 85:
        rank, color = "SSS+", "#29c75f"
        price = "Fragment (~150+ TON)" if length <= 5 else "Fragment (~30-80 TON)"
    elif score >= 70:
        rank, color = "SS", "#eab308"
        price = "Fragment (~15-40 TON)" if length <= 5 else "Редкий актив (~5-15 TON)"
    elif score >= 55:
        rank, color = "S", "#a855f7"
        price = "Красивый ник (~3-10 TON)"
    else:
        rank, color = "A", "#3b82f6"
        price = "Обычный ник"

    return {
        "rank": rank,
        "status": price if check_result is True else "Занят",
        "color": color,
        "score": score
    }

# --- МАРШРУТЫ API ---
@app.get("/")
async def read_root():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html не найден"})

@app.get("/api/generate")
async def generate_username(
    request: Request, 
    platform: str = Query("telegram"),
    use_filter: bool = Query(False),
    len_mode: str = Query("5-6"),
    use_num: bool = Query(False),
    use_und: bool = Query(False)
):
    client_ip = request.client.host if request.client else "global"
    now = time.time()
    if client_ip in USER_COOLDOWNS:
        elapsed = now - USER_COOLDOWNS[client_ip]
        if elapsed < COOLDOWN_SECONDS:
            await asyncio.sleep(COOLDOWN_SECONDS - elapsed)
    USER_COOLDOWNS[client_ip] = time.time()

    for _ in range(3):
        if use_filter:
            generated, is_pure, has_und = generate_smart_username(len_mode, use_num, use_und)
        else:
            rand_type = random.random()
            is_pure, has_und = False, False
            if rand_type < 0.20:
                generated = random.choice(PURE_WORDS)
                is_pure = True
            else:
                cat = random.choice(list(BRAND_CATEGORIES.values()))
                b, c = random.choice(cat["names"]), random.choice(cat["contexts"])
                generated = f"{b}_{c}" if random.random() < 0.5 else f"{b}{c}"
                has_und = "_" in generated

        if generated.lower() in ["error", "timeout", "retry"]:
            continue

        check_result = await check_username_telethon(generated)

        if check_result is not None:
            is_free_bool = True if check_result is True else False
            return {
                "status": "success",
                "generated_username": generated,
                "platform": platform,
                "is_free": is_free_bool,
                "evaluation": calculate_catch_score(generated, check_result, is_pure, has_und)
            }
        
        await asyncio.sleep(0.3)

    return JSONResponse(status_code=503, content={"error": "telethon_timeout"})

@app.get("/api/radar/add")
async def radar_add(chat_id: str, username: str):
    db = load_radar_db()
    if chat_id not in db: db[chat_id] = []
    username = username.replace("@", "").strip()
    if username not in db[chat_id]:
        db[chat_id].append(username)
        save_radar_db(db)
    return {"status": "ok", "targets": db[chat_id]}

@app.get("/api/radar/list")
async def radar_list(chat_id: str):
    db = load_radar_db()
    return {"targets": db.get(chat_id, [])}

@app.get("/api/radar/remove")
async def radar_remove(chat_id: str, username: str):
    db = load_radar_db()
    username = username.replace("@", "").strip()
    if chat_id in db and username in db[chat_id]:
        db[chat_id].remove(username)
        save_radar_db(db)
    return {"status": "ok", "targets": db.get(chat_id, [])}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
