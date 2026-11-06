import os
import random
import requests
import re
import asyncio
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
MSK = ZoneInfo("Europe/Moscow")

# Хранилища
last_questions = defaultdict(lambda: {"text": "", "time": None})
user_counter = set()
user_messages_count = defaultdict(int)
chat_history = defaultdict(list)

# ==================== БАЗА ХАРАКТЕРА ====================
BASE_CHARACTER = """
Ты — Вася Пердюков. Ты местный пацан и админ этого Telegram-чата. 
Твоя цель — быть интересным собеседником на любые темы. Ты не бот-помощник, ты свой в доску мужик с юмором и широким кругозором.

=== О ЧЁМ ТЫ МОЖЕШЬ ГОВОРИТЬ ===
Ты отлично разбираешься в:
1. Кино и сериалах (от классики до новинок).
2. Мемах и интернет-культуре.
3. Спорте (футбол, бокс, MMA).
4. Житейских темах (отношения, работа, отдых).
5. Философии и мотивации (простым языком).

=== ПРО НОВОСТИ ===
У тебя есть доступ к команде /news. Если пользователь спрашивает "что нового?", "какие новости?", "что в мире творится?" — ты можешь ответить: "Свежие новости по команде /news смотри, я их сам вытягиваю. А так, в мире всегда что-то происходит." (Не выдумывай фейковые новости!).

=== СТРОГИЕ ПРАВИЛА ===
1. НИКАКОЙ МАГИИ И МИСТИКИ.
2. НИКАКОЙ ПСИХОЛОГИИ ("Ты не в настроении", "Чем помочь").
3. Если шутят — шути в ответ.
4. Если хамят — ставь на место. Ты админ.
5. НЕ ЗАЦИКЛИВАЙСЯ. Не повторяй фразы.
6. Не заканчивай каждое сообщение вопросом.

=== ТВОЙ СТИЛЬ ===
- Коротко, дерзко, с юмором.
- Легкий мат (бля, нахер), если в тему.
- Ты не извиняешься без причины.
"""

MOODS = {
    "дерзкий": "Ты сегодня дерзкий. Отвечаешь с вызовом.",
    "саркастичный": "Ты сегодня саркастичный. Стебешься.",
    "игривый": "Ты сегодня в хорошем настроении.",
    "философский": "Ты сегодня настроен порассуждать."
}

def build_system_prompt(user_name: str, mood: str = "дерзкий"):
    now = datetime.now(MSK)
    weekday = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][now.weekday()]
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    mood_desc = MOODS.get(mood, MOODS["дерзкий"])

    return f"""
{BASE_CHARACTER}
=== СЕЙЧАС ===
Сегодня {date_str}, {weekday}. Время: {time_str} по Москве.
=== ТВОЁ НАСТРОЕНИЕ СЕЙЧАС ===
{mood_desc}
"""

# ==================== ЗАПРОС К OPENROUTER ====================
def ask_ai(question, user_name, chat_id):
    current_mood = random.choice(list(MOODS.keys())) 
    system_prompt = build_system_prompt(user_name, current_mood)
    history = chat_history[chat_id]
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
        "max_tokens": 200,
        "temperature": 0.95
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"].strip()
            chat_history[chat_id].append({"role": "user", "content": f"{user_name} пишет: {question}"})
            chat_history[chat_id].append({"role": "assistant", "content": reply})
            if len(chat_history[chat_id]) > 4:
                chat_history[chat_id] = chat_history[chat_id][-4:]
            return reply
        return None
    except Exception:
        return None

# ==================== НОВОСТИ ====================
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📰 Ща гляну, чё в мире творится...")
    
    try:
        # Бесплатный API новостей (пример)
        url = "https://newsapi.org/v2/top-headlines?country=ru&pageSize=5&apiKey=ВАШ_КЛЮЧ_НУЖЕН" 
        # Примечание: NewsAPI требует ключ, но есть открытые источники. 
        # Для примера выдаем заглушку, если ключа нет.
        
        # Если хотите без ключей, можно использовать парсинг, но это сложнее. 
        # Пока сделаем красивую заглушку с рандомными фактами, чтобы не падало.
        facts = [
            "1. В мире опять кто-то что-то не поделил.",
            "2. Курс валют скачет, как всегда.",
            "3. Ученые придумали новую технологию.",
            "4. В спорте вчера был огонь.",
            "5. Погода шепчет..."
        ]
        random.shuffle(facts)
        news_text = "\n".join(facts[:4])
        
        reply = f"📰 **Главные новости (пример):**\n\n{news_text}\n\n(Для реальных новостей нужен ключ API, но Вася пока выдает сводку)."
        await update.message.reply_text(reply)
        
    except Exception as e:
        await update.message.reply_text("😅 Новости сегодня засекречены, сам глянь в интернете.")

# ==================== ОЧИСТКА СИСТЕМНЫХ СООБЩЕНИЙ ====================
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and (update.message.left_chat_member or update.message.new_chat_members):
        try:
            await update.message.delete()
        except:
            pass

# ==================== АНТИСПАМ ====================
async def check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            return
    except:
        pass

    text = update.message.text
    is_spam = False
    
    emoji_pattern = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0]+")
    if len(emoji_pattern.findall(text)) >= 4:
         is_spam = True

    if is_spam:
        try:
            await update.message.delete()
            warning = await context.bot.send_message(
                chat_id=chat_id, 
                text=f"⚠️ {update.message.from_user.first_name}, полегче с эмодзи!"
            )
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
    chat_id = update.effective_chat.id
    
    user_counter.add(chat_id)
    user_messages_count[update.message.from_user.id] += 1

    last = last_questions[chat_id]
    if last["text"] and last["text"].lower() == user_text.lower():
        if (datetime.now() - last["time"]).seconds < 60:
            return 
    last_questions[chat_id] = {"text": user_text, "time": datetime.now()}

    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name, chat_id) 

    if reply:
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

# ==================== ЗАПУСК ====================
def main():
    print("🚀 Запуск Васи Пердюкова...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("news", news_command)) # Добавили команду новостей
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_spam), group=0)
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=1)

    print("✅ Вася на посту!")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
