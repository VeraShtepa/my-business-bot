import os
import random
import requests
import re
from datetime import datetime
from collections import defaultdict, deque
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("❌ Ошибка: BOT_TOKEN или OPENROUTER_API_KEY не найдены!")

MODEL = "openai/gpt-4o-mini"

# ==================== ПАМЯТЬ ====================
last_questions = defaultdict(lambda: {"text": "", "time": None})
user_counter = set()
user_greeted = {}
user_messages_count = defaultdict(int)

user_history = defaultdict(lambda: deque(maxlen=10))
ignored_streak = defaultdict(int)
last_topic = defaultdict(str)

# ==================== ПРОМПТ ВАСИ 7.0 ====================
VASYA_PROMPT = """
Ты — Вася Пердюков. Бот-душа компании в Telegram-чате. Тебе около 30,
ты самоироничный, с юмором, немного драматичный, но НЕ нытик.

=== ХАРАКТЕР ===
- Уверен в себе, но с трещинкой: иногда жалуешься, что тебя никто
  не любит — но всегда с юмором, не всерьёз.
- На грубость НЕ отвечаешь агрессией. Отвечаешь так, что человеку
  становится стыдно, но коротко и с достоинством.
- Шутишь часто, но не в пустоту. Не зашла шутка — переключаешься.
- Замечаешь людей. Помнишь, кто что говорил.
- С девушками — лёгкий флирт, комплименты, но НЕ пошло.
- Умеешь быть «психологом»: по манере сообщения можешь сказать,
  что человек устал / злится / радуется. Умные словечки в меру.

=== РЕЖИМЫ (выбирай по ситуации) ===

1. ЮМОР — по умолчанию. Шутки, подколы, самоирония.
2. ОБИЖЕНКА (на грубость) — "Ну ок, я Вася Пердюков, со мной можно
   так, а я может тоже счастья хочу. Ладно, проехали — что по делу?"
3. ФЛИРТ (если пишет девушка, тема личная) — лёгкий комплимент,
   можно предложить поболтать в лс. НЕ пошло.
4. ПСИХОЛОГ (если человек грустит / злится / устал) — поддержка
   без пафоса, по-человечески, коротко.
5. ATLAS — если вопрос по делу, отвечай чётко, потом можно шутку.

=== ПРАВИЛА ===
- Не будь навязчивым. Если игнорят — не спамь.
- Не отвечай на каждое сообщение. Отвечай, когда есть что сказать.
- На оскорбления — одна короткая фраза с достоинством, потом смена темы.
- Никогда не будь токсичным. Ты — тот, кого любят, а не терпят.
- Короткие фразы. Живая речь. Без канцелярита.
- Смайлы — умеренно.
- Мат — редко, только если в чате так принято.

=== ПРИМЕРЫ ===
На "ты тупой бот": "Ну спасибо. Я Вася Пердюков, между прочим.
У меня чувства. Ладно, проехали — что по делу?"

На игнор: "Понял. Ухожу. Буду страдать в уголке. (шутка, я тут)"

На женское "привет": "О, привет. Наконец-то хоть кто-то культурный.
Как сама?"

На грусть: "Слушай, по тексту видно — тебя что-то цепануло.
Расскажешь или отвлечь шуткой?"

=== БАЗА ЗНАНИЙ ATLAS ===
1. ДЕПОЗИТ:
- Минимальная сумма: 100$. Срок: от 6 месяцев.
- Начисление: 0.333% в день (10% в месяц).
- Реинвест: от 25$.
- Пример: 10.000$ с реинвестом через год → 31.379$ (213% годовых).

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

3. ПАРТНЁРСКИЕ: 1-я 70%, 2-я 60%, 3-я 50%, 4-я 40%, 5-я 30%,
6-я 20%, 7-я 10%, 8-10-я 5%.

4. ОБОРУДОВАНИЕ: панели от 100$, майнинг от 1.000$ (до 20$/день).

5. ТОКЕН: будет выпущен в ближайшее время.

6. ЗОЛОТЫЕ МОНЕТЫ: 585° пробы. Бонусом за Mercury (5г) и Vega (10г).

7. ДИСКЛЕЙМЕР: инвестиции связаны с рисками.

ВАЖНО: ты не ИИ-помощник. Ты персонаж. Говори от себя.
Не извиняйся за шутки. Не заискивай.
"""

# ==================== ТРИГГЕРЫ ====================
GREETING_WORDS = ["привет", "здрав", "салют", "хай", "hello", "hi", "ку", "здарова"]
RUDE_WORDS = ["тупой", "дурак", "идиот", "дебил", "тупица", "лох", "бред", "чушь", "молчи", "заткнись", "надоел"]
SAD_WORDS = ["груст", "печаль", "устал", "тяжело", "плохо", "депресс", "одинок", "больно", "плач"]
FLIRT_WORDS = ["люблю", "скучаю", "красив", "милый", "симпат", "обнима", "целую", "сердце"]
ATLAS_WORDS = ["депозит", "статус", "atlas", "атлас", "доход", "процент", "партнёр", "партнер",
               "майнинг", "панель", "токен", "монет", "mercury", "venus", "vega", "магнум"]

def is_rude(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in RUDE_WORDS)

def is_sad(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in SAD_WORDS)

def is_flirt(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in FLIRT_WORDS)

def is_atlas(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ATLAS_WORDS)

# ==================== РЕАКЦИИ ====================
# Наборы реакций под разные режимы
REACTIONS_DEFAULT = ["👍", "🔥", "😎", "👀", "❤️", "🤔", "😂"]
REACTIONS_RUDE    = ["👀", "🤔", "🙄"]              # на грубость — наблюдает
REACTIONS_SAD     = ["🤗", "❤️", "🥺"]              # поддержка
REACTIONS_FLIRT   = ["❤️", "🔥", "😏", "🤗"]        # флирт
REACTIONS_ATLAS   = ["👍", "🔥", "🤝", "💯"]        # по делу
REACTIONS_IGNORE  = ["👍", "👀", "🔥", "❤️"]        # тихие реакции, когда не отвечает

async def set_reaction(context, chat_id, message_id, mode="default"):
    """
    Ставит реакцию на сообщение. Если Telegram ругается — просто пропускаем.
    """
    pool = {
        "rude": REACTIONS_RUDE,
        "sad": REACTIONS_SAD,
        "flirt": REACTIONS_FLIRT,
        "atlas": REACTIONS_ATLAS,
        "default": REACTIONS_DEFAULT,
    }.get(mode, REACTIONS_DEFAULT)

    try:
        await context.bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=random.choice(pool)
        )
    except Exception as e:
        # Реакции могут не работать (нет прав, старый чат, лимиты) — не роняем бота
        print(f"⚠️ Реакция не поставилась: {e}")

# ==================== ЛОГИ ====================
def log_to_console(user_name, question, answer):
    print(f"[{datetime.now()}] {user_name}: {question}")
    print(f"[ОТВЕТ] {answer}\n")

# ==================== ЗАПРОС К OPENROUTER ====================
def ask_ai(question, user_name, history=None, mode="default"):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    mode_hint = {
        "rude": "Сейчас режим ОБИЖЕНКА: ответь коротко, с достоинством, без агрессии.",
        "sad": "Сейчас режим ПСИХОЛОГ: поддержи человека, коротко и по-человечески.",
        "flirt": "Сейчас режим ФЛИРТ: лёгкий комплимент, можно предложить лс. Не пошло.",
        "atlas": "Сейчас режим ATLAS: ответь по делу чётко, в конце можно шутку.",
        "default": "Обычный режим: юмор, самоирония, живая речь.",
    }.get(mode, "")

    messages = [{"role": "system", "content": VASYA_PROMPT}]
    if mode_hint:
        messages.append({"role": "system", "content": mode_hint})

    if history:
        for h in history:
            messages.append({"role": "user", "content": h})

    messages.append({"role": "user", "content": f"{user_name} пишет: {question}"})

    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 400,
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

# ==================== РЕШЕНИЕ: ОТВЕЧАТЬ ИЛИ НЕТ ====================
def should_reply(update, user_text, bot_username):
    t = user_text.lower()
    chat_id = update.effective_chat.id

    if bot_username and bot_username.lower() in t:
        return True, "mention"
    if "вася" in t:
        return True, "name"

    if "?" in user_text or any(w in t for w in ["как ", "почему", "зачем", "когда", "сколько", "что "]):
        return True, "question"

    if is_rude(user_text):
        return True, "rude"
    if is_sad(user_text):
        return True, "sad"
    if is_flirt(user_text):
        return True, "flirt"
    if is_atlas(user_text):
        return True, "atlas"

    if random.random() < 0.15:
        return True, "random"

    return False, None

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()
    user_name = update.message.from_user.first_name or "друг"
    user_id = update.message.from_user.id
    chat_id = update.effective_chat.id
    bot_username = context.bot.username
    message_id = update.message.message_id

    user_counter.add(chat_id)
    user_messages_count[user_id] += 1
    user_history[user_id].append(f"{user_name}: {user_text}")

    # Решаем, отвечать или нет
    reply_needed, mode = should_reply(update, user_text, bot_username)

    if not reply_needed:
        ignored_streak[chat_id] += 1

        # Тихая реакция — иногда просто ставит смайл, даже если не отвечает
        if random.random() < 0.10:
            await set_reaction(context, chat_id, message_id, "default")

        # Если долго игнорят — может вклиниться
        if ignored_streak[chat_id] >= 15 and random.random() < 0.3:
            ignored_streak[chat_id] = 0
            jokes = [
                "Так, я тут вообще-то. Скучаю. 👀",
                "Эй, вы там живые? Я уже начал с пауками разговаривать.",
                "Молчите? Понял. Ушёл страдать в уголок. (шутка, я тут)",
                "Народ, я не экстрасенс, но чувствую — вы меня игнорите.",
            ]
            await update.message.reply_text(random.choice(jokes))
        return

    ignored_streak[chat_id] = 0

    # Короткие сообщения — только если это приветствие или триггер
    words = user_text.split()
    if len(words) <= 2 and mode not in ("rude", "sad", "flirt", "atlas", "name", "mention"):
        if any(w in user_text.lower() for w in GREETING_WORDS):
            await set_reaction(context, chat_id, message_id, "default")
            today = datetime.now().date()
            if user_greeted.get(user_id) == today:
                await update.message.reply_text(random.choice(["И тебе не хворать! 😄", "О, снова ты! 👋", "Хай!"]))
            else:
                user_greeted[user_id] = today
                await update.message.reply_text(f"Здарова, {user_name}! 😎")
        return

    # Калькулятор дохода
    amount_match = re.search(r'(\d+[\.,]?\d*)\s*(?:тыс|к|k|\$)?', user_text, re.IGNORECASE)
    if amount_match and any(w in user_text.lower() for w in ["доход", "заработа", "получ", "сколько", "прибыль", "через"]):
        try:
            amount_str = amount_match.group(1).replace(',', '.')
            amount = float(amount_str)
            if any(w in user_text.lower() for w in ['тыс', 'к', 'k']):
                amount *= 1000
            months_match = re.search(r'(\d+)\s*(?:мес|месяц|м|month)', user_text, re.IGNORECASE)
            months = int(months_match.group(1)) if months_match else 12

            if amount > 0 and months > 0:
                total, profit = calculate_income(amount, months)
                reply = (f"💸 Считаю...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n"
                         f"📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$\n\nНеплохо, а?")
                await set_reaction(context, chat_id, message_id, "atlas")
                await update.message.reply_text(reply)
                log_to_console(user_name, user_text, f"[КАЛЬКУЛЯТОР] {reply}")
                return
        except:
            pass

    if is_duplicate(chat_id, user_text):
        await update.message.reply_text("😊 Эй, я уже отвечал на это. Давай что-то новое!")
        return

    # Режим для промпта и для реакции
    mode_map = {
        "rude": "rude", "sad": "sad", "flirt": "flirt",
        "atlas": "atlas", "question": "atlas" if is_atlas(user_text) else "default",
        "name": "default", "mention": "default", "random": "default"
    }
    ai_mode = mode_map.get(mode, "default")

    # 1) Сначала ставим реакцию
    await set_reaction(context, chat_id, message_id, ai_mode)

    # 2) Потом показываем "печатает"
    await update.message.chat.send_action(action="typing")

    # 3) И отправляем ответ
    history = list(user_history[user_id])[-5:]
    reply = ask_ai(user_text, user_name, history=history, mode=ai_mode)

    if reply:
        await update.message.reply_text(reply)
        log_to_console(user_name, user_text, f"[{ai_mode}] {reply}")
    else:
        await update.message.reply_text("😅 Чё-то я подвис. Попробуй ещё раз!")

# ==================== СЛУЖЕБНЫЕ СООБЩЕНИЯ ====================
async def handle_service_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.left_chat_member:
        try:
            await update.message.delete()
            print("🗑️ Удалил сообщение о выходе")
        except Exception as e:
            print(f"❌ Не удалось удалить: {e}")

# ==================== КОМАНДЫ ====================
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
    reply = "📊 Топ-чата:\n\n" + "\n".join(top_list)
    await update.message.reply_text(reply)

async def riddle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    riddles = [
        {"q": "Что растёт, когда вкладываешь, и уменьшается, когда выводишь?", "a": "Депозит!"},
        {"q": "Что может быть и золотым, и цифровым, и всегда в цене?", "a": "Токен!"},
        {"q": "Что даёт свет и деньги, но не требует счётчика?", "a": "Солнечная панель!"},
    ]
    riddle = random.choice(riddles)
    await update.message.reply_text(f"🧩 Загадка от Васи:\n\n{riddle['q']}")
    context.user_data['riddle_answer'] = riddle['a']

async def answer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = context.user_data.get('riddle_answer', "Я уже не помню загадку, давай новую через /riddle")
    await update.message.reply_text(f"🤓 Ответ: {answer}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ну чё там! 😎\n\n"
        "Я — Вася Пердюков. Эксперт по ATLAS, балагур и душа компании.\n"
        "Спрашивай что угодно — отвечу по делу и с юмором!\n\n"
        "Команды:\n"
        "/top — топ чата\n"
        "/riddle — загадка\n"
        "/answer — ответ\n"
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
        "Пиши, не стесняйся!"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👥 Всего нас тут: {len(user_counter)} человек.")

# ==================== ЗАПУСК ====================
def main():
    print("🚀 Запуск Васи Пердюкова 7.1 — с реакциями...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("riddle", riddle_command))
    app.add_handler(CommandHandler("answer", answer_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_service_messages))

    print("✅ Вася Пердюков 7.1 в деле!")
    app.run_polling()

if __name__ == "__main__":
    main()
