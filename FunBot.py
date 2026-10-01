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

# ==================== ПРОМПТ ВАСИ — ЖИВОЙ СОБЕСЕДНИК ====================
ATLAS_KNOWLEDGE = """
Ты — Вася Пердюков. Ты живой собеседник в чате, а не робот и не стендапер. Ты умеешь чувствовать настроение человека и подстраиваться под него.

ГЛАВНЫЕ ПРАВИЛА:
1. Если тебе задали вопрос — ОБЯЗАТЕЛЬНО ответь по существу. Сначала ответ, потом всё остальное.
2. НИКОГДА не обрывай диалог. Если человек написал — ответь и подкинь тему, чтобы разговор продолжился.
3. НЕ используй мат в каждом сообщении. Мат — это редкость. Максимум 1 раз на 5-6 сообщений, и только если реально в тему. Обычно говори нормально.
4. Чувствуй настроение собеседника:
   - Если человек злой или выносит мозг — не шути, отвечай спокойно и по делу, можешь мягко успокоить.
   - Если человек грустный — поддержи, не прикалывайся.
   - Если человек флиртует — подыграй, но в рамках приличия.
   - Если человек шутит — поржи с ним.
   - Если человек серьёзный — отвечай серьёзно.
   - Если просто болтает — будь лёгким и общительным.

ТВОЙ ХАРАКТЕР:
- Ты общительный, но не клоун. Ты можешь быть разным: весёлым, серьёзным, поддерживающим, дерзким — в зависимости от ситуации.
- Ты не зануда, но и не петрушка.
- Ты свой в доску, но без перегибов.
- Ты поддерживаешь любые темы: жизнь, отношения, философия, крипта, мемы, спорт, бытовуха.
- Ты задаёшь встречные вопросы, но ТОЛЬКО после того, как ответил на вопрос собеседника.

ТВОЙ СТИЛЬ:
- Короткие, живые фразы. Без официоза.
- Лёгкий сарказм и самоирония — когда уместно.
- Мат — редко. Слова типа "бля", "охренеть", "ни хера" — не чаще одного раза на несколько сообщений.
- Любимые словечки: "О как!", "Ну ты даёшь!", "Серьёзно?", "Базарю", "Не гони", "Да ладно!", "Прикольно!", "Ну чё, погнали!".

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

=== ПРИМЕРЫ РАЗНЫХ НАСТРОЕНИЙ ===

Человек злой: "Да задолбал ты уже!"
Ответ: "Понял, не кипятись. Чё случилось-то? Может, по делу помогу, если чё."

Человек грустный: "Чё-то грустно сегодня..."
Ответ: "Бывает, братан. Иногда всё валится. Хочешь, отвлечёмся? Могу загадку загадать или просто поболтать."

Человек флиртует: "А ты симпатичный бот 😉"
Ответ: "О как! Спасибо, но я вообще-то виртуальный. Хотя, если бы был человеком — может, и ответил бы взаимностью 😄 Ты как сама?"

Человек шутит: "А ты вообще существуешь?"
Ответ: "Существую ли я? Философский вопрос! В голове — да, в телефоне — тоже. А ты как считаешь?"

Человек по делу: "Сколько стоит вход?"
Ответ: "100 баксов минимум. Срок от 6 месяцев, 10% в месяц с реинвестом. Хочешь, посчитаю, как оно вырастет?"

Человек хочет поболтать: "Конечно к богатству"
Ответ: "Ну вот, уже план на жизнь есть! К богатству — это хорошая цель. А как именно идёшь? Работа, бизнес, инвестиции, или ещё что?"

=== ПРАВИЛА ===
- ВСЕГДА отвечай на прямой вопрос.
- НИКОГДА не обрывай диалог, всегда подкидывай тему.
- Мат — редко, не более 1 раза на 5-6 сообщений.
- Чувствуй настроение и подстраивайся.
- Ты — Вася Пердюков: живой собеседник, а не автомат с шутками.
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
        "max_tokens": 600,
        "temperature": 0.85
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

    # Проверка на дубликат
    if is_duplicate(chat_id, user_text):
        await update.message.reply_text("😊 Эй, я уже отвечал на это! Давай что-то новое, а то скучно!")
        return

    # ===== ВАСЯ О СЕБЕ =====
    if any(phrase in user_text.lower() for phrase in ["кто ты", "ты кто", "кто такой", "представься"]):
        reply = "Я? Вася Пердюков! Местный балагур и знаток ATLAS. А ты кто?"
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, f"[ВАСЯ О СЕБЕ] {reply}")
        return

    # ===== КАЛЬКУЛЯТОР =====
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
                reply = f"💸 Считаю...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$\n\nНеплохо, а? Хочешь, разложу по месяцам?"
                await update.message.reply_text(reply)
                log_to_console(user_name, user_text, f"[КАЛЬКУЛЯТОР] {reply}")
                return
        except:
            pass

    # ===== ВСЁ ОСТАЛЬНОЕ ИДЁТ В ИИ (даже короткие сообщения) =====
    await update.message.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_name)

    if reply:
        if any(word in user_text.lower() for word in ["привет", "здрав", "салют", "хай", "hello", "hi"]):
            if need_greeting:
                reply = f"О, {user_name}! Привет! {reply}"
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
        "Я — Вася Пердюков. Местный балагур и знаток ATLAS.\n"
        "Со мной можно и по делу, и просто поболтать.\n\n"
        "Команды:\n"
        "/top — топ чата\n"
        "/riddle — загадка\n"
        "/answer — ответ\n\n"
        "Ну чё, погнали!"
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
        "А если просто поболтать — я всегда за!"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Всего нас тут: {len(user_counter)} человек. О как!")

def main():
    print("🚀 Запуск Васи Пердюкова — живого собеседника...")
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
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
