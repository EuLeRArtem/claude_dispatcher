import logging
import sys
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, ContextTypes, CallbackQueryHandler, CommandHandler

from config import load_config, get_claude_credentials_path
from core.notifier import Notifier
from core.project_registry import ProjectRegistry
from core.session_manager import SessionManager
from core.limit_tracker import LimitTracker
from analytics.collector import UsageCollector
from analytics.charts import UsageCharts
from analytics.handlers import create_analytics_handlers
from handlers.auth import authorized
from handlers.projects import create_project_handlers
from handlers.sessions import create_session_handlers
from handlers.settings import create_settings_handlers

logger = logging.getLogger(__name__)

CB_BACK_MAIN = "main_menu"
CB_LIMITS = "limits"


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📂 Проекты", callback_data="projects")],
        [InlineKeyboardButton("🚀 Новая сессия", callback_data="new_session")],
        [InlineKeyboardButton("📋 Сессии", callback_data="sessions")],
        [InlineKeyboardButton("📊 Лимиты", callback_data=CB_LIMITS)],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
    ]
    text = "🏠 <b>Claude Dispatcher</b>"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )


def main():
    cfg = load_config()

    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, cfg.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("logs/bot.log", encoding="utf-8"),
        ],
    )

    app = Application.builder().token(cfg.telegram_bot_token).build()

    bot_instance: Bot = app.bot
    auth_check = authorized(cfg.telegram_user_id)

    # Core components
    notifier = Notifier(bot=bot_instance, chat_id=cfg.telegram_user_id)
    registry = ProjectRegistry(data_file="data/projects.json")
    session_manager = SessionManager(notifier=notifier, terminal_mode=cfg.terminal)

    # Analytics
    collector = UsageCollector(data_dir="data/usage")
    charts = UsageCharts(collector=collector, output_dir="data/charts")

    # Limit tracker with collector callback
    limit_tracker = LimitTracker(
        notifier=notifier,
        thresholds=cfg.thresholds,
        poll_interval_sec=cfg.poll_interval_sec,
        credentials_path=get_claude_credentials_path(),
        on_usage=collector.record,
    )

    # Store config in bot_data for handlers
    app.bot_data["config"] = cfg

    # Register handlers
    # Main menu
    start_handler = CommandHandler("start", auth_check(main_menu))
    back_handler = CallbackQueryHandler(auth_check(main_menu), pattern=f"^{CB_BACK_MAIN}$")

    app.add_handler(start_handler)
    app.add_handler(back_handler)

    # Session handlers (ConversationHandler must be added before simple CallbackQueryHandlers)
    for handler in create_session_handlers(registry, session_manager, auth_check):
        app.add_handler(handler)

    # Project handlers
    for handler in create_project_handlers(registry, auth_check):
        app.add_handler(handler)

    # Settings handlers
    for handler in create_settings_handlers(auth_check):
        app.add_handler(handler)

    # Analytics handlers
    for handler in create_analytics_handlers(limit_tracker, charts, auth_check):
        app.add_handler(handler)

    # Start limit tracker after app starts
    async def post_init(application: Application):
        limit_tracker.start()
        logger.info("Bot started. Limit tracker polling every %ds", cfg.poll_interval_sec)

    async def post_shutdown(application: Application):
        limit_tracker.stop()

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    logger.info("Starting Claude Dispatcher Bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
