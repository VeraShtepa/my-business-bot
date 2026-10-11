# FunBot.py — Вася Пердюков 2.0
import os
import random
import sqlite3
import requests
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

from prompt import build_system_prompt, MOODS, INITIATIVE_PROMPTS

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1003835539142"))  # Вася пишет сюда сам
MODEL = "cognitivecomputations/dolphin-mistral-24b-venice-edition"
MSK = ZoneInfo("Europe/Moscow")
DB_PATH = os.getenv("DB_PATH", "vasya.db")

if not BOT_TOKEN or not OPENROUTER_API_KEY:
    raise ValueError("❌ BOT_TOKEN или OPENROUTER_API_KEY не найдены!")

# ==================== БАЗА ДАННЫХ ====================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        nickname TEXT,
        facts TEXT DEFAULT '',
        msg_count INTEGER DEFAULT 0,
        last_seen TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        role TEXT,
        content TEXT,
        ts TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS state (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    conn.commit()
    conn.close()

def db_get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, nickname, facts, msg_count FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def db_upsert_user(user_id, name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, name, last_seen) VALUES (?, ?, ?)",
              (user_id, name, datetime.now(MSK).isoformat()))
    c.execute("UPDATE users SET name=?, msg_count=msg_count+1, last_seen=? WHERE user_id=?",
              (name, datetime.now(MSK).isoformat(), user_id))
    conn.commit()
    conn.close()

def db_add_fact(user_id, fact):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT facts FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row:
        facts = row[0] or ""
        fact_list = [f for f in facts.split("|") if f]
        if fact not in fact_list:
            fact_list.append(fact)
            fact_list = fact_list[-10:]
        c.execute("UPDATE users SET facts=? WHERE user_id=?", ("|".join(fact_list), user_id))
    conn.commit()
    conn.close()

def db_get_facts(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT facts FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return [f for f in (row[0] or "").split("|") if f] if row else []

def db_save_message(user_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO history (user_id, role, content, ts) VALUES (?, ?, ?, ?)",
              (user_id, role, content, datetime.now(MSK).isoformat()))
    c.execute("""DELETE FROM history WHERE id NOT IN (
        SELECT id FROM history WHERE user_id=? ORDER BY id DESC LIMIT 30
    ) AND user_id=?""", (user_id, user_id))
    conn.commit()
    conn.close()

def db_get_history(user_id, limit=10):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM history WHERE user_id=? ORDER BY id DESC LIMIT ?",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return list(reversed(rows))

def db_get_state(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM state WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default

def db_set_state(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO state (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_mood():
    """Настроение меняется раз в 3 часа."""
    last_change = db_get_state("mood_changed")
    now = datetime.now(MSK)
    if not last_change or (now - datetime.fromisoformat(last_change)).total_seconds() > 3 * 3600:
        mood = random.choice(list(MOODS.keys()))
        db_set_state("mood", mood)
        db_set_state("mood_changed", now.isoformat())
        return mood
    return db_get_state("mood", "бодрый")

# ==================== ЗАПРОС К ИИ ====================
def ask_ai(question, user_id, user_name, extra_system=None):
    mood = get_mood()
    facts = db_get_facts(user_id)
    system = build_system_prompt(mood, user_name, facts)
    if extra_system:
        system = extra_system + "\n\n" + system

    history = db_get_history(user_id, limit=10)
    messages = [{"role": "system", "content": system}]
    for role, content in history:
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": f"{user_name} пишет: {question}"})

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 250,
        "temperature": 0.95
    }
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            return content.strip() if content else None
        print(f"API error: {r.status_code} — {r.text[:200]}")
        return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

# ==================== КАЛЬКУЛЯТОР ====================
def calculate_income(amount, months):
    total = amount
    for _ in range(months):
        total *= 1.10
    return round(total, 2), round(total - amount, 2)

# ==================== ОСНОВНОЙ ОБРАБОТЧИК ====================
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    msg = update.message
    user_text = msg.text.strip()
    user = msg.from_user
    user_id = user.id
    user_name = user.first_name or "друг"

    db_upsert_user(user_id, user_name)

    if any(p in user_text.lower() for p in ["кто ты", "ты кто", "кто такой", "представься"]):
        reply = "Я? Вася Пердюков! Местный балагур. А ты кто?"
        await msg.reply_text(reply)
        db_save_message(user_id, "user", user_text)
        db_save_message(user_id, "assistant", reply)
        return

    amount_match = re.search(r'(\d+[\.,]?\d*)\s*(?:тыс|к|k|\$)?', user_text, re.IGNORECASE)
    if amount_match and any(w in user_text.lower() for w in
                            ["доход", "заработа", "получ", "сколько", "калькулят", "прибыль", "через"]):
        try:
            amount = float(amount_match.group(1).replace(',', '.'))
            if any(w in user_text.lower() for w in ["тыс", "к", "k"]):
                amount *= 1000
            months_match = re.search(r'(\d+)\s*(?:мес|месяц|м|month)', user_text, re.IGNORECASE)
            months = int(months_match.group(1)) if months_match else 12
            if amount > 0 and months > 0:
                total, profit = calculate_income(amount, months)
                reply = (f"💸 Считаю...\n\n💰 Вклад: {amount:.2f}$\n📅 Срок: {months} мес.\n"
                         f"📈 Итог: {total:.2f}$\n🤑 Прибыль: {profit:.2f}$\n\nНеплохо, а?")
                await msg.reply_text(reply)
                db_save_message(user_id, "user", user_text)
                db_save_message(user_id, "assistant", reply)
                return
        except Exception:
            pass

    await msg.chat.send_action(action="typing")
    reply = ask_ai(user_text, user_id, user_name)

    if reply:
        await msg.reply_text(reply)
        db_save_message(user_id, "user", user_text)
        db_save_message(user_id, "assistant", reply)
        print(f"[{datetime.now(MSK).strftime('%H:%M')}] {user_name}: {user_text}")
        print(f"[ВАСЯ/{get_mood()}] {reply}\n")
    else:
        await msg.reply_text("😅 Чё-то я подвис. Повтори?")

# ==================== ИНИЦИАТИВА ====================
async def vasya_initiative(context: ContextTypes.DEFAULT_TYPE):
    task = random.choice(INITIATIVE_PROMPTS)
    mood = get_mood()
    system = build_system_prompt(mood, "чат", [])
    system += f"\n\n=== ЗАДАНИЕ ===\n{task}"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "Напиши сообщение в чат."}
        ],
        "max_tokens": 150,
        "temperature": 0.95
    }
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            text = r.json()["choices"][0]["message"]["content"].strip()
            await context.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
            print(f"[ИНИЦИАТИВА/{mood}] {text}\n")
    except Exception as e:
        print(f"Ошибка инициативы: {e}")

# ==================== КОМАНДЫ ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "О, привет! 😎\n\nЯ — Вася Пердюков. Местный балагур и знаток ATLAS.\n"
        "Со мной можно и по делу, и просто поболтать.\n\n"
        "Команды: /top /riddle /answer /stats /mood"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ну чё, помогаю чем могу:\n\n"
        "💰 Депозиты и проценты\n🏅 Статусы\n🤝 Партнёрка\n"
        "🖥️ Майнинг и панели\n🪙 Токен и монеты\n\n"
        "📊 /top — топ чата\n🧩 /riddle — загадка\n"
        "🤓 /answer — ответ\n🎭 /mood — моё настроение"
    )

async def mood_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mood = get_mood()
    await update.message.reply_text(f"🎭 Сейчас я {mood}. О как!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    count = c.fetchone()[0]
    conn.close()
    await update.message.reply_text(f"👥 Всего нас тут: {count} человек. О как!")

async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, msg_count FROM users ORDER BY msg_count DESC LIMIT 5")
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text("📊 Пока никто не писал.")
        return
    text = "📊 **Топ-чата:**\n\n" + "\n".join(f"👤 {n} — {c} сообщений" for n, c in rows)
    await update.message.reply_text(text)

async def riddle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    riddles = [
        {"q": "Что растёт, когда вкладываешь, и уменьшается, когда выводишь?", "a": "Депозит!"},
        {"q": "Что может быть и золотым, и цифровым, и всегда в цене?", "a": "Криптовалюта!"},
        {"q": "Что даёт свет и деньги, но не требует счётчика?", "a": "Солнечная панель!"},
        {"q": "Кто работает 24/7, не пьёт, не ест и приносит доход?", "a": "Майнинг-бот!"},
    ]
    r = random.choice(riddles)
    await update.message.reply_text(f"🧩 **Загадка от Васи:**\n\n{r['q']}")
    context.user_data['riddle_answer'] = r['a']

async def answer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = context.user_data.get('riddle_answer', "Загадку я уже забыл, давай новую: /riddle")
    await update.message.reply_text(f"🤓 **Ответ:** {answer}")

# ==================== ЗАПУСК ====================
def main():
    db_init()
    print("🚀 Запуск Васи 2.0...")
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("top", top_command))
    app.add_handler(CommandHandler("riddle", riddle_command))
    app.add_handler(CommandHandler("answer", answer_command))
    app.add_handler(CommandHandler("mood", mood_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))

    if app.job_queue:
        app.job_queue.run_repeating(vasya_initiative, interval=5 * 3600, first=600)
        print("✅ Инициатива включена (каждые ~5 часов, первый раз через 10 минут)")

    print("✅ Вася 2.0 в деле!")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
