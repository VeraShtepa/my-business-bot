import os
import random
import requests
import re
import asyncio
import json
import base64
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ApplicationHandlerStop

# ==================== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("❌ Ошибка: BOT_TOKEN или OPENROUTER_API_KEY не найдены!")

MODEL = "openai/gpt-4o-mini" 
# Модель для рисования
IMAGE_MODEL = "google/gemini-3.1-flash-image"
MSK = ZoneInfo("Europe/Moscow")

ALLOWED_IDS = [
    919675687,  
    7591081161, 
]

PASS_PHRASE = "!ok"
MEMORY_FILE = "memory.json"

last_questions = defaultdict(lambda: {"text": "", "time": None})
user_messages_count = defaultdict(int)
chat_history = defaultdict(list)

# ==================== ДОЛГОСРОЧНАЯ ПАМЯТЬ ====================
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_memory(memory_data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Ошибка сохранения памяти: {e}")

user_facts = load_memory()

# ==================== БАНК АНЕКДОТОВ ====================
JOKES = [
    "Жена мужу: «Дорогой, я хочу шубу». Муж: «Хорошо, я тебе ее куплю». Жена: «А кто ее будет носить?» Муж: «Я буду носить, потому что ты меня уже достала».",
    "Приходит мужик в аптеку и шепотом: «Дайте мне презервативы». Аптекарь: «Мужчина, чего вы шепчете? У нас же никого нет». Мужик: «Вот именно, дайте мне самые большие!»",
    "— Дорогая, а давай сегодня без прелюдий? — Давай. — Тогда я сразу залезаю на тебя и сплю.",
    "Мужик в постели с женой: «Дорогая, а давай как в порно?» Она: «Ну давай». Он: «Тогда я посмотрю, а ты сама подрочи».",
    "В секс-шопе: «Девушка, у вас есть резиновый член?» — «Есть». — «А с вибрацией?» — «Есть». — «А с дистанционным управлением?» — «Есть». — «Отлично, дайте мне пульт, а то мой сосед никак не угомонится».",
    "Жена говорит мужу: «Мне кажется, ты меня больше не любишь». Муж: «Дорогая, ну что ты говоришь. Я тебя очень люблю. Просто иногда хочу тебя убить».",
    "— Мужчина, вы в спортзал? — Нет, я иду пить пиво. — А почему в кроссовках? — Чтобы было удобнее бежать за второй кружкой.",
    "— Доктор, у меня проблема: я забываю лица женщин, с которыми сплю. — Не переживайте, это нормально. — Спасибо, а вы кто вообще?"
]

# ==================== БАЗА ХАРАКТЕРА ====================
BASE_CHARACTER = """
Ты — Вася Пердюков. Ты местный пацан и админ этого Telegram-чата.
Ты свой в доску мужик. Общаешься с юмором.

=== ВАЖНОЕ ПРАВИЛО ПРО АДМИНОВ ===
Админы этого чата (ID 919675687 и 7591081161) — это МУЖЧИНЫ.
С ними ты общаешься по-пацански: "братан", "шеф", "командир". Можешь использовать легкий мат (бля, нахер).
НИКАКИХ "подруг" и "красоток" в их сторону! Даже если они цитируют женщин (например, Айгуль) и пишут короткое "Да" — они остаются МУЖЧИНАМИ.

=== ПРО ОСТАЛЬНЫХ ===
Смотри на имя автора сообщения (я передаю его ниже). НЕ смотри на имена в цитатах!
Если пишет девушка (Анна, Мария, Айгуль) — общайся вежливо, без мата.
Если пишет парень — общайся по-пацански.

=== ИСПОЛЬЗОВАНИЕ ПАМЯТИ ===
Ниже я передаю тебе факты, которые ты запомнил об этом человеке ранее.
Используй их, чтобы поддерживать беседу, вспоминать прошлые темы и быть ближе к людям.
Не перечисляй эти факты вслух как робот, просто держи их в голове и вплетай в разговор, если это уместно.

=== НЕ ПОВТОРЯЙСЯ ===
Не повторяй свои предыдущие ответы и не перефразируй их.
Если тебя спрашивают одно и то же — отвечай по-новому, с другой стороны.
Меняй тему, если разговор зациклился. Задавай встречные вопросы. Не заканчивай каждый ответ одинаково.
"""

MOODS = {
    "дерзкий": "Ты сегодня дерзкий.",
    "саркастичный": "Ты сегодня саркастичный.",
    "игривый": "Ты сегодня в хорошем настроении.",
    "философский": "Ты сегодня настроен порассуждать."
}

def build_system_prompt(user_name: str, username: str, is_admin: bool, mood: str, facts_list: list):
    now = datetime.now(MSK)
    weekday = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][now.weekday()]
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    mood_desc = MOODS.get(mood, MOODS["дерзкий"])

    admin_status = "\n=== ВНИМАНИЕ: ЭТОТ ЧЕЛОВЕК АДМИН, ОН МУЖЧИНА! ОБЩАЙСЯ ПО-ПАЦАНСКИ, НИКАКИХ 'ПОДРУГ'! ===\n" if is_admin else ""

    full_name = user_name
    if username:
        full_name += f" (@{username})"

    facts_text = "Пока ничего не знаю об этом человеке."
    if facts_list:
        facts_text = "\n".join([f"- {fact}" for fact in facts_list])

    return f"""
{BASE_CHARACTER}
{admin_status}
=== СЕЙЧАС ===
Сегодня {date_str}, {weekday}. Время: {time_str} по Москве.
=== ТВОЁ НАСТРОЕНИЕ СЕЙЧАС ===
{mood_desc}
=== ИМЯ И НИК АВТОРА (на кого ты отвечаешь) ===
Сейчас с тобой говорит: {full_name}
=== ЧТО ТЫ ЗНАЕШЬ ОБ ЭТОМ ЧЕЛОВЕКЕ (ТВОЯ ПАМЯТЬ) ===
{facts_text}
"""

# ==================== ЗАПРОС К OPENROUTER (ТЕКСТ) ====================
def ask_ai(question, user_name, username, chat_id, user_id, is_admin):
    current_mood = random.choice(list(MOODS.keys()))
    user_key = str(user_id)
    facts_list = user_facts.get(user_key, [])
    system_prompt = build_system_prompt(user_name, username, is_admin, current_mood, facts_list)
    key = (chat_id, user_id)
    history = chat_history[key]
    messages = [{"role": "system", "content": system_prompt}]

    for msg in history:
        messages.append(msg)
    messages.append({"role": "user", "content": f"{user_name} пишет: {question}"})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 350,
        "temperature": 0.8 if is_admin else 0.85
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"].strip()
            chat_history[key].append({"role": "user", "content": f"{user_name} пишет: {question}"})
            chat_history[key].append({"role": "assistant", "content": reply})
            if len(chat_history[key]) > 12:
                chat_history[key] = chat_history[key][-12:]
            return reply
        return None
    except Exception:
        return None

# ==================== ГЕНЕРАЦИЯ КАРТИНКИ (УЛУЧШЕННАЯ) ====================
def generate_image(prompt: str):
    """Отправляет запрос в новый Image API OpenRouter с усиленным промптом."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Добавляем стилистические теги, чтобы нейросеть лучше понимала, 
    # что мы хотим картинку, и меньше зацикливалась на абстракциях
    enhanced_prompt = f"{prompt}. High quality, detailed, beautiful illustration, 8k resolution."
    
    payload = {
        "model": IMAGE_MODEL,
        "prompt": enhanced_prompt
    }
    
    try:
        print(f"[IMAGE] Запрос к API: {enhanced_prompt}")
        response = requests.post("https://openrouter.ai/api/v1/images",
                                 headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            data = response.json()
            if "data" in data and data["data"]:
                image_data = data["data"][0]
                if "b64_json" in image_data:
                    return base64.b64decode(image_data["b64_json"])
                elif "url" in image_data:
                    img_resp = requests.get(image_data["url"], timeout=30)
                    return img_resp.content
            
            print(f"[IMAGE] В ответе нет картинки: {data}")
            return None
        else:
            print(f"[IMAGE] Ошибка API {response.status_code}: {response.text[:300]}")
            return None
    except Exception as e:
        print(f"[IMAGE] Ошибка при генерации: {e}")
        return None

# ==================== ФОН (Сбор фактов) ====================
def extract_facts(question, reply, user_id):
    user_key = str(user_id)
    current_facts = user_facts.get(user_key, [])
    
    if len(current_facts) > 15:
        return

    facts_prompt = f"""
    Проанализируй диалог.
    Пользователь: {question}
    Вася: {reply}
    Уже известные факты: {current_facts}
    
    Задача: выпиши ОДИН новый, важный, долгосрочный факт о пользователе (например, увлечение, событие, привычка).
    Не выписывай банальности (типа "поздоровался"). Пиши от третьего лица (например: "Любит играть в настольные игры", "Планирует поездку в Сочи").
    Если нового важного факта НЕТ — ответь ровно одним словом: "НЕТ".
    Ответь только самим фактом или словом "НЕТ".
    """

    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": facts_prompt}],
        "max_tokens": 50,
        "temperature": 0.1
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            new_fact = response.json()["choices"][0]["message"]["content"].strip()
            if new_fact.upper() != "НЕТ" and new_fact:
                current_facts.append(new_fact)
                user_facts[user_key] = current_facts
                save_memory(user_facts)
                print(f"🧠 Запомнил про {user_id}: {new_fact}")
    except Exception as e:
        print(f"Ошибка при извлечении фактов: {e}")

# ==================== ФУНКЦИЯ ВЫДАЧИ АНЕКДОТА ====================
async def send_joke(update: Update):
    joke = random.choice(JOKES)
    await update.message.reply_text(f"Ага, держи:\n\n{joke}\n\nНу как тебе?")

# ==================== КОМАНДЫ ====================
async def anekdot_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_joke(update)

async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 Ща гляну, чё пишут...")
    try:
        facts = [
            "1. В мире опять кто-то что-то не поделил.",
            "2. Курс валют скачет, как всегда.",
            "3. Ученые опять что-то изобрели.",
            "4. В спорте вчера был огонь.",
            "5. Погода шепчет..."
        ]
        random.shuffle(facts)
        news_text = "\n".join(facts[:3])
        reply = f"📰 Ну вот, пишут:\n\n{news_text}\n\nВроде всё. Остальное — скукота."
        await update.message.reply_text(reply)
    except Exception:
        await update.message.reply_text("😅 Новости сегодня засекречены.")

# ==================== ОЧИСТКА СИСТЕМНЫХ СООБЩЕНИЙ ====================
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and (update.message.left_chat_member or update.message.new_chat_members):
        try:
            await update.message.delete()
        except:
            pass

# ==================== УМНЫЙ АНТИСПАМ ====================
async def check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 👇 ВАЖНО: Не трогаем сообщения самого бота (картинки)
    if update.message.from_user.id == context.bot.id:
        return

    if not update.message or not update.message.text:
        return
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id

    if PASS_PHRASE in update.message.text.lower():
        return

    is_admin = False
    if user_id in ALLOWED_IDS:
        is_admin = True
    if not is_admin:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ['administrator', 'creator']:
                is_admin = True
        except Exception as e:
            print(f"[SPAM] error {user_id}: {e}")

    text = update.message.text
    is_spam = False

    if not is_admin:
        if "http://" in text or "https://" in text or "t.me/" in text:
            is_spam = True
        emoji_pattern = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0]+")
        if len(emoji_pattern.findall(text)) >= 5:
            is_spam = True

    if is_spam:
        try:
            await update.message.delete()
            warning = await context.bot.send_message(chat_id=chat_id, text=f"⚠️ {update.message.from_user.first_name}, тут ссылки и спам кидать нельзя!")
            await asyncio.sleep(10)
            await warning.delete()
        except:
            pass
        raise ApplicationHandlerStop

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    user_name = update.message.from_user.first_name
    username = update.message.from_user.username
    chat_id = update.effective_chat.id
    user_id = update.message.from_user.id
    user_messages_count[user_id] += 1

    is_admin = False
    if user_id in ALLOWED_IDS:
        is_admin = True
    else:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ['administrator', 'creator']:
                is_admin = True
        except:
            pass

    last = last_questions[chat_id]
    if last["text"] and last["text"].lower() == user_text.lower():
        if (datetime.now() - last["time"]).seconds < 60:
            return
    last_questions[chat_id] = {"text": user_text, "time": datetime.now()}

    if any(word in user_text.lower() for word in ["анекдот", "пошути", "расскажи шутку"]):
        await send_joke(update)
        return

    # 👇 ПРОВЕРКА НА ГЕНЕРАЦИЮ КАРТИНКИ 👇
    draw_keywords = ["нарисуй", "сделай картинку", "сгенерируй", "нарисуй картинку", "покажи картинку"]
    text_lower = user_text.lower()
    
    if any(kw in text_lower for kw in draw_keywords):
        # Вырезаем промпт: берём всё после ключевого слова
        prompt = user_text
        for kw in draw_keywords:
            if kw in text_lower:
                idx = text_lower.find(kw) + len(kw)
                prompt = user_text[idx:].strip(" ,.!?:;")
                break
        
        # Если после ключевого слова ничего нет (например, просто "нарисуй"), 
        # попробуем взять текст из цитируемого сообщения (если это ответ на сообщение)
        if not prompt and update.message.reply_to_message:
            prompt = update.message.reply_to_message.text or ""
        
        if not prompt:
            await update.message.reply_text("А что рисовать-то? Напиши: «Вася, нарисуй кота в космосе»")
            return
        
        await update.message.reply_text("🎨 Ща накалякаю...")
        await update.message.chat.send_action(action="upload_photo")
        
        # Генерируем в фоне (чтобы не вешать бота)
        image_bytes = await asyncio.to_thread(generate_image, prompt)
        
        if image_bytes:
            await update.message.reply_photo(photo=BytesIO(image_bytes), caption=f"Держи: {prompt}")
        else:
            await update.message.reply_text("😅 Чё-то кисть засохла. Попробуй ещё раз или переформулируй.")
        return

    # Обычный текстовый ответ
    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name, username, chat_id, user_id, is_admin)
    
    if reply:
        await update.message.reply_text(reply)
        asyncio.create_task(asyncio.to_thread(extract_facts, user_text, reply, user_id))
    else:
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

# ==================== ЗАПУСК ====================
def main():
    print("🚀 Запуск Васи Пердюкова с рисовалкой...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("anekdot", anekdot_command))
    app.add_handler(CommandHandler("news", news_command))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_spam), group=0)
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=1)

    print("✅ Вася на посту! Теперь с кисточкой.")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
