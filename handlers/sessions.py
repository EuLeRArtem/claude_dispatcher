import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.project_registry import ProjectRegistry
from core.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Conversation states
SELECT_PROJECT, SELECT_MODE, ENTER_PROMPT = range(3)

# Callback data
CB_SESSIONS = "sessions"
CB_NEW_SESSION = "new_session"
CB_SESSION_PROJECT = "sess_proj:"
CB_SESSION_MODE = "sess_mode:"
CB_SESSION_KILL = "sess_kill:"
CB_SESSION_BACK_PROJ = "sess_back_proj"
CB_BACK_MAIN = "main_menu"


def create_session_handlers(
    registry: ProjectRegistry,
    session_manager: SessionManager,
    auth_check,
    main_menu_callback=None,
):

    @auth_check
    async def show_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()

        sessions = session_manager.list_sessions()
        if not sessions:
            text = "📋 Нет активных сессий"
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]
        else:
            lines = ["📋 <b>Активные сессии:</b>\n"]
            keyboard = []
            for s in sessions:
                mode_label = "remote" if s.mode == "remote" else "обычная"
                lines.append(
                    f"  • <b>{s.project_name}</b> — {mode_label} — {s.duration_minutes()} мин"
                )
                keyboard.append([
                    InlineKeyboardButton(
                        f"❌ {s.project_name}", callback_data=f"{CB_SESSION_KILL}{s.session_id}"
                    )
                ])
            text = "\n".join(lines)
            keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)])

        msg_kwargs = dict(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        if query:
            await query.edit_message_text(**msg_kwargs)
        else:
            await update.message.reply_text(**msg_kwargs)

    @auth_check
    async def kill_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        session_id = query.data.replace(CB_SESSION_KILL, "")

        killed = await session_manager.kill_session(session_id)
        text = "✅ Сессия завершена" if killed else "⚠️ Сессия не найдена"

        keyboard = [[InlineKeyboardButton("🔙 К сессиям", callback_data=CB_SESSIONS)]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    # --- New session wizard ---

    @auth_check
    async def wizard_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        projects = registry.list()
        if not projects:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]
            await query.edit_message_text(
                "Нет зарегистрированных проектов. Сначала добавь проект.",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return ConversationHandler.END

        keyboard = [
            [InlineKeyboardButton(p["name"], callback_data=f"{CB_SESSION_PROJECT}{p['name']}")]
            for p in projects
        ]
        keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data=CB_BACK_MAIN)])

        await query.edit_message_text(
            "Какой проект?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_PROJECT

    @auth_check
    async def wizard_select_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        project_name = query.data.replace(CB_SESSION_PROJECT, "")
        context.user_data["session_project"] = project_name

        keyboard = [
            [InlineKeyboardButton("🖥️ Remote Control", callback_data=f"{CB_SESSION_MODE}remote")],
            [InlineKeyboardButton("▶️ Обычная", callback_data=f"{CB_SESSION_MODE}normal")],
            [InlineKeyboardButton("🔙 Назад", callback_data=CB_SESSION_BACK_PROJ)],
        ]
        await query.edit_message_text(
            f"Проект: <b>{project_name}</b>\nРежим?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
        )
        return SELECT_MODE

    @auth_check
    async def wizard_back_to_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        projects = registry.list()
        keyboard = [
            [InlineKeyboardButton(p["name"], callback_data=f"{CB_SESSION_PROJECT}{p['name']}")]
            for p in projects
        ]
        keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data=CB_BACK_MAIN)])
        await query.edit_message_text(
            "Какой проект?", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_PROJECT

    @auth_check
    async def wizard_select_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        mode = query.data.replace(CB_SESSION_MODE, "")
        context.user_data["session_mode"] = mode

        await query.edit_message_text(
            "Введи промпт (или /skip для пустой сессии):"
        )
        return ENTER_PROMPT

    @auth_check
    async def wizard_enter_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
        prompt = update.message.text
        if prompt == "/skip":
            prompt = ""

        project_name = context.user_data.get("session_project")
        mode = context.user_data.get("session_mode")

        project = registry.get(project_name)
        if not project:
            await update.message.reply_text("⚠️ Проект не найден")
            return ConversationHandler.END

        await update.message.reply_text(f"⏳ Запускаю {mode} сессию для <b>{project_name}</b>...", parse_mode="HTML")

        if mode == "remote":
            await session_manager.start_remote(project_name, project["path"], prompt)
        else:
            if not prompt:
                await update.message.reply_text("⚠️ Для обычного режима нужен промпт")
                return ConversationHandler.END
            await session_manager.start_normal(project_name, project["path"], prompt)

        # Show main menu after session creation
        if main_menu_callback:
            await main_menu_callback(update, context)

        return ConversationHandler.END

    @auth_check
    async def wizard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if main_menu_callback:
            await main_menu_callback(update, context)
        return ConversationHandler.END

    wizard_conversation = ConversationHandler(
        entry_points=[CallbackQueryHandler(wizard_start, pattern=f"^{CB_NEW_SESSION}$")],
        states={
            SELECT_PROJECT: [CallbackQueryHandler(wizard_select_project, pattern=f"^{CB_SESSION_PROJECT}")],
            SELECT_MODE: [
                CallbackQueryHandler(wizard_back_to_projects, pattern=f"^{CB_SESSION_BACK_PROJ}$"),
                CallbackQueryHandler(wizard_select_mode, pattern=f"^{CB_SESSION_MODE}"),
            ],
            ENTER_PROMPT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wizard_enter_prompt),
                MessageHandler(filters.Regex(r"^/skip$"), wizard_enter_prompt),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(wizard_cancel, pattern=f"^{CB_BACK_MAIN}$"),
            CallbackQueryHandler(wizard_cancel),  # catch-all: any unexpected callback cancels wizard
        ],
        per_message=False,
    )

    return [
        wizard_conversation,
        CallbackQueryHandler(show_sessions, pattern=f"^{CB_SESSIONS}$"),
        CallbackQueryHandler(kill_session, pattern=f"^{CB_SESSION_KILL}"),
    ]
