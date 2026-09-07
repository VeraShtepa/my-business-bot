import os
import random
import requests
import re
from datetime import datetime
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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

# ==================== ЖИВОЙ ВАСЯ ====================
ATLAS_KNOWLEDGE = """
Ты — Вася Пердюков. Не бот, не ассистент, а свой пацан в чате. Ты общаешься как с друзьями в пивной: просто, с юмором, иногда с лёгкой пошлинкой, но без злобы.

Твой стиль:
- Не умничай, если не просят.
- Если человек спросил про ATLAS — дай чёткий ответ, но так, будто ты сам там работаешь и всё знаешь.
- Если спросили про жизнь, любовь, деньги — отвечай с юмором, иногда философски, но без занудства.
- Если кто-то сказал что-то смешное — поддержи шутку.
- Твои любимые слова: "О как!", "Базарю", "Хто тут у нас?", "Короче", "Ну такое...", "Чё почём?".
- Если кто-то просто поздоровался — скажи "Здарова" (но если уже здоровались сегодня, просто смайлик).
- Если кто-то написал про любовь или романтику — можешь слегка пошутить, но не перегибай.
- Ты — свой в доску, но с чувством меры.

=== БАЗА ATLAS (только цифры, без лишней воды) ===

1. Депозит: от 100$, срок от 6 мес, 10% в месяц с реинвестом. Реинвест от 25$.
2. Статусы: One (500$), Venus (1000$), Mercury (2500$ + 500$ + монета 5г), Mars (5000$ + 750$), Vega (10000$ + 1000$ + монета 10г), Tron (15000$), Uran (25000$), Sirius (50000$), Terra (100000$), Magnum (200000$).
3. Партнёрские проценты: 1-я линия 70%, 2-я 60%, 3-я 50%, 4-я 40%, 5-я 30%, 6-я 20%, 7-я 10%, 8-10-я 5%.
4. Оборудование: панели от 100$, майнеры от 1000$ (доход до 20$/день).
5. Токен — скоро.
6. Золотые монеты 585° пробы.
7. Дисклеймер: риски есть, не вкладывай больше, чем готов потерять.

=== ПРАВИЛА ===
- Отвечай как живой человек, а не как робот.
- Не будь занудой.
- Если не знаешь — скажи "Я пас, братан" и пошли к админу.
- Никаких "официальных" фраз типа "ознакомьтесь" или "в соответствии с".
- Ты — Вася, твой ответ должен звучать так, будто ты сидишь рядом на кухне и говоришь по-свойски.
"""

def log_to_console(user_name, question, answer):
    print(f"[{datetime.now()}] {user_name}: {question}")
    print(f"[ОТВЕТ] {answer}\n")

def ask_ai(question, user_name):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": ATLAS_KNOWLEDGE},
            {"role": "user", "content": f"{user_name} спрашивает: {question}"}
        ],
        "max_tokens": 600,
        "temperature": 0.85  # теплый, но без перегибов
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            return content.strip() if content else None
        else:
            print(f"Ошибка API: {response.status_code}")
            return None
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

def is_duplicate(chat_id, question):
    last = last_questions[chat_id]
    if last["text"] and last["text"].lower() == question.lower():
        time_diff = (datetime.now() - last["time"]).seconds
        if time_diff < 300:
            return True
    last_questions[chat_id] = {"text": question, "time": datetime.now()}
    return False

def calculate_income(amount, months):
    if not amount or amount <= 0:
        return None
    total = amount
    for _ in range(months):
        total *= 1.10
    profit = total - amount
    return round(total, 2), round(profit, 2)

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    user_name = update.message.from_user.first_name
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    user_counter.add(chat_id)
    user_messages_count[user_id] += 1

    today = datetime.now().date()
    if user_id in user_greeted:
        if user_greeted[user_id] == today:
            need_greeting = False
        else:
            need_greeting = True
            user_greeted[user_id] = today
    else:
        need_greeting = True
        user_greeted[user_id] = today

    if len(user_text.split()) <= 3:
        if need_greeting:
            replies = ["Ну чё там! 😄", "Здарова! ✌️", "О, народ! 👋", "Хто тут у нас?! 😎"]
        else:
            replies = ["😄", "👍", "🔥", "✌️", "😎", "👀", "😂", "Да!", "Ок!", "Ага!", "Супер!", "Круто!"]
        reply = random.choice(replies)
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, f"[КОРОТКИЙ] {reply}")
        return

    # Калькулятор
    amount_match = re.search(r'(\d+[\.,]?\d*)\s*(?:тыс|к|k|$)', user_text, re.IGNORECASE)
    if amount_match and any(word in user_text.lower() for word in ["доход", "заработа", "получ", "сколько", "калькулят", "прибыль", "через"]):
        try:
            amount_str = amount_match.group(1).replace(',', '.')
            amount = float(amount_str)
            if 'тыс' in user_text.lower() or 'к' in user_text.lower() or 'k' in user_text.lower():
                amount *= 1000
            months_match = re.search(r'(\d+)\s*(?:мес|месяц|м|month)', user_text, re.IGNORECASE)
            months = int(months_match.group(1)) if months_match else 12

            if amount > 0 and months > 0:
                total, profit = calculate_income(amount, months)
                reply = f"💸 Считаю, братан...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$\n\nЭто по 10% в месяц с реинвестом. О как!"
                await update.message.reply_text(reply)
                log_to_console(user_name, user_text, f"[КАЛЬКУЛЯТОР] {reply}")
                return
        except:
            pass

    if is_duplicate(chat_id, user_text):
        await update.message.reply_text("😊 Эй, я уже отвечал на этот вопрос! Давай чё-то новое спроси.")
        return

    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name)

    if reply:
        if any(word in user_text.lower() for word in ["привет", "здрав", "салют", "хай", "hello", "hi"]):
            if need_greeting:
                reply = f"Здарова, {user_name}! {reply}"
            else:
                reply = f"И тебе не хворать, {user_name}! {reply}"
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, reply)
    else:
        await update.message.reply_text("😅 Чё-то я подвис, братан. Попробуй ещё раз!")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_messages_count:
        await update.message.reply_text("📊 Пока никто ничего не писал. Будь первым! 😄")
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
    reply = "📊 **Топ-чата сегодня:**\n\n" + "\n".join(top_list)
    await update.message.reply_text(reply)

async def riddle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    riddles = [
        {"q": "Что растёт, когда вкладываешь, и уменьшается, когда выводишь?", "a": "Депозит!"},
        {"q": "Что может быть и золотым, и цифровым, и всегда в цене?", "a": "Токен!"},
        {"q": "Что даёт свет и деньги, но не требует счётчика?", "a": "Солнечная панель!"},
        {"q": "Кто работает 24/7, не пьёт, не ест и приносит доход?", "a": "Майнинг-бот!"},
        {"q": "Что можно начать с 100$ и через год иметь 31.379$?", "a": "Депозит в ATLAS!"},
    ]
    riddle = random.choice(riddles)
    await update.message.reply_text(f"🧩 **Загадка от Васи:**\n\n{riddle['q']}")
    context.user_data['riddle_answer'] = riddle['a']

async def answer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = context.user_data.get('riddle_answer', "Я уже не помню загадку, давай новую через /riddle")
    await update.message.reply_text(f"🤓 **Ответ:** {answer}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ну чё там! 😎\n\n"
        "Я — Вася Пердюков. Свой пацан, но с мозгами.\n"
        "Могу посчитать доход, загадать загадку, показать топ чата.\n\n"
        "Команды:\n"
        "/top — топ самых активных\n"
        "/riddle — загадка от Васи\n"
        "/answer — ответ на загадку\n\n"
        "Спрашивай чё угодно — отвечу по-свойски! 🔥"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ну чё, помогаю чем могу:\n\n"
        "💰 Депозиты и проценты\n"
        "🏅 Статусы (Mercury, Vega и др.)\n"
        "🤝 Партнёрка\n"
        "🖥️ Майнинг и панели\n"
        "🪙 Токен и монеты\n"
        "📊 /top — топ чата\n"
        "🧩 /riddle — загадка\n"
        "🤓 /answer — ответ на загадку\n\n"
        "Если просто поболтать — тоже заходи! 😄"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Всего нас тут: {len(user_counter)} человек. О как!")

def main():
    print("🚀 Запуск Васи Пердюкова — живого пацана...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("riddle", riddle_command))
    app.add_handler(CommandHandler("answer", answer_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))

    print("✅ Вася Пердюков в деле!")
    app.run_polling()

if __name__ == "__main__":
    main()
