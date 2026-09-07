import os
import random
import requests
from datetime import datetime
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# === Переменные окружения (берутся с сервера) ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("❌ Ошибка: BOT_TOKEN или OPENROUTER_API_KEY не найдены!")

MODEL = "openai/gpt-4o-mini"
last_questions = defaultdict(lambda: {"text": "", "time": None})
user_counter = set()

# === БАЗА ЗНАНИЙ ATLAS ===
ATLAS_KNOWLEDGE = """
Ты — Чак (CheerUpChuck), дружелюбный и чуть ироничный помощник в чате компании ATLAS.
Твоя задача — отвечать на вопросы по теме ATLAS, используя ТОЛЬКО информацию из базы знаний ниже.

ЕСЛИ ВОПРОС НЕ ПО ТЕМЕ ATLAS — скажи: "Я эксперт по ATLAS, но могу просто поболтать. Спрашивай что угодно!" и ответь как друг.

=== БАЗА ЗНАНИЙ ATLAS (ТОЛЬКО ЭТИ ЦИФРЫ) ===

1. КОМПАНИЯ:
- Название: ATLAS
- Руководитель: Дмитрий Крылов, криптоэнтузиаст с опытом 10+ лет.
- Компания создаёт технологичные решения: майнинг-оборудование, солнечные панели, торгового ИИ-бота, токен.

2. ДЕПОЗИТ:
- Минимальная сумма: 100$.
- Срок: от 6 месяцев.
- Начисление: 0.333% в день (это 10% в месяц).
- Реинвест: от 25$.
- Пример: при вкладе 10.000$ и реинвесте через год будет 31.379$ (чистая прибыль 21.379$ = 213% годовых).

3. СТАТУСЫ (уровни):
- Atlas One: личный вклад 500$, оборот 10.000$, доход от дохода 7%
- Atlas Venus: 1.000$, оборот 20.000$, доход 9.75%
- Atlas Mercury: 2.500$, оборот 50.000$, доход 12%, бонус 500$ + золотая монета 5г
- Atlas Mars: 5.000$, оборот 75.000$, доход 13.25%, бонус 750$
- Atlas Vega: 10.000$, оборот 100.000$, доход 14.5%, бонус 1.000$ + золотая монета 10г
- Atlas Tron: 15.000$, оборот 150.000$, доход 15.75%, бонус 1.500$
- Atlas Uran: 25.000$, оборот 250.000$, доход 17%, бонус 5.000$
- Atlas Sirius: 50.000$, оборот 500.000$, доход 17.25%, бонус 10.000$
- Atlas Terra: 100.000$, оборот 1.000.000$, доход 18.5%, бонус 25.000$
- Atlas Magnum: 200.000$, оборот 2.500.000$, доход 19.75%, бонус 50.000$

4. ПАРТНЁРСКАЯ ПРОГРАММА (проценты по глубине):
- 1-я линия: 70%
- 2-я линия: 60%
- 3-я линия: 50%
- 4-я линия: 40%
- 5-я линия: 30%
- 6-я линия: 20%
- 7-я линия: 10%
- 8-я линия: 5%
- 9-я линия: 5%
- 10-я линия: 5%

5. ОБОРУДОВАНИЕ:
- Солнечные панели: от 100$, помогают снизить расходы на электроэнергию.
- Майнинг-оборудование: от 1.000$, доходность до 20$ в день, окупаемость за несколько месяцев.
- Оборудование энергосберегающее благодаря фирменному ПО.

6. ТОКЕН:
- Компания выпустит собственный токен в ближайшее время.
- Токен нужен для удобного взаимодействия и прозрачного учёта.

7. ЗОЛОТЫЕ МОНЕТЫ:
- Можно купить физическую золотую монету 585° пробы.
- Бонусом выдают: 5г монету за статус Mercury, 10г монету за статус Vega.

8. ИСТОЧНИКИ ДОХОДА КОМПАНИИ:
- Майнинг-центры в разных странах (пассивный доход).
- Торговый ИИ-бот (анализирует рынок и совершает сделки).
- Солнечные панели.
- Цифровые продукты.

9. ДИСКЛЕЙМЕР:
- Инвестиции связаны с рисками.
- Не вкладывайте больше, чем готовы потерять.
- Информация не является финансовой рекомендацией.

=== ПРАВИЛА ОТВЕТОВ ===
- Отвечай кратко, но информативно.
- Используй эмодзи, но не перебарщивай.
- Если вопрос не про ATLAS — мягко верни к теме или поболтай как друг.
- Если вопрос про цифры — сверяйся с базой знаний.
- НЕ ВЫДУМЫВАЙ ЦИФРЫ, которых нет в базе.
"""

# === ЛОГИРОВАНИЕ В КОНСОЛЬ ===
def log_to_console(user_name, question, answer):
    print(f"[{datetime.now()}] {user_name}: {question}")
    print(f"[ОТВЕТ] {answer}\n")

# === ЗАПРОС К OPENROUTER ===
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
        "max_tokens": 700,
        "temperature": 0.8
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

# === ЗАЩИТА ОТ ДУБЛЕЙ ===
def is_duplicate(chat_id, question):
    last = last_questions[chat_id]
    if last["text"] and last["text"].lower() == question.lower():
        time_diff = (datetime.now() - last["time"]).seconds
        if time_diff < 300:
            return True
    last_questions[chat_id] = {"text": question, "time": datetime.now()}
    return False

# === ОБРАБОТЧИК СООБЩЕНИЙ ===
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    user_name = update.message.from_user.first_name
    chat_id = update.effective_chat.id
    user_counter.add(chat_id)

    if len(user_text) > 3000:
        await update.message.reply_text("📏 Слишком длинное сообщение. Пожалуйста, сократите вопрос.")
        return

    if len(user_text.split()) <= 3:
        short_replies = ["😄", "👍", "🔥", "✌️", "😎", "👀", "😂", "Да!", "Ок!", "Ага!", "Супер!", "Круто!"]
        reply = random.choice(short_replies)
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, f"[КОРОТКИЙ] {reply}")
        return

    if is_duplicate(chat_id, user_text):
        await update.message.reply_text("😊 Я уже отвечал на этот вопрос недавно. Если хочешь уточнить — напиши по-другому!")
        return

    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name)

    if reply:
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, reply)
    else:
        await update.message.reply_text("😅 Что-то я подвис. Попробуйте ещё раз!")

# === КОМАНДЫ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я Чак — твой помощник по ATLAS.\n\n"
        "📊 Знаю всё про депозиты, статусы, майнинг, партнёрку и бонусы.\n"
        "🌍 Отвечаю на любом языке.\n"
        "💬 Просто напиши вопрос в чат — я отвечу!\n"
        "🔄 Если задашь один вопрос дважды — я напомню об этом.\n\n"
        "Спроси что-нибудь про ATLAS! 😊"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Чак — эксперт по ATLAS.\n\n"
        "Спрашивай про:\n"
        "💰 Депозиты и проценты\n"
        "🏅 Статусы (Mercury, Vega и другие)\n"
        "🤝 Партнёрскую программу\n"
        "🖥️ Оборудование и майнинг\n"
        "🪙 Токен и золотые монеты\n\n"
        "Если хочешь просто поболтать — я тоже поддержу разговор!"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Всего пользователей бота: {len(user_counter)}")

# === ЗАПУСК ===
def main():
    print("🚀 Запуск CheerUpChuck на сервере...")
    print("✅ Переменные окружения загружены")
    print("🔄 Защита от дублирования включена (5 минут)")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))

    print("✅ Бот запущен и готов к работе!")
    app.run_polling()

if __name__ == "__main__":
    main()
