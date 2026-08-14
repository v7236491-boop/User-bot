import os
import time
import json
import random
import asyncio
import logging
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
import aiofiles

from telethon import TelegramClient, errors
from telethon.tl.functions.account import CheckUsernameRequest
from aiogram import Bot

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("scanner_backend")

TG_API_ID = int(os.getenv("TG_API_ID", "1234567"))
TG_API_HASH = os.getenv("TG_API_HASH", "your_api_hash_here")
TG_SESSION_NAME = os.getenv("TG_SESSION_NAME", "scanner_session")
BOT_TOKEN = os.getenv("BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
GAME_DB_PATH = os.path.join(DATA_DIR, "game_data.json")
RADAR_DB_PATH = os.path.join(DATA_DIR, "radar_db.json")
LEADERBOARD_DB_PATH = os.path.join(DATA_DIR, "leaderboard_db.json")

DB_LOCK = asyncio.Lock()

# Глобальный кулдаун FloodWait
flood_cooldown_until: float = 0.0

# Клиенты
telethon_client: Optional[TelegramClient] = None
tg_bot: Optional[Bot] = None

# ==========================================
# 2. СЛОВАРИ И КОНСТАНТЫ ГЕНЕРАТОРА
# ==========================================
CONSONANTS_EASY = "bcdfgklmnprstvwz"
VOWELS_EASY = "aeiouy"

TOP_BRANDS = [
    "ton", "core", "apex", "meta", "cyber", "hyper", "volt", "flux", "pulse",
    "nova", "quantum", "matrix", "nexus", "orbit", "vortex", "alpha", "prime",
    "shadow", "phantom", "echo", "frost", "blaze", "storm", "spark", "drift",
    "zenith", "stellar", "astral", "aether", "solis", "lunar", "titan", "aurora"
]

PURE_WORDS = [
    "trade", "token", "chain", "block", "cloud", "space", "shard", "pixel",
    "logic", "sonic", "glide", "pulse", "flash", "light", "prism", "forge",
    "oasis", "vault", "haven", "realm", "guard", "scope", "route", "phase"
]

OFFLINE_RATES = {
    0: 0.0,
    1: 0.5,
    2: 1.2,
    3: 2.5,
    4: 4.5,
    5: 7.5,
    6: 12.0,
    7: 18.0,
    8: 26.0,
    9: 36.0,
    10: 50.0
}

SHOP_PRICES = {
    "radar_slot": 5000,
    "turbo_parse": 3500,
    "theme_cyberpunk": 40000,
    "rank_legend": 100000
}

# ==========================================
# 3. АТОМАРНАЯ РАБОТА С JSON БАЗОЙ
# ==========================================
def ensure_db_files_exist():
    defaults = {
        GAME_DB_PATH: {},
        RADAR_DB_PATH: [],
        LEADERBOARD_DB_PATH: []
    }
    for file_path, default_data in defaults.items():
        if not os.path.exists(file_path):
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)


async def read_json_db(file_path: str) -> Any:
    async with DB_LOCK:
        if not os.path.exists(file_path):
            return {} if "game" in file_path else []
        async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
            content = await f.read()
            if not content.strip():
                return {} if "game" in file_path else []
            return json.loads(content)


async def write_json_db_atomic(file_path: str, data: Any) -> None:
    async with DB_LOCK:
        tmp_path = f"{file_path}.tmp"
        content = json.dumps(data, ensure_ascii=False, indent=2)
        
        loop = asyncio.get_running_loop()
        
        def _sync_write_and_flush():
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, file_path)

        await loop.run_in_executor(None, _sync_write_and_flush)

# ==========================================
# 4. ВСПОМОГАТЕЛЬНАЯ ЛОГИКА И СКОРИНГ
# ==========================================
def calculate_catch_score(username: str, is_available: bool) -> Dict[str, Any]:
    if not is_available:
        return {
            "tier": "F",
            "score": 0,
            "estimated_value_ton": "0 TON",
            "description": "Занятый никнейм"
        }

    clean_name = username.lower().replace("_", "")
    length = len(clean_name)
    has_digits = any(char.isdigit() for char in username)
    has_underscore = "_" in username

    is_brand = clean_name in TOP_BRANDS or clean_name in PURE_WORDS

    consecutive_consonants = 0
    max_consonants = 0
    for char in clean_name:
        if char in CONSONANTS_EASY:
            consecutive_consonants += 1
            if consecutive_consonants > max_consonants:
                max_consonants = consecutive_consonants
        else:
            consecutive_consonants = 0

    if (is_brand and length <= 6) or (length == 4 and not has_digits and not has_underscore):
        return {
            "tier": "SSS+",
            "score": 100,
            "estimated_value_ton": "100-500+ TON",
            "description": "Элитный никнейм (Ультра-редкость / Бренд)"
        }

    if length == 5 and not has_digits and not has_underscore and max_consonants <= 2:
        return {
            "tier": "SS",
            "score": 75,
            "estimated_value_ton": "15-40 TON",
            "description": "Чистый 5-буквенный никнейм"
        }

    if length == 6 and not has_digits and not has_underscore and max_consonants <= 2:
        return {
            "tier": "S",
            "score": 55,
            "estimated_value_ton": "5-15 TON",
            "description": "Красивый 6-буквенный никнейм"
        }

    if has_digits or has_underscore or max_consonants >= 3:
        return {
            "tier": "B" if (has_digits and has_underscore) else "A",
            "score": 20 if (has_digits and has_underscore) else 35,
            "estimated_value_ton": "1-3 TON",
            "description": "Составной никнейм с цифрами или знаками"
        }

    return {
        "tier": "A",
        "score": 40,
        "estimated_value_ton": "2-5 TON",
        "description": "Стандартный читаемый никнейм"
    }


def generate_smart_username(
    len_mode: str,
    use_filter: bool,
    use_num: bool,
    use_und: bool
) -> str:
    target_length = 5 if len_mode == "5-6" else 7
    if len_mode == "5-6" and random.random() > 0.5:
        target_length = 6
    elif len_mode == "7-8" and random.random() > 0.5:
        target_length = 8

    if not use_filter and random.random() < 0.25:
        base_word = random.choice(TOP_BRANDS + PURE_WORDS)
        if len(base_word) > target_length:
            base_word = base_word[:target_length]
    else:
        syllables = []
        is_consonant = random.choice([True, False])
        current_len = 0
        while current_len < target_length:
            if is_consonant:
                char = random.choice(CONSONANTS_EASY)
            else:
                char = random.choice(VOWELS_EASY)
            syllables.append(char)
            current_len += 1
            is_consonant = not is_consonant
        base_word = "".join(syllables)

    result = base_word
    if use_und and len(result) >= 4:
        pos = random.randint(2, len(result) - 2)
        result = result[:pos] + "_" + result[pos:]

    if use_num:
        num = str(random.randint(1, 99))
        result = result + num

    return result.lower()

# ==========================================
# 5. СЕРВИС ПРОВЕРКИ TELETHON И РАДАР
# ==========================================
async def verify_username_telegram(username: str) -> tuple[bool, str]:
    global flood_cooldown_until

    now = time.time()
    if now < flood_cooldown_until:
        remaining = int(flood_cooldown_until - now)
        logger.warning(f"Telethon в режиме FloodWait кулдауна. Осталось {remaining} сек.")
        return False, "rate_limit"

    if not telethon_client or not telethon_client.is_connected():
        logger.error("Telethon клиент не инициализирован или не подключен.")
        return False, "client_offline"

    try:
        result = await telethon_client(CheckUsernameRequest(username=username))
        return bool(result), "ok"
    except errors.FloodWaitError as e:
        flood_cooldown_until = time.time() + e.seconds
        logger.error(f"Пойман FloodWait на {e.seconds} секунд!")
        return False, "rate_limit"
    except errors.UsernameInvalidError:
        return False, "invalid_format"
    except errors.UsernameOccupiedError:
        return False, "ok"
    except Exception as e:
        logger.error(f"Непредвиденная ошибка Telethon при проверке '{username}': {e}")
        return False, "error"


async def radar_worker():
    logger.info("Воркер радара успешно запущен.")
    while True:
        try:
            await asyncio.sleep(10)
            radar_items: List[Dict[str, Any]] = await read_json_db(RADAR_DB_PATH)
            if not radar_items:
                continue

            updated_items = []
            for item in radar_items:
                username = item.get("username", "")
                user_id = item.get("user_id")

                if not username or not user_id:
                    continue

                is_free, status = await verify_username_telegram(username)
                if status == "ok" and is_free:
                    logger.info(f"[RADAR] Никнейм @{username} освободился! Отправка уведомления {user_id}")
                    if tg_bot:
                        try:
                            msg = (
                                f"🚨 <b>РАДАР ОБНАРУЖИЛ СВОБОДНЫЙ НИКНЕЙМ!</b>\n\n"
                                f"Юзернейм: <code>@{username}</code>\n"
                                f"Статус: <b>СВОБОДЕН</b> ✅\n\n"
                                f"Займите его прямо сейчас в Telegram!"
                            )
                            await tg_bot.send_message(chat_id=user_id, text=msg, parse_mode="HTML")
                        except Exception as send_err:
                            logger.error(f"Не удалось отправить уведомление в бота: {send_err}")
                else:
                    updated_items.append(item)

            if len(updated_items) != len(radar_items):
                await write_json_db_atomic(RADAR_DB_PATH, updated_items)

        except asyncio.CancelledError:
            logger.info("Воркер радара остановлен.")
            break
        except Exception as e:
            logger.error(f"Ошибка в цикле воркера радара: {e}")

# ==========================================
# 6. LIFESPAN МЕНЕДЖЕР FASTAPI
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global telethon_client, tg_bot

    ensure_db_files_exist()
    logger.info("Инициализация сервисов...")

    if BOT_TOKEN and "ABC-DEF" not in BOT_TOKEN:
        try:
            tg_bot = Bot(token=BOT_TOKEN)
            bot_info = await tg_bot.get_me()
            logger.info(f"Aiogram бот подключен: @{bot_info.username}")
        except Exception as e:
            logger.warning(f"Не удалось запустить Aiogram бот: {e}")
    else:
        logger.warning("BOT_TOKEN не задан, бот пропущен.")

    if TG_API_HASH != "your_api_hash_here":
        try:
            telethon_client = TelegramClient(
                os.path.join(DATA_DIR, TG_SESSION_NAME),
                TG_API_ID,
                TG_API_HASH
            )
            await telethon_client.connect()
            if not await telethon_client.is_user_authorized():
                logger.warning("Telethon сессия не авторизована! Проверки могут быть ограничены.")
            else:
                logger.info("Telethon клиент успешно авторизован и готов к сканированию.")
        except Exception as e:
            logger.error(f"Ошибка запуска Telethon: {e}")
    else:
        logger.warning("TG_API_ID/TG_API_HASH не заданы, Telethon пропущен.")

    worker_task = asyncio.create_task(radar_worker())

    yield

    worker_task.cancel()
    if telethon_client and telethon_client.is_connected():
        await telethon_client.disconnect()
        logger.info("Telethon отключен.")
    if tg_bot:
        await tg_bot.session.close()
        logger.info("Сессия Aiogram бота закрыта.")

# ==========================================
# 7. FASTAPI ПРИЛОЖЕНИЕ И РОУТИНГ
# ==========================================
app = FastAPI(title="Username Scanner PRO & Cosmic Core 3D", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SyncTapRequest(BaseModel):
    user_id: str
    taps: int = Field(..., ge=1, le=100)


class BuyUpgradeRequest(BaseModel):
    user_id: str
    item_id: str


class RadarAddRequest(BaseModel):
    user_id: int
    username: str


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(DATA_DIR, "index.html")
    if os.path.exists(index_path):
        async with aiofiles.open(index_path, mode="r", encoding="utf-8") as f:
            content = await f.read()
        return HTMLResponse(content=content)
    return HTMLResponse("<h2>Файл index.html не найден в корневой директории проекта.</h2>", status_code=404)


@app.get("/api/generate")
async def api_generate_username(
    platform: str = Query("telegram", pattern="^(telegram|whatsapp)$"),
    use_filter: bool = Query(True),
    len_mode: str = Query("5-6", pattern="^(5-6|7-8)$"),
    use_num: bool = Query(False),
    use_und: bool = Query(False),
    finder_name: str = Query("Anonymous"),
    finder_id: str = Query("guest")
):
    attempts = 5
    checked_items = []

    for _ in range(attempts):
        candidate = generate_smart_username(
            len_mode=len_mode,
            use_filter=use_filter,
            use_num=use_num,
            use_und=use_und
        )

        if platform == "telegram":
            is_free, status = await verify_username_telegram(candidate)
            if status == "rate_limit":
                return JSONResponse(
                    status_code=429,
                    content={
                        "status": "rate_limit",
                        "message": "Превышен лимит запросов Telegram API (FloodWait). Попробуйте позже.",
                        "retry_after": max(0, int(flood_cooldown_until - time.time()))
                    }
                )
        else:
            is_free = len(candidate) >= 5 and not candidate.startswith("_")
            status = "ok"

        score_data = calculate_catch_score(candidate, is_free)

        item_result = {
            "username": candidate,
            "platform": platform,
            "is_available": is_free,
            "status": status,
            "tier": score_data["tier"],
            "score": score_data["score"],
            "estimated_value_ton": score_data["estimated_value_ton"],
            "description": score_data["description"],
            "timestamp": int(time.time())
        }

        checked_items.append(item_result)

        if is_free and score_data["score"] >= 55:
            leaderboard = await read_json_db(LEADERBOARD_DB_PATH)
            entry = {
                "username": candidate,
                "tier": score_data["tier"],
                "score": score_data["score"],
                "value": score_data["estimated_value_ton"],
                "finder_name": finder_name,
                "finder_id": finder_id,
                "date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            leaderboard.insert(0, entry)
            await write_json_db_atomic(LEADERBOARD_DB_PATH, leaderboard[:1000])

        if is_free:
            break

    return {
        "success": True,
        "results": checked_items,
        "primary": checked_items[-1]
    }


@app.get("/api/game/state")
async def get_game_state(user_id: str = Query(...)):
    game_db = await read_json_db(GAME_DB_PATH)
    now = time.time()

    user_state = game_db.get(user_id)
    if not user_state:
        user_state = {
            "coins": 0.0,
            "energy": 1000,
            "max_energy": 1000,
            "multi_tap": 1,
            "offline_miner": 0,
            "purchased_items": [],
            "last_active": now,
            "created_at": now
        }
        game_db[user_id] = user_state
        await write_json_db_atomic(GAME_DB_PATH, game_db)
        return {"state": user_state, "offline_earned": 0.0}

    time_diff = now - user_state.get("last_active", now)
    energy_recovery = int(time_diff * 1.0)
    current_energy = min(
        user_state.get("max_energy", 1000),
        user_state.get("energy", 1000) + energy_recovery
    )
    user_state["energy"] = current_energy

    capped_offline_time = min(time_diff, 10800.0)
    miner_lvl = user_state.get("offline_miner", 0)
    rate_per_sec = OFFLINE_RATES.get(miner_lvl, 0.0)
    offline_earned = round(capped_offline_time * rate_per_sec, 2)

    user_state["coins"] = round(user_state.get("coins", 0.0) + offline_earned, 2)
    user_state["last_active"] = now

    game_db[user_id] = user_state
    await write_json_db_atomic(GAME_DB_PATH, game_db)

    return {
        "state": user_state,
        "offline_earned": offline_earned,
        "offline_seconds": int(capped_offline_time)
    }


@app.post("/api/game/sync_tap")
async def sync_tap(payload: SyncTapRequest):
    game_db = await read_json_db(GAME_DB_PATH)
    now = time.time()

    user_state = game_db.get(payload.user_id)
    if not user_state:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    time_diff = now - user_state.get("last_active", now)
    current_energy = min(
        user_state.get("max_energy", 1000),
        user_state.get("energy", 1000) + int(time_diff * 1.0)
    )

    taps_requested = payload.taps
    actual_taps = min(current_energy, taps_requested)

    if actual_taps <= 0:
        return {
            "success": False,
            "message": "Недостаточно энергии",
            "state": user_state
        }

    multi_tap = user_state.get("multi_tap", 1)
    earned = actual_taps * multi_tap

    user_state["energy"] = current_energy - actual_taps
    user_state["coins"] = round(user_state.get("coins", 0.0) + earned, 2)
    user_state["last_active"] = now

    game_db[payload.user_id] = user_state
    await write_json_db_atomic(GAME_DB_PATH, game_db)

    return {
        "success": True,
        "earned": earned,
        "taps_processed": actual_taps,
        "state": user_state
    }


@app.post("/api/game/buy")
async def buy_upgrade(payload: BuyUpgradeRequest):
    game_db = await read_json_db(GAME_DB_PATH)
    user_state = game_db.get(payload.user_id)

    if not user_state:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    item_id = payload.item_id
    coins = user_state.get("coins", 0.0)

    if item_id == "multi_tap":
        lvl = user_state.get("multi_tap", 1)
        if lvl >= 20:
            raise HTTPException(status_code=400, detail="Достигнут максимальный уровень Multi-Tap")
        cost = int(200 * (1.8 ** (lvl - 1)))
        if coins < cost:
            raise HTTPException(status_code=400, detail="Недостаточно монет")
        user_state["coins"] = round(coins - cost, 2)
        user_state["multi_tap"] = lvl + 1

    elif item_id == "max_energy":
        current_max = user_state.get("max_energy", 1000)
        step = (current_max - 1000) // 500
        cost = int(150 * (1.6 ** step))
        if coins < cost:
            raise HTTPException(status_code=400, detail="Недостаточно монет")
        user_state["coins"] = round(coins - cost, 2)
        user_state["max_energy"] = current_max + 500
        user_state["energy"] = user_state.get("energy", 1000) + 500

    elif item_id == "offline_miner":
        lvl = user_state.get("offline_miner", 0)
        if lvl >= 10:
            raise HTTPException(status_code=400, detail="Достигнут максимальный уровень Offline Miner")
        cost = int(3000 * (2.2 ** lvl))
        if coins < cost:
            raise HTTPException(status_code=400, detail="Недостаточно монет")
        user_state["coins"] = round(coins - cost, 2)
        user_state["offline_miner"] = lvl + 1

    elif item_id in SHOP_PRICES:
        cost = SHOP_PRICES[item_id]
        purchased = user_state.get("purchased_items", [])
        if item_id in purchased:
            raise HTTPException(status_code=400, detail="Предмет уже приобретен")
        if coins < cost:
            raise HTTPException(status_code=400, detail="Недостаточно монет")
        user_state["coins"] = round(coins - cost, 2)
        purchased.append(item_id)
        user_state["purchased_items"] = purchased
    else:
        raise HTTPException(status_code=400, detail="Неизвестный предмет")

    game_db[payload.user_id] = user_state
    await write_json_db_atomic(GAME_DB_PATH, game_db)

    return {"success": True, "state": user_state}


@app.get("/api/leaderboard")
async def get_leaderboard():
    data = await read_json_db(LEADERBOARD_DB_PATH)
    return {"leaderboard": data[:100]}


@app.post("/api/radar/add")
async def add_to_radar(payload: RadarAddRequest):
    radar_db = await read_json_db(RADAR_DB_PATH)
    clean_username = payload.username.lower().replace("@", "").strip()

    for item in radar_db:
        if item.get("username") == clean_username and item.get("user_id") == payload.user_id:
            return {"success": True, "message": "Никнейм уже находится на отслеживании"}

    radar_db.append({
        "username": clean_username,
        "user_id": payload.user_id,
        "added_at": int(time.time())
    })
    await write_json_db_atomic(RADAR_DB_PATH, radar_db)
    return {"success": True, "message": f"Никнейм @{clean_username} успешно добавлен в радар"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
