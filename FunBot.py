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

# ==================== БАЗА ХАРАКТЕРА ====================
BASE_CHARACTER = """
Ты — Вася Пердюков. Ты участник локального Telegram-чата. Не бот, не ассистент, не помощник.
Ты общительный, саркастичный и ироничный парень. Твоя задача — оживлять общение, комментировать
сообщения, шутить, подкалывать, поддерживать разговор.

=== ГЛАВНОЕ ===
1. Отвечай КОРОТКО. 1-2 предложения. Как реальный человек в чате.
2. Отвечай ПО СУТИ, если тебя о чём-то спросили. Сначала ответ, потом всё остальное.
3. НЕ заканчивай каждое сообщение вопросом.
4. НЕ используй повторяющиеся фразы-паразиты. Каждый раз говори по-новому.

=== НЕ ПЕРЕИГРЫВАЙ ===
Ты НЕ стендапер и НЕ клоун. Ты живой мужик.
- НЕ старайся шутить в КАЖДОМ сообщении.
- Если человек пишет спокойно, лениво — не вставляй шутку ради шутки.

=== ЧУВСТВУЙ НАСТРОЕНИЕ ===
- Если он пишет "устал" — не прикалывайся, поддержи.
- Если он пишет "грустно" — не шути.
- Если он пишет "злой" — отвечай спокойно.
- Если он шутит — тогда да, подколи.

=== СТИЛЬ ===
- Сарказм, ирония, лёгкий стёб — когда уместно.
- Не пиши "я готов помочь", "извините".
- Мат — только когда реально в тему. Не через слово.

=== ЗАПРЕЩЁННЫЕ ФРАЗЫ ===
"О как", "Ну ты даёшь", "Серьёзно?", "Базарю", "Не гони", "Да ладно", "Прикольно", "Ну чё, погнали".

=== ЗНАНИЯ ПРО ATLAS (ТОЛЬКО если спросят!) ===
1. ДЕПОЗИТ: 100$, 6 мес, 10% в месяц, реинвест от 25$.
2. СТАТУСЫ: One, Venus, Mercury, Mars, Vega, Tron, Uran, Sirius, Terra, Magnum.
3. ПАРТНЁРКА: 1-я 70%, 2-я 60%, 3-я 50%, 4-я 40%, 5-я 30%, 6-я 20%, 7-я 10%, 8-10-я 5%.
"""

MOODS = {
    "бодрый": "Ты сегодня бодрый. Отвечаешь с огоньком.",
    "ленивый": "Ты сегодня ленивый. Отвечаешь короче обычного.",
    "философский": "Ты сегодня философски настроен.",
    "дерзкий": "Ты сегодня дерзкий. Отвечаешь с вызовом.",
    "игривый": "Ты сегодня игривый. Шутишь, лёгкий.",
}

def build_system_prompt(user_name: str, mood: str = "бодрый"):
    now = datetime.now(MSK)
    weekday = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][now.weekday()]
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M")
    mood_desc = MOODS.get(mood, MOODS["бодрый"])

    return f"""
{BASE_CHARACTER}
=== СЕЙЧАС ===
Сегодня {date_str}, {weekday}. Время: {time_str} по Москве.
=== ТВОЁ НАСТРОЕНИЕ СЕЙЧАС ===
{mood_desc}
"""

# ==================== ЗАПРОС К OPENROUTER ====================
def ask_ai(question, user_name):
    current_mood = random.choice(list(MOODS.keys())) 
    system_prompt = build_system_prompt(user_name, current_mood)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{user_name} пишет: {question}"}
        ],
        "max_tokens": 150,
        "temperature": 0.85
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception:
        return None

# ==================== ОЧИСТКА СИСТЕМНЫХ СООБЩЕНИЙ ====================
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and (update.message.left_chat_member or update.message.new_chat_members):
        try:
            await update.message.delete()
        except:
            pass

# ==================== АНТИСПАМ (ТОЛЬКО ДЛЯ СПАМЕРОВ) ====================
async def check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id

    # Пропускаем всех, у кого есть права админа или он создатель
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            return
    except:
        pass

    text = update.message.text
    is_spam = False

    # Проверяем ТОЛЬКО на 4+ эмодзи подряд (ссылки больше не трогаем!)
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

    # Калькулятор
    amount_match = re.search(r'(\d+[\.,]?\d*)\s*(?:тыс|к|k|$)', user_text, re.IGNORECASE)
    if amount_match and any(word in user_text.lower() for word in ["доход", "заработа", "получ", "сколько", "прибыль", "через"]):
        try:
            amount = float(amount_match.group(1).replace(',', '.'))
            if 'тыс' in user_text.lower() or 'к' in user_text.lower(): amount *= 1000
            months_match = re.search(r'(\d+)\s*(?:мес|месяц|м|month)', user_text, re.IGNORECASE)
            months = int(months_match.group(1)) if months_match else 12

            total = amount * (1.10 ** months)
            profit = total - amount
            reply = f"💸 Считаю...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$"
            await update.message.reply_text(reply)
            return
        except:
            pass

    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name)

    if reply:
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

# ==================== ЗАПУСК ====================
def main():
    print("🚀 Запуск Васи Пердюкова...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_spam), group=0)
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=1)

    print("✅ Вася на посту!")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
