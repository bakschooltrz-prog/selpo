
import os, logging, asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")
MANAGER_ID = int(os.environ.get("MANAGER_ID", "1338569085"))
BRANCH     = "Сельпо"

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


# ─── Отмена ───────────────────────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    context.user_data.clear()
    await update.message.reply_text("Отменено. /start — начать заново.")
    return ConversationHandler.END


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
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
    app.add_handler(CallbackQueryHandler(global_callback_handler))

    print(f"✅ Книга отзывов {BRANCH} запущена!")
    app.run_polling()


if __name__ == "__main__":
    main()
