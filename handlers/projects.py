import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
)

from core.project_registry import ProjectRegistry

logger = logging.getLogger(__name__)

# Callback data prefixes
CB_PROJECTS = "projects"
CB_PROJECT_ADD = "proj_add"
CB_PROJECT_SCAN = "proj_scan:"
CB_PROJECT_REMOVE = "proj_rm"
CB_PROJECT_RM_CONFIRM = "proj_rm_confirm:"
CB_BACK_MAIN = "main_menu"


def create_project_handlers(registry: ProjectRegistry, auth_check):
    """Create and return handlers for project management."""

    @auth_check
    async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()

        projects = registry.list()
        if not projects:
            text = "📂 Нет зарегистрированных проектов"
        else:
            lines = ["📂 <b>Проекты:</b>\n"]
            for p in projects:
                lines.append(f"  • <b>{p['name']}</b>\n    <code>{p['path']}</code>")
            text = "\n".join(lines)

        keyboard = [
            [InlineKeyboardButton("➕ Добавить", callback_data=CB_PROJECT_ADD)],
        ]
        if projects:
            keyboard.append(
                [InlineKeyboardButton("❌ Удалить", callback_data=CB_PROJECT_REMOVE)]
            )
        keyboard.append(
            [InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]
        )

        if query:
            await query.edit_message_text(
                text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
            )

    @auth_check
    async def scan_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        projects_dir = context.bot_data.get("config").projects_dir
        if not projects_dir:
            await query.edit_message_text("⚙️ projects_dir не задан в config.json")
            return

        found = registry.scan(projects_dir)
        registered_names = {p["name"] for p in registry.list()}
        new_repos = [r for r in found if r["name"] not in registered_names]

        if not new_repos:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_PROJECTS)]]
            await query.edit_message_text(
                "Новых git-репозиториев не найдено",
                reply_markup=InlineKeyboardMarkup(keyboard),
            )
            return

        keyboard = [
            [InlineKeyboardButton(r["name"], callback_data=f"{CB_PROJECT_SCAN}{r['name']}|{r['path']}")]
            for r in new_repos
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=CB_PROJECTS)])

        await query.edit_message_text(
            f"Найдено {len(new_repos)} репозиториев:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    @auth_check
    async def add_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data.replace(CB_PROJECT_SCAN, "")
        name, path = data.split("|", 1)

        try:
            registry.add(name, path)
            text = f"✅ Проект <b>{name}</b> зарегистрирован\n<code>{path}</code>"
        except ValueError as e:
            text = f"⚠️ {e}"

        keyboard = [[InlineKeyboardButton("🔙 К проектам", callback_data=CB_PROJECTS)]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    @auth_check
    async def show_remove_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        projects = registry.list()
        keyboard = [
            [InlineKeyboardButton(f"❌ {p['name']}", callback_data=f"{CB_PROJECT_RM_CONFIRM}{p['name']}")]
            for p in projects
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=CB_PROJECTS)])

        await query.edit_message_text(
            "Выбери проект для удаления:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    @auth_check
    async def remove_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        name = query.data.replace(CB_PROJECT_RM_CONFIRM, "")

        try:
            registry.remove(name)
            text = f"✅ Проект <b>{name}</b> удалён"
        except ValueError as e:
            text = f"⚠️ {e}"

        keyboard = [[InlineKeyboardButton("🔙 К проектам", callback_data=CB_PROJECTS)]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    return [
        CallbackQueryHandler(show_projects, pattern=f"^{CB_PROJECTS}$"),
        CallbackQueryHandler(scan_projects, pattern=f"^{CB_PROJECT_ADD}$"),
        CallbackQueryHandler(add_project, pattern=f"^{CB_PROJECT_SCAN}"),
        CallbackQueryHandler(show_remove_list, pattern=f"^{CB_PROJECT_REMOVE}$"),
        CallbackQueryHandler(remove_project, pattern=f"^{CB_PROJECT_RM_CONFIRM}"),
    ]
