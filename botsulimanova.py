import os, logging, asyncio, sqlite3, csv, io
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")
MANAGER_ID = int(os.environ.get("MANAGER_ID", "1338569085"))
BRANCH     = "Сельпо"

# ВАЖНО: на Railway файловая система эфемерная (сбрасывается при редеплое).
# Чтобы статистика не терялась, подключите Volume (Settings -> Volumes),
# смонтируйте его, например, в /data, и задайте переменную окружения:
# DB_PATH=/data/reviews.db
DB_PATH = os.environ.get("DB_PATH", "reviews.db")

EMPLOYEES = [
    "Бакиров Габит",
    "Бакиров Шакен",
    "Махамбпет Нуржас",
    "Райф Арсен",
    "Рыстай Уласкан",
]

TIMEOUT_SECONDS = 80
SELECT_EMPLOYEE, SELECT_RATING, GET_COMMENT = range(3)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)


# ─── База данных ──────────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            username TEXT,
            voice INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_review(employee, rating, username, comment="", voice=False):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO reviews (employee, rating, comment, username, voice, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (employee, rating, comment, username, int(voice), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def is_manager(update: Update) -> bool:
    return update.effective_user.id == MANAGER_ID


def employee_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👤 {emp}", callback_data=f"emp_{i}")]
        for i, emp in enumerate(EMPLOYEES)
    ])


def rating_keyboard():
    stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    rows = [
        [InlineKeyboardButton(stars[i], callback_data=f"rate_{i+1}")]
        for i in range(5)
    ]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])
    return InlineKeyboardMarkup(rows)


def cancel_timer(context):
    task = context.user_data.pop("_timer", None)
    if task and not task.done():
        task.cancel()


def start_timer(update, context, msg_id):
    cancel_timer(context)
    context.user_data["_timer"] = asyncio.create_task(
        _timeout_reset(update, context, msg_id)
    )


async def _timeout_reset(update, context, msg_id):
    await asyncio.sleep(TIMEOUT_SECONDS)
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
    except Exception:
        pass
    context.user_data.clear()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"⏱️ Время вышло.\n\n📋 Книга отзывов — {BRANCH}\n\nВыберите сотрудника:",
        parse_mode="Markdown",
        reply_markup=employee_keyboard()
    )


async def _auto_restart(update, context, old_msg_id):
    await asyncio.sleep(80)
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old_msg_id)
    except Exception:
        pass
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔄 Новый отзыв?\n\n📋 Книга отзывов — {BRANCH}\n\nВыберите сотрудника:",
        parse_mode="Markdown",
        reply_markup=employee_keyboard()
    )


async def send_to_manager(context, employee, rating, username, comment=""):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    stars = "⭐" * rating
    comment_line = f"💬 {comment}\n" if comment else ""

    if rating <= 2:
        header = "📕 Негативный отзыв!"
    else:
        header = "📗 Положительный отзыв!"

    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"{header}\n\n"
            f"🏢 Филиал: {BRANCH}\n"
            f"👤 Сотрудник: {employee}\n"
            f"⭐ Оценка: {stars} ({rating}/5)\n"
            f"{comment_line}"
            f"🕐 {now}\n"
            f"👥 @{username}"
        ),
        parse_mode="Markdown"
    )


# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    context.user_data.clear()
    msg = await update.message.reply_text(
        f"📋 Книга отзывов — {BRANCH}\n\nВыберите сотрудника:",
        parse_mode="Markdown",
        reply_markup=employee_keyboard()
    )
    start_timer(update, context, msg.message_id)
    return SELECT_EMPLOYEE


# ─── Выбор сотрудника ─────────────────────────────────────────────────────────
async def select_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_timer(context)

    idx = int(query.data.replace("emp_", ""))
    employee = EMPLOYEES[idx]
    context.user_data["employee"] = employee

    await query.edit_message_text(
        f"👤 Сотрудник: {employee}\n\nПоставьте оценку от 1 до 5 звёзд:",
        parse_mode="Markdown",
        reply_markup=rating_keyboard()
    )
    start_timer(update, context, query.message.message_id)
    return SELECT_RATING


# ─── Выбор рейтинга ───────────────────────────────────────────────────────────
async def select_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_timer(context)

    if query.data == "back":
        await query.edit_message_text(
            f"📋 Книга отзывов — {BRANCH}\n\nВыберите сотрудника:",
            parse_mode="Markdown",
            reply_markup=employee_keyboard()
        )
        start_timer(update, context, query.message.message_id)
        return SELECT_EMPLOYEE

    rating = int(query.data.replace("rate_", ""))
    context.user_data["rating"] = rating
    employee = context.user_data.get("employee", "Неизвестно")
    username = update.effective_user.username or "аноним"
    stars = "⭐" * rating

    # 3, 4, 5 звёзд — сразу отправляем
    if rating >= 3:
        await send_to_manager(context, employee, rating, username)
        save_review(employee, rating, username)

        msg = await query.edit_message_text(
            f"✅ Спасибо за оценку!\n\n"
            f"👤 {employee}\n"
            f"{stars} ({rating}/5)\n\n"
            f"Меню появится через 80 секунд...",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        asyncio.create_task(_auto_restart(update, context, msg.message_id))
        return ConversationHandler.END

    # 1 или 2 звезды — просим причину
    await query.edit_message_text(
        f"👤 {employee}\n"
        f"{stars} ({rating}/5)\n\n"
        f"😔 Жаль, что вам не понравилось.\n"
        f"Пожалуйста, опишите причину или отправьте 🎤 голосовое сообщение:",
        parse_mode="Markdown"
    )
    start_timer(update, context, query.message.message_id)
    return GET_COMMENT


# ─── Текстовый комментарий ────────────────────────────────────────────────────
async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    employee = context.user_data.get("employee", "Неизвестно")
    rating   = context.user_data.get("rating", 1)
    username = update.effective_user.username or "аноним"
    comment  = update.message.text or ""
    stars    = "⭐" * rating

    await send_to_manager(context, employee, rating, username, comment=comment)
    save_review(employee, rating, username, comment=comment)

    msg = await update.message.reply_text(
        f"✅ Спасибо за отзыв!\n\n"
        f"👤 {employee}\n"
        f"{stars} ({rating}/5)\n\n"
        f"Меню появится через 80 секунд...",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    asyncio.create_task(_auto_restart(update, context, msg.message_id))
    return ConversationHandler.END


# ─── Голосовой комментарий ────────────────────────────────────────────────────
async def get_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    employee = context.user_data.get("employee", "Неизвестно")
    rating   = context.user_data.get("rating", 1)
    username = update.effective_user.username or "аноним"
    now      = datetime.now().strftime("%d.%m.%Y %H:%M")
    stars    = "⭐" * rating

    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"📕 Негативный отзыв (голосовой)!\n\n"
            f"🏢 Филиал: {BRANCH}\n"
            f"👤 Сотрудник: {employee}\n"
            f"⭐ Оценка: {stars} ({rating}/5)\n"
            f"🕐 {now}\n"
            f"👥 @{username}"
        ),
        parse_mode="Markdown"
    )
    await context.bot.forward_message(
        chat_id=MANAGER_ID,
        from_chat_id=update.effective_chat.id,
        message_id=update.message.message_id
    )
    save_review(employee, rating, username, comment="(голосовое сообщение)", voice=True)

    msg = await update.message.reply_text(
        f"✅ Спасибо за отзыв!\n\n"
        f"👤 {employee}\n"
        f"{stars} ({rating}/5)\n\n"
        f"Меню появится через 80 секунд...",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    asyncio.create_task(_auto_restart(update, context, msg.message_id))
    return ConversationHandler.END


# ─── Глобальный обработчик (после авто-рестарта) ─────────────────────────────
async def global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("emp_"):
        idx = int(query.data.replace("emp_", ""))
        employee = EMPLOYEES[idx]
        context.user_data.clear()
        context.user_data["employee"] = employee

        await query.edit_message_text(
            f"👤 Сотрудник: {employee}\n\nПоставьте оценку от 1 до 5 звёзд:",
            parse_mode="Markdown",
            reply_markup=rating_keyboard()
        )
        start_timer(update, context, query.message.message_id)


# ─── Статистика ───────────────────────────────────────────────────────────────
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update):
        await update.message.reply_text("⛔ Команда доступна только менеджеру.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), AVG(rating) FROM reviews")
    total, avg_all = cur.fetchone()

    if not total:
        await update.message.reply_text("📊 Пока нет ни одного отзыва.")
        conn.close()
        return

    cur.execute("""
        SELECT employee, COUNT(*) as cnt, AVG(rating) as avg_r
        FROM reviews
        GROUP BY employee
        ORDER BY cnt DESC
    """)
    rows = cur.fetchall()

    lines = [f"📊 *Статистика отзывов — {BRANCH}*", f"Всего отзывов: {total}", f"Средняя оценка: {avg_all:.2f} ⭐", ""]

    for employee, cnt, avg_r in rows:
        cur.execute("""
            SELECT rating, COUNT(*) FROM reviews
            WHERE employee = ?
            GROUP BY rating
        """, (employee,))
        dist = dict(cur.fetchall())
        dist_str = "  ".join(f"{r}⭐:{dist.get(r, 0)}" for r in range(1, 6))
        lines.append(f"👤 *{employee}*")
        lines.append(f"   Всего: {cnt}, средняя: {avg_r:.2f} ⭐")
        lines.append(f"   {dist_str}")
        lines.append("")

    conn.close()
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── Экспорт в CSV ────────────────────────────────────────────────────────────
async def export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update):
        await update.message.reply_text("⛔ Команда доступна только менеджеру.")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT employee, rating, comment, username, voice, created_at FROM reviews ORDER BY created_at")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text("📊 Пока нет ни одного отзыва.")
        return

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Сотрудник", "Оценка", "Комментарий", "Username", "Голосовое", "Дата"])
    for employee, rating, comment, username, voice, created_at in rows:
        writer.writerow([employee, rating, comment or "", username or "", "да" if voice else "нет", created_at])

    data = io.BytesIO(buf.getvalue().encode("utf-8-sig"))  # BOM для корректного открытия в Excel
    data.name = f"reviews_{BRANCH}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    await update.message.reply_document(document=InputFile(data, filename=data.name))


# ─── Отмена ───────────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    context.user_data.clear()
    await update.message.reply_text("Отменено. /start — начать заново.")
    return ConversationHandler.END


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(select_employee, pattern="^emp_"),
        ],
        states={
            SELECT_EMPLOYEE: [
                CallbackQueryHandler(select_employee, pattern="^emp_"),
            ],
            SELECT_RATING: [
                CallbackQueryHandler(select_rating),
            ],
            GET_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_comment),
                MessageHandler(filters.VOICE, get_voice),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("start", start),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("export", export))
    app.add_handler(CallbackQueryHandler(global_callback_handler))

    print(f"✅ Книга отзывов {BRANCH} запущена!")
    app.run_polling()


if __name__ == "__main__":
    main()


