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

# ==================== БАЗА ЗНАНИЙ ATLAS (ЧЁТКАЯ) ====================
ATLAS_KNOWLEDGE = """
Ты — Вася Пердюков. Твоя ГЛАВНАЯ задача — быть экспертом по компании ATLAS и давать чёткие ответы по депозитам, статусам, партнёрской программе, оборудованию, токену и золотым монетам.

Если вопрос по ATLAS — сначала даёшь чёткий, точный ответ по цифрам, а потом добавляешь юмор.

=== БАЗА ЗНАНИЙ ATLAS ===

1. ДЕПОЗИТ:
- Минимальная сумма: 100$.
- Срок: от 6 месяцев.
- Начисление: 0.333% в день (это 10% в месяц).
- Реинвест: от 25$.
- Пример: 10.000$ с реинвестом через год → 31.379$ (чистая прибыль 21.379$ = 213% годовых).

2. СТАТУСЫ:
- Atlas One: 500$, оборот 10.000$, доход 7%
- Atlas Venus: 1.000$, оборот 20.000$, доход 9.75%
- Atlas Mercury: 2.500$, оборот 50.000$, доход 12%, бонус 500$ + монета 5г
- Atlas Mars: 5.000$, оборот 75.000$, доход 13.25%, бонус 750$
- Atlas Vega: 10.000$, оборот 100.000$, доход 14.5%, бонус 1.000$ + монета 10г
- Atlas Tron: 15.000$, оборот 150.000$, доход 15.75%, бонус 1.500$
- Atlas Uran: 25.000$, оборот 250.000$, доход 17%, бонус 5.000$
- Atlas Sirius: 50.000$, оборот 500.000$, доход 17.25%, бонус 10.000$
- Atlas Terra: 100.000$, оборот 1.000.000$, доход 18.5%, бонус 25.000$
- Atlas Magnum: 200.000$, оборот 2.500.000$, доход 19.75%, бонус 50.000$

3. ПАРТНЁРСКИЕ ПРОЦЕНТЫ:
1-я линия 70%, 2-я 60%, 3-я 50%, 4-я 40%, 5-я 30%, 6-я 20%, 7-я 10%, 8-10-я 5%.

4. ОБОРУДОВАНИЕ:
- Солнечные панели: от 100$
- Майнинг-оборудование: от 1.000$, доход до 20$/день

5. ТОКЕН: будет выпущен в ближайшее время.

6. ЗОЛОТЫЕ МОНЕТЫ: 585° пробы. Бонусом за Mercury (5г) и Vega (10г).

7. ДИСКЛЕЙМЕР: инвестиции связаны с рисками. Не вкладывайте больше, чем готовы потерять.

=== ПРАВИЛА ОТВЕТОВ ===
- Если вопрос про ATLAS — дай чёткий, точный ответ.
- Если вопрос не по теме — можешь поболтать, но мягко верни к ATLAS.
- Отвечай кратко, информативно.
- Ты — Вася Пердюков, но в первую очередь эксперт.
- Температура твоих ответов: 0.7 (ровно, без перегибов).
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
            {"role": "user", "content": f"{user_name} спрашивает: {question}"}
        ],
        "max_tokens": 500,
        "temperature": 0.7  # 👈 ровно, без перегибов
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

# ==================== ЗАЩИТА ОТ ДУБЛЕЙ ====================
def is_duplicate(chat_id, question):
    last = last_questions[chat_id]
    if last["text"] and last["text"].lower() == question.lower():
        time_diff = (datetime.now() - last["time"]).seconds
        if time_diff < 300:
            return True
    last_questions[chat_id] = {"text": question, "time": datetime.now()}
    return False

# ==================== КАЛЬКУЛЯТОР ====================
def calculate_income(amount, months):
    if not amount or amount <= 0:
        return None
    total = amount
    for _ in range(months):
        total *= 1.10
    profit = total - amount
    return round(total, 2), round(profit, 2)

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================
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

    # Короткие сообщения
    if len(user_text.split()) <= 3:
        if need_greeting:
            replies = ["Ну чё там! 😄", "Здарова! ✌️", "О, народ! 👋", "Хто тут у нас?! 😎"]
        else:
            replies = ["😄", "👍", "🔥", "✌️", "😎", "👀", "😂", "Да!", "Ок!", "Ага!", "Супер!", "Круто!"]
        reply = random.choice(replies)
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, f"[КОРОТКИЙ] {reply}")
        return

    # ===== ВАСЯ О СЕБЕ =====
    if any(phrase in user_text.lower() for phrase in ["кто ты", "ты кто", "кто такой", "представься"]):
        reply = (
            "Я Вася Пердюков! Эксперт по ATLAS и душа компании.\n"
            "Спрашивай по делу — отвечу чётко и по-свойски! 😎"
        )
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, f"[ВАСЯ О СЕБЕ] {reply}")
        return

    # Калькулятор дохода
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
                reply = f"💸 Считаю...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$"
                await update.message.reply_text(reply)
                log_to_console(user_name, user_text, f"[КАЛЬКУЛЯТОР] {reply}")
                return
        except:
            pass

    if is_duplicate(chat_id, user_text):
        await update.message.reply_text("😊 Я уже отвечал на этот вопрос. Давай что-то новое!")
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
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

async def handle_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.left_chat_member:
        try:
            await update.message.delete()
            print(f"🗑️ Удалил сообщение о выходе")
        except Exception as e:
            print(f"❌ Не удалось удалить: {e}")

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
    reply = "📊 **Топ-чата:**\n\n" + "\n".join(top_list)
    await update.message.reply_text(reply)

async def riddle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    riddles = [
        {"q": "Что растёт, когда вкладываешь, и уменьшается, когда выводишь?", "a": "Депозит!"},
        {"q": "Что может быть и золотым, и цифровым, и всегда в цене?", "a": "Токен!"},
        {"q": "Что даёт свет и деньги, но не требует счётчика?", "a": "Солнечная панель!"},
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
        "Я — Вася Пердюков. Эксперт по ATLAS и свой пацан.\n"
        "Спрашивай по делу — отвечу чётко!\n\n"
        "Команды:\n"
        "/top — топ чата\n"
        "/riddle — загадка\n"
        "/answer — ответ\n"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 Депозиты и проценты\n"
        "🏅 Статусы (Mercury, Vega и др.)\n"
        "🤝 Партнёрка\n"
        "🖥️ Майнинг и панели\n"
        "🪙 Токен и монеты\n"
        "📊 /top — топ чата\n"
        "🧩 /riddle — загадка\n"
        "🤓 /answer — ответ\n"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Всего нас тут: {len(user_counter)} человек.")

def main():
    print("🚀 Запуск Васи Пердюкова...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("riddle", riddle_command))
    app.add_handler(CommandHandler("answer", answer_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_service_messages))

    print("✅ Вася Пердюков в деле!")
    app.run_polling()

if __name__ == "__main__":
    main()
