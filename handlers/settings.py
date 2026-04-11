import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)

CB_SETTINGS = "settings"
CB_BACK_MAIN = "main_menu"


def create_settings_handlers(auth_check):

    @auth_check
    async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        cfg = context.bot_data.get("config")
        text = (
            "⚙️ <b>Настройки</b>\n\n"
            f"📁 Директория проектов: <code>{cfg.projects_dir or 'не задана'}</code>\n"
            f"⏱️ Интервал поллинга: {cfg.poll_interval_sec} сек\n"
            f"📊 Пороги: {', '.join(str(t) + '%' for t in cfg.thresholds)}\n"
            f"🖥️ IDE: {cfg.ide} (таймаут триггера: {cfg.ide_trigger_timeout} сек)\n"
            f"📝 Уровень логов: {cfg.log_level}\n\n"
            "<i>Для изменения отредактируй config.json и перезапусти бота</i>"
        )
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )

    return [
        CallbackQueryHandler(show_settings, pattern=f"^{CB_SETTINGS}$"),
    ]
