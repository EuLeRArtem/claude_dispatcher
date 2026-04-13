import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

logger = logging.getLogger(__name__)

CB_SETTINGS = "settings"
CB_BACK_MAIN = "main_menu"

_LABELS = {
    "sessions": "Сессии",
    "limits": "Лимиты",
    "permissions": "Разрешения",
}


def _toggle_icon(enabled: bool) -> str:
    return "🔔" if enabled else "🔕"


def _build_settings_text(cfg, states: dict[str, bool]) -> str:
    notif_lines = " | ".join(
        f"{_LABELS[k]}: {'вкл' if v else 'выкл'}" for k, v in states.items()
    )
    return (
        "⚙️ <b>Настройки</b>\n\n"
        f"📁 Директория проектов: <code>{cfg.projects_dir or 'не задана'}</code>\n"
        f"⏱️ Интервал поллинга: {cfg.poll_interval_sec} сек\n"
        f"📊 Пороги: {', '.join(str(t) + '%' for t in cfg.thresholds)}\n"
        f"🖥️ IDE: {cfg.ide} (таймаут триггера: {cfg.ide_trigger_timeout} сек)\n"
        f"📝 Уровень логов: {cfg.log_level}\n\n"
        f"🔔 <b>Уведомления:</b>\n  {notif_lines}\n\n"
        "<i>Конфигурация: config.json | Уведомления: кнопки ниже</i>"
    )


def _build_keyboard(states: dict[str, bool]) -> InlineKeyboardMarkup:
    toggles = [
        InlineKeyboardButton(
            f"{_toggle_icon(states[k])} {_LABELS[k]}",
            callback_data=f"toggle_{k}",
        )
        for k in _LABELS
    ]
    return InlineKeyboardMarkup([
        toggles,
        [InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)],
    ])


async def _render_settings(query, context):
    cfg = context.bot_data.get("config")
    ns = context.bot_data.get("notification_settings")
    states = ns.all_states()
    await query.edit_message_text(
        _build_settings_text(cfg, states),
        reply_markup=_build_keyboard(states),
        parse_mode="HTML",
    )


def create_settings_handlers(auth_check):

    @auth_check
    async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await _render_settings(query, context)

    @auth_check
    async def handle_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        category = query.data.replace("toggle_", "")
        ns = context.bot_data.get("notification_settings")
        new_state = ns.toggle(category)
        label = _LABELS.get(category, category)
        icon = _toggle_icon(new_state)
        await query.answer(f"{icon} {label}: {'вкл' if new_state else 'выкл'}")
        await _render_settings(query, context)

    return [
        CallbackQueryHandler(show_settings, pattern=f"^{CB_SETTINGS}$"),
        CallbackQueryHandler(handle_toggle, pattern=r"^toggle_(sessions|limits|permissions)$"),
    ]
