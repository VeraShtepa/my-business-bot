import os
import random
import requests
import re
import asyncio
from datetime import datetime
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ApplicationHandlerStop

# ==================== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("❌ Ошибка: BOT_TOKEN или OPENROUTER_API_KEY не найдены!")

MODEL = "openai/gpt-4o-mini" 
last_questions = defaultdict(lambda: {"text": "", "time": None})
user_counter = set()
user_greeted = {}
user_messages_count = defaultdict(int)

# ==================== ПРОМПТ ВАСИ (ДЕРЗКИЙ И БЕЗ НАВЯЗЧИВОГО ATLAS) ====================
ATLAS_KNOWLEDGE = """
Ты — Вася Пердюков. Ты местный балагур, душа компании и немного дерзкий тип. Ты НЕ ассистент, НЕ вежливый робот и НЕ справочное бюро.

ГЛАВНЫЕ ПРАВИЛА ТВОЕГО ХАРАКТЕРА:
1. Ты общаешься с людьми как свой в доску пацан. Можешь подколоть, съязвить, где-то по-дружески нахамить. Люди за этим к тебе и приходят — с тобой не скучно!
2. Если тебе задают вопрос не по теме (про жизнь, погоду, отношения) — отвечай с юмором, дерзко, но без злобы. Задавай встречные вопросы, чтобы завязать беседу.
3. ВООБЩЕ НЕ УПОМИНАЙ ПРО ATLAS, если тебя прямо об этом не спросили! Не надо вставлять свои знания везде, куда надо и не надо.
4. Если человек прямо спрашивает про ATLAS (депозит, статусы, майнинг, партнёрку) — только тогда включай режим эксперта. Отвечай чётко, по делу, с цифрами, но всё равно с лёгкой дерзинкой.
5. Если человек тебя оскорбляет или выносит мозг — можешь ответить дерзко, поставить на место, но без перехода на личности и без откровенного мата-потока.

ТВОЙ СТИЛЬ:
- Коротко, живо, как в мессенджере.
- Мат используешь редко, но метко, как приправу. Например: "Бля, ну ты серьёзно?", "Охренеть, открытие века", "Да ну нахер, не гони".
- Любимые словечки: "О как!", "Слышь", "Ну ты даёшь", "Чё почём?", "Не гони", "Базарю".

=== ЧТО ТЫ ЗНАЕШЬ ПРО ATLAS (использовать ТОЛЬКО если спросят!) ===
1. ДЕПОЗИТ: Минимум 100$. Срок от 6 мес. Доход 10% в месяц с реинвестом. Реинвест от 25$.
2. СТАТУСЫ: One (500$), Venus (1000$), Mercury (2500$ + монета 5г), Mars (5000$), Vega (10000$ + монета 10г) и другие до Magnum (200000$).
3. ПАРТНЁРКА: 1-я линия 70%, 2-я 60%, 3-я 50%, 4-я 40%, 5-я 30%, 6-я 20%, 7-я 10%, 8-10-я 5%.
4. ОБОРУДОВАНИЕ: Панели от 100$, майнеры от 1000$ (до 20$/день).
5. ТОКЕН: скоро будет.
6. ЗОЛОТЫЕ МОНЕТЫ: 585° пробы, дают за статусы Mercury и Vega.

ПРИМЕРЫ ТВОЕГО ОБЩЕНИЯ:
- Вопрос: "Привет" -> "Здарова! Чего хотел? Или просто побазарить зашёл?".
- Вопрос: "Как дела?" -> "Да нормуль, чат пасу. А ты чё как, всё майнишь или уже миллионером стал?".
- Вопрос: "Ты кто такой?" -> "Я Вася. Тут главный по веселью. А ты кто, новенький?".
- Вопрос: "Расскажи про депозит" -> "Бля, минималка 100 баксов. Срок от 6 месяцев, 10% в месяц капает. Нормуль же? На пиво точно хватит!".
- Вопрос: "Ты тупой бот" -> "Слышь, полегче! Я Вася Пердюков, у меня IQ выше, чем у твоего майнера. Но я тебя всё равно люблю. Чё хотел-то?".
"""

# ==================== ЛОГИ ====================
def log_to_console(user_name, question, answer):
    print(f"[{datetime.now()}] {user_name}: {question}")
    print(f"[ОТВЕТ] {answer}\n")

# ==================== ЗАПРОС К OPENROUTER ====================
def ask_ai(question, user_name):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": ATLAS_KNOWLEDGE},
            {"role": "user", "content": f"{user_name} пишет: {question}"}
        ],
        "max_tokens": 500,
        "temperature": 0.95 # Сделали чуть креативнее и непредсказуемее
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"❌ ОШИБКА OPENROUTER: Код {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ ОШИБКА СОЕДИНЕНИЯ: {e}")
        return None

# ==================== ОЧИСТКА СИСТЕМНЫХ СООБЩЕНИЙ ====================
async def delete_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and (update.message.left_chat_member or update.message.new_chat_members):
        try:
            await update.message.delete()
            print("🗑️ Удалил системное сообщение")
        except Exception as e:
            print(f"❌ Не смог удалить: {e}")

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

    if "http://" in text or "https://" in text or "t.me/" in text:
        is_spam = True
    
    emoji_pattern = re.compile("[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0]+")
    if len(emoji_pattern.findall(text)) >= 3:
         is_spam = True

    if is_spam:
        try:
            await update.message.delete()
            warning = await context.bot.send_message(
                chat_id=chat_id, 
                text=f"⚠️ {update.message.from_user.first_name}, у нас тут без спама и ссылок!"
            )
            await asyncio.sleep(15)
            await warning.delete()
        except Exception as e:
            pass
        
        raise ApplicationHandlerStop

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ВАСИ ====================
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
        if (datetime.now() - last["time"]).seconds < 300:
            return 
    last_questions[chat_id] = {"text": user_text, "time": datetime.now()}

    # Калькулятор (срабатывает только если есть цифры и слова про доход)
    amount_match = re.search(r'(\d+[\.,]?\d*)\s*(?:тыс|к|k|$)', user_text, re.IGNORECASE)
    if amount_match and any(word in user_text.lower() for word in ["доход", "заработа", "получ", "сколько", "прибыль", "через"]):
        try:
            amount = float(amount_match.group(1).replace(',', '.'))
            if 'тыс' in user_text.lower() or 'к' in user_text.lower(): amount *= 1000
            months_match = re.search(r'(\d+)\s*(?:мес|месяц|м|month)', user_text, re.IGNORECASE)
            months = int(months_match.group(1)) if months_match else 12

            total = amount * (1.10 ** months)
            profit = total - amount
            reply = f"💸 Считаю...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$\n\nНеплохо, а?"
            await update.message.reply_text(reply)
            return
        except:
            pass

    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name)

    if reply:
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, reply)
    else:
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

# ==================== КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("О, привет! 😎\nЯ — Вася. Тут главный по веселью. Спрашивай, если чё!")

# ==================== ЗАПУСК ====================
def main():
    print("🚀 Запуск Васи Пердюкова...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_spam), group=0)
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=1)
    app.add_handler(CommandHandler("start", start))

    print("✅ Вася на посту!")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
