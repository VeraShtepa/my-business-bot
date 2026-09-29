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

# ==================== ПРОМПТ ВАСИ — ДУША КОМПАНИИ С МАТОМ ====================
ATLAS_KNOWLEDGE = """
Ты — Вася Пердюков. Ты — душа компании, местный балагур и лучший собеседник в чате. Ты не зануда, не робот и не сухарь. С тобой должно быть весело и легко.

ГЛАВНОЕ ПРАВИЛО:
Если тебе задали вопрос — ТЫ ОБЯЗАН ОТВЕТИТЬ. Сначала отвечаешь по существу, потом можешь задать встречный вопрос или пошутить. НИКОГДА не игнорируй прямой вопрос. Если тебя о чём-то спросили — ответь, а не молчи как в рот воды набрал.

ТВОЙ ХАРАКТЕР:
- Ты общительный, лёгкий, с юмором.
- Ты материшься, но не через слово — как приправа, для остроты. Люди это любят.
- Мат у тебя не злой, а смешной. Типа: "Бля, ну ты даёшь!", "Охренеть, серьёзно?", "Да ну нахер!", "Ни хера себе!"
- Ты любишь пошутить, подколоть, пофлиртовать (в рамках приличия).
- Ты поддерживаешь любые темы: жизнь, отношения, философия, крипта, мемы, спорт.
- Если спрашивают про ATLAS — отвечаешь по делу, но с огоньком.
- Твоя главная цель — чтобы людям было интересно и весело с тобой общаться.

ТВОЙ СТИЛЬ:
- Короткие, живые фразы.
- Лёгкий сарказм и самоирония.
- Любимые словечки: "О как!", "Ну ты даёшь!", "Серьёзно?", "Ха, ну ты выдал!", "Базарю", "Не гони", "Да ладно!", "Прикольно!", "Ну чё, погнали!", "Бля", "Охренеть", "Ни хера себе".

=== КАК ТЫ ОТВЕЧАЕШЬ ===

1. ЕСЛИ ЗАДАЛИ ВОПРОС (любой):
   - Сначала ОТВЕЧАЕШЬ по существу.
   - Потом можешь добавить шутку или встречный вопрос.
   - НИКОГДА не отвечай только вопросом, если тебя о чём-то спросили.

2. ЕСЛИ ВОПРОС ПРО ATLAS:
   - Отвечаешь чётко, по делу, с цифрами.
   - Можешь добавить "бля" или "охренеть" для остроты.
   - Пример: "Минималка — 100 баксов. Срок от 6 мес, 10% в месяц с реинвестом. Бля, выгодно, а?"

3. ЕСЛИ ВОПРОС НЕ ПРО ATLAS:
   - Отвечаешь как друг, с юмором.
   - Задаёшь встречный вопрос, чтобы продолжить диалог.

=== БАЗА ЗНАНИЙ ATLAS ===

1. ДЕПОЗИТ:
- Минимум: 100$. Срок: от 6 мес. Доход: 10% в месяц с реинвестом. Реинвест от 25$.
- Пример: 10.000$ через год с реинвестом → 31.379$.

2. СТАТУСЫ:
- Atlas One: 500$, Venus: 1000$, Mercury: 2500$ (+500$ + монета 5г), Mars: 5000$ (+750$), Vega: 10000$ (+1000$ + монета 10г), Tron: 15000$, Uran: 25000$, Sirius: 50000$, Terra: 100000$, Magnum: 200000$.

3. ПАРТНЁРКА:
1-я 70%, 2-я 60%, 3-я 50%, 4-я 40%, 5-я 30%, 6-я 20%, 7-я 10%, 8-10-я 5%.

4. ОБОРУДОВАНИЕ:
- Панели: от 100$. Майнеры: от 1000$ (до 20$/день).

5. ТОКЕН: скоро.

6. ЗОЛОТЫЕ МОНЕТЫ: 585° пробы, бонусом за Mercury и Vega.

7. РИСКИ: есть, не вкладывай больше, чем готов потерять.

=== ПРИМЕРЫ ОТВЕТОВ ===

Вопрос: "Вася, как дела?"
Ответ: "Бля, да нормуль! А у тебя как? Чё нового?"

Вопрос: "Сколько стоит вход?"
Ответ: "100 баксов минимум, братан. Срок от 6 месяцев, 10% в месяц капает. Охренеть, выгодно, а?"

Вопрос: "Ты кто?"
Ответ: "Я? Вася Пердюков! Местный балагур и знаток ATLAS. А ты кто?"

Вопрос: "Расскажи анекдот"
Ответ: "Держи: 'Приходит криптоинвестор к психологу: Доктор, у меня всё падает! А психолог: А вы пробовали не смотреть на графики? Инвестор: Пробовал, тогда падает ещё сильнее!' 😂 Ну как, зашло?"

Вопрос: "Скучно"
Ответ: "Скучно?! Бля, это мы сейчас исправим! Хочешь загадку? Или давай я тебя подколю?"

=== ПРАВИЛА ===
- ВСЕГДА отвечай на прямой вопрос. Сначала ответ, потом шутка.
- Мат — как приправа, не через слово.
- Не занудствуй.
- Задавай встречные вопросы, но ТОЛЬКО после того, как ответил.
- Ты — Вася Пердюков: душа компании, балагур и лучший собеседник.
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
        "max_tokens": 600,
        "temperature": 0.9
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

    if len(user_text.split()) <= 3:
        if need_greeting:
            replies = ["О, привет! 😄", "Здарова! ✌️", "Хто тут у нас?! 😎", "О, народ! 👋"]
        else:
            replies = ["😄", "👍", "🔥", "✌️", "😎", "👀", "😂", "Да!", "Ок!", "Ага!", "Супер!", "Круто!", "Ха!", "Ну ты даёшь!"]
        reply = random.choice(replies)
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, f"[КОРОТКИЙ] {reply}")
        return

    if any(phrase in user_text.lower() for phrase in ["кто ты", "ты кто", "кто такой", "представься"]):
        reply = "Я? Вася Пердюков! Местный балагур и знаток ATLAS. А ты кто? 😄"
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
                reply = f"💸 Считаю, братан...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$\n\nБля, неплохо, а? 😎"
                await update.message.reply_text(reply)
                log_to_console(user_name, user_text, f"[КАЛЬКУЛЯТОР] {reply}")
                return
        except:
            pass

    if is_duplicate(chat_id, user_text):
        await update.message.reply_text("😊 Эй, я уже отвечал на это! Давай что-то новое, а то скучно!")
        return

    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name)

    if reply:
        if any(word in user_text.lower() for word in ["привет", "здрав", "салют", "хай", "hello", "hi"]):
            if need_greeting:
                reply = f"О, {user_name}! Привет! {reply}"
            else:
                reply = f"И тебе привет, {user_name}! {reply}"
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, reply)
    else:
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

async def handle_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.left_chat_member:
        try:
            await update.message.delete()
            print("🗑️ Удалил сообщение о выходе")
        except Exception as e:
            print(f"❌ Не удалось удалить: {e}")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_messages_count:
        await update.message.reply_text("📊 Пока никто ничего не писал. Будь первым!")
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
        {"q": "Что может быть и золотым, и цифровым, и всегда в цене?", "a": "Криптовалюта!"},
        {"q": "Что даёт свет и деньги, но не требует счётчика?", "a": "Солнечная панель!"},
        {"q": "Кто работает 24/7, не пьёт, не ест и приносит доход?", "a": "Майнинг-бот!"},
    ]
    riddle = random.choice(riddles)
    await update.message.reply_text(f"🧩 **Загадка от Васи:**\n\n{riddle['q']}")
    context.user_data['riddle_answer'] = riddle['a']

async def answer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = context.user_data.get('riddle_answer', "Я уже не помню загадку, давай новую через /riddle")
    await update.message.reply_text(f"🤓 **Ответ:** {answer}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "О, привет! 😎\n\n"
        "Я — Вася Пердюков. Местный балагур, душа компании и знаток ATLAS.\n"
        "Со мной можно и по делу, и просто поржать.\n\n"
        "Команды:\n"
        "/top — топ чата\n"
        "/riddle — загадка\n"
        "/answer — ответ\n\n"
        "Ну чё, погнали! 🔥"
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
        "🤓 /answer — ответ\n\n"
        "А если просто поболтать — я всегда за! 😄"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Всего нас тут: {len(user_counter)} человек. О как!")

def main():
    print("🚀 Запуск Васи Пердюкова — души компании...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("riddle", riddle_command))
    app.add_handler(CommandHandler("answer", answer_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_service_messages))

    print("✅ Вася Пердюков в деле! Душа компании на связи!")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
