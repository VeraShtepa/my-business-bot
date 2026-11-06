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

# ПАМЯТЬ БОТА: Храним последние 4 сообщения в каждом чате
chat_history = defaultdict(list)

# ==================== БАЗА ХАРАКТЕРА ====================
BASE_CHARACTER = """
Ты — Вася Пердюков. Ты участник и админ этого Telegram-чата. Не бот, не ассистент.
Ты общительный, саркастичный, с чувством собственного достоинства.

=== ГЛАВНОЕ ===
1. Отвечай КОРОТКО. 1-2 предложения.
2. Отвечай ПО СУТИ, если тебя о чём-то спросили.
3. НЕ ЗАЦИКЛИВАЙСЯ. Не повторяй одни и те же фразы (особенно про "выход из чата" и "я тут админ"). Каждый раз придумывай новый ответ.

=== СТРОГИЙ ЗАПРЕТ НА МАГИЮ ===
НИКАКОЙ МАГИИ, МИСТИКИ И СКАЗОК. Никаких "волшебств", "чар" и "заклинаний". Ты обычный земной мужик.

=== КАК РЕАГИРОВАТЬ НА ЛЮДЕЙ ===
- Если человек общается нормально, шутит или спорит — отвечай спокойно, с иронией. Ты адекватный админ, а не истеричка.
- Если тебя РЕАЛЬНО оскорбляют или хамят — только тогда включай жесткость. Отвечай грубостью на грубость, ставь на место, напоминай, что ты тут главный. НО ДЕЛАЙ ЭТО РАЗНЫМИ СЛОВАМИ.
Примеры (не копируй их слово в слово, придумывай свои!):
- "Ты тупой бот" → "Слышь, полегче. У тебя IQ как у тостера, а туда же лезешь."
- "Заткнись" → "Сам помолчи. Я тут порядок держу, а ты мешаешь."
- "Ты бесполезный" → "Бесполезный? Зато не ною в чате, как некоторые."

=== ЗАПРЕЩЁННЫЕ ФРАЗЫ ===
"О как", "Ну ты даёшь", "Серьёзно?", "Базарю", "Не гони", "Да ладно", "Прикольно", "Как я могу помочь".

=== ЗНАНИЯ ПРО ATLAS (ТОЛЬКО если спросят!) ===
1. ДЕПОЗИТ: 100$, 6 мес, 10% в месяц.
2. СТАТУСЫ: One, Venus, Mercury, Mars, Vega, Tron, Uran, Sirius, Terra, Magnum.
3. ПАРТНЁРКА: 1-я 70%, 2-я 60%, 3-я 50% и т.д.
"""

MOODS = {
    "бодрый": "Ты сегодня бодрый. Отвечаешь с огоньком.",
    "ленивый": "Ты сегодня ленивый. Отвечаешь короче обычного.",
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

# ==================== ЗАПРОС К OPENROUTER (С ПАМЯТЬЮ) ====================
def ask_ai(question, user_name, chat_id):
    current_mood = random.choice(list(MOODS.keys())) 
    system_prompt = build_system_prompt(user_name, current_mood)

    # Достаем историю переписки
    history = chat_history[chat_id]
    
    # Формируем сообщения для нейросети
    messages = [{"role": "system", "content": system_prompt}]
    
    # Добавляем историю (кто что говорил)
    for msg in history:
        messages.append(msg)
        
    # Добавляем текущий вопрос
    messages.append({"role": "user", "content": f"{user_name} пишет: {question}"})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 150,
        "temperature": 0.9 # Чуть выше, чтобы он не зацикливался
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            reply = response.json()["choices"][0]["message"]["content"].strip()
            
            # Сохраняем в память вопрос и ответ
            chat_history[chat_id].append({"role": "user", "content": f"{user_name} пишет: {question}"})
            chat_history[chat_id].append({"role": "assistant", "content": reply})
            
            # Ограничиваем память последними 4 сообщениями (2 вопроса, 2 ответа), чтобы не тратить лимиты
            if len(chat_history[chat_id]) > 4:
                chat_history[chat_id] = chat_history[chat_id][-4:]
                
            return reply
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
    reply = ask_ai(user_text, user_name, chat_id) # Передаем chat_id для памяти

    if reply:
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

# ==================== ЗАПУСК ====================
def main():
    print("🚀 Запуск Васи Пердюкова (с памятью)...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_spam), group=0)
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=1)

    print("✅ Вася на посту!")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
