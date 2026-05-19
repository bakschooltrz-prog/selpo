
import os, logging, asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN  = os.environ.get("BOT_TOKEN", "8394248182:AAHcjWI_sGGUvXUIdo1iHHqYYvNc3I2l_KU")
MANAGER_ID = int(os.environ.get("MANAGER_ID", "60365607"))
BRANCH     = "Сельпо"

EMPLOYEES = [
    "Бакиров Габит",
    "Бакиров Шакен",
    "Махамбет Нуржас",
    "Рыстай Уласкан",
    "Райф Арсен",
]

# Жалобы: первые 3 — быстрые (без комментария), последняя — с комментарием
COMPLAINTS = [
    "❌ Некачественная работа",
    "⏳ Долгое обслуживание",
    "😠 Грубое общение",
    "👀 Невнимательность мастера",
    "✏️ Другое",
]
QUICK_COMPLAINTS = COMPLAINTS[:3]  # без комментария
OTHER_COMPLAINT  = COMPLAINTS[3]   # требует комментария

TIMEOUT_SECONDS = 80
SELECT_EMPLOYEE, SELECT_COMPLAINT, GET_COMMENT = range(3)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)


def employee_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👤 {emp}", callback_data=f"emp_{i}")]
        for i, emp in enumerate(EMPLOYEES)
    ])


def complaint_keyboard():
    rows = [
        [InlineKeyboardButton(COMPLAINTS[i], callback_data=f"comp_{i}")]
        for i in range(len(COMPLAINTS))
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
        text=f"⏱ Время вышло.\n\n📋 *Книга жалоб — {BRANCH}*\n\nВыберите сотрудника:",
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
        text=f"🔄 *Новая жалоба?*\n\n📋 *Книга жалоб — {BRANCH}*\n\nВыберите сотрудника:",
        parse_mode="Markdown",
        reply_markup=employee_keyboard()
    )


async def send_complaint_to_manager(context, employee, complaint_text, username, extra_comment=""):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    comment_line = f"💬 {extra_comment}\n" if extra_comment else ""
    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"📕 *Новая жалоба!*\n\n"
            f"🏢 Филиал: *{BRANCH}*\n"
            f"👤 Сотрудник: *{employee}*\n"
            f"⚠️ Причина: {complaint_text}\n"
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
        f"📋 *Книга жалоб — {BRANCH}*\n\nВыберите сотрудника:",
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
        f"👤 Сотрудник: *{employee}*\n\nВыберите причину жалобы:",
        parse_mode="Markdown",
        reply_markup=complaint_keyboard()
    )
    start_timer(update, context, query.message.message_id)
    return SELECT_COMPLAINT


# ─── Выбор жалобы ─────────────────────────────────────────────────────────────
async def select_complaint(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cancel_timer(context)

    # Кнопка "Назад"
    if query.data == "back":
        await query.edit_message_text(
            f"📋 *Книга жалоб — {BRANCH}*\n\nВыберите сотрудника:",
            parse_mode="Markdown",
            reply_markup=employee_keyboard()
        )
        start_timer(update, context, query.message.message_id)
        return SELECT_EMPLOYEE

    comp_idx = int(query.data.replace("comp_", ""))
    complaint_text = COMPLAINTS[comp_idx]
    context.user_data["complaint"] = complaint_text
    employee = context.user_data.get("employee", "Неизвестно")
    username = update.effective_user.username or "аноним"

    # Быстрые жалобы — сразу отправляем и перезапускаем
    if complaint_text in QUICK_COMPLAINTS:
        await send_complaint_to_manager(context, employee, complaint_text, username)

        msg = await query.edit_message_text(
            f"✅ *Спасибо за жалобу!*\n\n"
            f"👤 {employee}\n"
            f"⚠️ {complaint_text}\n\n"
            f"_Меню появится через 80 секунд..._",
            parse_mode="Markdown"
        )
        context.user_data.clear()
        asyncio.create_task(_auto_restart(update, context, msg.message_id))
        return ConversationHandler.END

    # "Другое" — просим комментарий
    await query.edit_message_text(
        f"👤 {employee}\n"
        f"⚠️ {complaint_text}\n\n"
        f"Опишите ситуацию или отправьте 🎤 голосовое сообщение:",
        parse_mode="Markdown"
    )
    start_timer(update, context, query.message.message_id)
    return GET_COMMENT


# ─── Текстовый комментарий ────────────────────────────────────────────────────
async def get_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    employee       = context.user_data.get("employee", "Неизвестно")
    complaint_text = context.user_data.get("complaint", OTHER_COMPLAINT)
    username       = update.effective_user.username or "аноним"
    comment        = update.message.text or ""

    await send_complaint_to_manager(context, employee, complaint_text, username, extra_comment=comment)

    msg = await update.message.reply_text(
        f"✅ *Спасибо за жалобу!*\n\n"
        f"👤 {employee}\n"
        f"⚠️ {complaint_text}\n\n"
        f"_Меню появится через 80 секунд..._",
        parse_mode="Markdown"
    )
    context.user_data.clear()
    asyncio.create_task(_auto_restart(update, context, msg.message_id))
    return ConversationHandler.END


# ─── Голосовой комментарий ────────────────────────────────────────────────────
async def get_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cancel_timer(context)
    employee       = context.user_data.get("employee", "Неизвестно")
    complaint_text = context.user_data.get("complaint", OTHER_COMPLAINT)
    username       = update.effective_user.username or "аноним"
    now            = datetime.now().strftime("%d.%m.%Y %H:%M")

    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"📕 *Новая жалоба (голосовая)!*\n\n"
            f"🏢 Филиал: *{BRANCH}*\n"
            f"👤 Сотрудник: *{employee}*\n"
            f"⚠️ Причина: {complaint_text}\n"
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
        f"✅ *Спасибо за жалобу!*\n\n"
        f"👤 {employee}\n"
        f"⚠️ {complaint_text}\n\n"
        f"_Меню появится через 80 секунд..._",
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
            f"👤 Сотрудник: *{employee}*\n\nВыберите причину жалобы:",
            parse_mode="Markdown",
            reply_markup=complaint_keyboard()
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
            SELECT_COMPLAINT: [
                CallbackQueryHandler(select_complaint),
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

    print(f"✅ Книга жалоб {BRANCH} запущена!")
    app.run_polling()


if __name__ == "__main__":
    main()
