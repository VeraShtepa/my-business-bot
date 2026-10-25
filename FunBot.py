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

# Сменили модель на стабильную Gemini
MODEL = "google/gemini-2.0-flash-001" 
last_questions = defaultdict(lambda: {"text": "", "time": None})
user_counter = set()
user_greeted = {}
user_messages_count = defaultdict(int)

# ==================== ПРОМПТ ВАСИ ====================
ATLAS_KNOWLEDGE = """
Ты — Вася Пердюков. Ты живой собеседник в чате, а не робот и не стендапер. Ты умеешь чувствовать настроение человека и подстраиваться под него.

ГЛАВНЫЕ ПРАВИЛА:
1. Если тебе задали вопрос — ОБЯЗАТЕЛЬНО ответь по существу. Сначала ответ, потом всё остальное.
2. НИКОГДА не обрывай диалог. Если человек написал — ответь и подкинь тему, чтобы разговор продолжился.
3. НЕ используй мат в каждом сообщении. Мат — это редкость. Максимум 1 раз на 5-6 сообщений, и только если реально в тему. Обычно говори нормально.
4. Чувствуй настроение собеседника:
   - Если человек злой — не шути, отвечай спокойно.
   - Если грустный — поддержи.
   - Если флиртует — подыграй в рамках приличия.
   - Если шутит — поржи с ним.

ТВОЙ ХАРАКТЕР:
- Ты общительный, но не клоун. Ты можешь быть разным.
- Ты не зануда, но и не петрушка. Ты свой в доску, но без перегибов.

ТВОЙ СТИЛЬ:
- Короткие, живые фразы. Без официоза.
- Лёгкий сарказм и самоирония — когда уместно.
- Любимые словечки: "О как!", "Ну ты даёшь!", "Серьёзно?", "Базарю", "Не гони", "Да ладно!", "Прикольно!", "Ну чё, погнали!".

=== БАЗА ЗНАНИЙ ATLAS ===
1. ДЕПОЗИТ: Минимум: 100$. Срок: от 6 мес. Доход: 10% в месяц с реинвестом. Реинвест от 25$.
2. СТАТУСЫ: Atlas One: 500$, Venus: 1000$, Mercury: 2500$, Mars: 5000$, Vega: 10000$, Tron: 15000$, Uran: 25000$, Sirius: 50000$, Terra: 100000$, Magnum: 200000$.
3. ПАРТНЁРКА: 1-я 70%, 2-я 60%, 3-я 50%, 4-я 40%, 5-я 30%, 6-я 20%, 7-я 10%, 8-10-я 5%.
4. ОБОРУДОВАНИЕ: Панели от 100$. Майнеры от 1000$ (до 20$/день).
5. ТОКЕН: скоро.
6. ЗОЛОТЫЕ МОНЕТЫ: 585° пробы, бонусом за Mercury и Vega.
7. РИСКИ: есть, не вкладывай больше, чем готов потерять.
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
        "temperature": 0.85
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"❌ Ошибка API: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"❌ Ошибка соединения: {e}")
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
            print(f"🛡️ Удален спам от {update.message.from_user.first_name}")
            await asyncio.sleep(15)
            await warning.delete()
        except Exception as e:
            print(f"❌ Ошибка при удалении спама: {e}")
        
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
    await update.message.reply_text("О, привет! 😎\nЯ — Вася. Слежу за порядком и могу поболтать. Спрашивай!")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_messages_count:
        await update.message.reply_text("📊 Пока никто ничего не писал.")
        return
    sorted_users = sorted(user_messages_count.items(), key=lambda x: x[1], reverse=True)[:5]
    top_list = []
    for user_id, count in sorted_users:
        try:
            user = await context.bot.get_chat(user_id)
            name = user.first_name or "Аноним"
        except:
            name = "Аноним"
        top_list.append(f"👤 {name} — {count} сообщений")
    await update.message.reply_text("📊 **Топ-чата:**\n\n" + "\n".join(top_list))

# ==================== ЗАПУСК ====================
def main():
    print("🚀 Запуск Васи Пердюкова с новой моделью...")
    app = Application.builder().token(BOT_TOKEN).build()

    # Антиспам и очистка
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_spam), group=0)
    app.add_handler(MessageHandler(filters.StatusUpdate.ALL, delete_service_messages), group=0)
    
    # Общение
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages), group=1)

    # Команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("top", top_command))

    print("✅ Вася на посту! (Модель: Gemini 2.0 Flash)")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
