
import os, logging, asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "8710464933:AAFhS409kgG6LuRhK61Fx_aYVABy8L3DoO0")
MANAGER_ID = int(os.environ.get("MANAGER_ID", "1338569085"))
BRANCH     = "Аскарова"

EMPLOYEES = [
    "Узакбаев Айбол",
    "Узакбаев Байбол",
    "Рахметулла Нурсултан",
    "Копбаев Елжан",
]

TIMEOUT_SECONDS = 15
SELECT_EMPLOYEE, SELECT_RATING, GET_COMMENT = range(3)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)


def stars(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


def employee_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👤 {emp}", callback_data=f"emp_{i}")]
        for i, emp in enumerate(EMPLOYEES)
    ])


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
        text=f"⏱ Время вышло.\n\n👋 Филиал: *{BRANCH}*\n\nВыберите сотрудника:",
        parse_mode="Markdown",
        reply_markup=employee_keyboard()
    )


async def show_main_menu(update, context):
    """Показывает главное меню — используется везде"""
    cancel_timer(context)
    context.user_data.clear()
    if update.message:
        msg = await update.message.reply_text(
            f"👋 Филиал: *{BRANCH}*\n\nВыберите сотрудника:",
            parse_mode="Markdown",
            reply_markup=employee_keyboard()
        )
    else:
        msg = await update.callback_query.edit_message_text(
            f"👋 Филиал: *{BRANCH}*\n\nВыберите сотрудника:",
            parse_mode="Markdown",
            reply_markup=employee_keyboard()
        )
    start_timer(update, context, msg.message_id)
    return SELECT_EMPLOYEE


# ─── /start ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await show_main_menu(update, context)


# ─── Ловим нажатия на кнопки сотрудников ВНЕ диалога (после авто-рестарта) ───
async def global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("emp_"):
        # Запускаем диалог заново
        idx = int(query.data.replace("emp_", ""))
        employee = EMPLOYEES[idx]
        context.user_data.clear()
        context.user_data["employee"] = employee

        keyboard = [[InlineKeyboardButton(stars(i), callback_data=f"rate_{i}")] for i in range(1, 6)]
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])

        await query.edit_message_text(
            f"👤 Сотрудник: *{employee}*\n\nПоставьте оценку:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        start_timer(update, context, query.message.message_id)


# ─── Выбор сотрудника ─────────────────────────────────────────────────────────
async def select_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_timer(context)

    idx = int(query.data.replace("emp_", ""))
    employee = EMPLOYEES[idx]
    context.user_data["employee"] = employee

    keyboard = [[InlineKeyboardButton(stars(i), callback_data=f"rate_{i}")] for i in range(1, 6)]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back")])

    await query.edit_message_text(
        f"👤 Сотрудник: *{employee}*\n\nПоставьте оценку:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    start_timer(update, context, query.message.message_id)
    return SELECT_RATING


# ─── Выбор оценки ─────────────────────────────────────────────────────────────
async def select_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_timer(context)

    if query.data == "back":
        msg = await query.edit_message_text(
            f"👋 Филиал: *{BRANCH}*\n\nВыберите сотрудника:",
            parse_mode="Markdown",
            reply_markup=employee_keyboard()
        )
        start_timer(update, context, query.message.message_id)
        return SELECT_EMPLOYEE

    rating = int(query.data.replace("rate_", ""))
    context.user_data["rating"] = rating

    await query.edit_message_text(
        f"👤 {context.user_data['employee']}\n"
        f"⭐ Оценка: {stars(rating)} ({rating}/5)\n\n"
        f"Напишите комментарий или отправьте 🎤 голосовое.\n"
        f"_(Если не хотите — напишите «-»)_",
        parse_mode="Markdown"
    )
    start_timer(update, context, query.message.message_id)
    return GET_COMMENT


# ─── Текстовый комментарий ────────────────────────────────────────────────────
async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    employee = context.user_data.get("employee", "Неизвестно")
    rating   = context.user_data.get("rating", 0)
    username = update.effective_user.username or "аноним"
    now      = datetime.now().strftime("%d.%m.%Y %H:%M")
    comment  = update.message.text or ""

    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"📝 *Новый отзыв!*\n\n"
            f"🏢 Филиал: *{BRANCH}*\n"
            f"👤 Сотрудник: *{employee}*\n"
            f"⭐ Оценка: {stars(rating)} ({rating}/5)\n"
            f"💬 {comment}\n"
            f"🕐 {now}\n"
            f"👥 @{username}"
        ),
        parse_mode="Markdown"
    )

    msg = await update.message.reply_text(
        f"✅ Спасибо! *{employee}* получил {stars(rating)}\n\n"
        f"_Меню появится через 15 секунд..._",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    asyncio.create_task(_auto_restart(update, context, msg.message_id))
    return ConversationHandler.END


# ─── Голосовой комментарий ────────────────────────────────────────────────────
async def get_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    employee = context.user_data.get("employee", "Неизвестно")
    rating   = context.user_data.get("rating", 0)
    username = update.effective_user.username or "аноним"
    now      = datetime.now().strftime("%d.%m.%Y %H:%M")

    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"🎤 *Голосовой отзыв!*\n\n"
            f"🏢 Филиал: *{BRANCH}*\n"
            f"👤 *{employee}*\n"
            f"⭐ {stars(rating)} ({rating}/5)\n"
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
        f"✅ Голосовой отзыв принят!\n*{employee}* — {stars(rating)}\n\n"
        f"_Меню появится через 15 секунд..._",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    asyncio.create_task(_auto_restart(update, context, msg.message_id))
    return ConversationHandler.END


# ─── Авто-рестарт после отзыва ────────────────────────────────────────────────
async def _auto_restart(update, context, old_msg_id):
    await asyncio.sleep(15)
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old_msg_id)
    except Exception:
        pass
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🔄 *Новый отзыв?*\n\n👋 Филиал: *{BRANCH}*\n\nВыберите сотрудника:",
        parse_mode="Markdown",
        reply_markup=employee_keyboard()
    )


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
            SELECT_EMPLOYEE: [CallbackQueryHandler(select_employee, pattern="^emp_")],
            SELECT_RATING:   [CallbackQueryHandler(select_rating)],
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
    # Глобальный обработчик — ловит нажатия после авто-рестарта
    app.add_handler(CallbackQueryHandler(global_callback_handler))

    print(f"✅ Бот {BRANCH} запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
