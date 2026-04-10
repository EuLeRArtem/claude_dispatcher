import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from analytics.charts import UsageCharts
from core.limit_tracker import LimitTracker

logger = logging.getLogger(__name__)

CB_LIMITS = "limits"
CB_BACK_MAIN = "main_menu"


def _format_usage_text(limit_tracker: LimitTracker) -> str | None:
    usage = limit_tracker.latest
    if not usage:
        return None

    five_pct = round(usage.five_hour_util * 100, 1)
    seven_pct = round(usage.seven_day_util * 100, 1)
    sonnet_pct = round(usage.seven_day_sonnet_util * 100, 1)

    reset_5h = ""
    if usage.five_hour_resets_at:
        try:
            dt = datetime.fromisoformat(usage.five_hour_resets_at)
            mins = max(0, int((dt - datetime.now(timezone.utc)).total_seconds() / 60))
            reset_5h = f" (reset через {mins} мин)"
        except ValueError:
            pass

    return (
        f"📊 <b>Использование лимитов</b>\n\n"
        f"⏱️ 5h: <b>{five_pct}%</b>{reset_5h}\n"
        f"📅 7d: <b>{seven_pct}%</b>\n"
        f"🤖 7d sonnet: <b>{sonnet_pct}%</b>"
    )


def create_analytics_handlers(
    limit_tracker: LimitTracker,
    charts: UsageCharts,
    auth_check,
):

    @auth_check
    async def show_limits(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle both /usage command and inline button press."""
        text = _format_usage_text(limit_tracker)
        if not text:
            text = "📊 Данные ещё не загружены, подожди немного"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)]]

        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
            )
        else:
            await update.message.reply_text(text, parse_mode="HTML")

    @auth_check
    async def cmd_usage_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = charts.generate_day(today)
        if not path:
            await update.message.reply_text("📊 Нет данных за сегодня")
            return
        with open(path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=f"📊 Usage — {today}")

    @auth_check
    async def cmd_usage_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = charts.generate_week(today)
        if not path:
            await update.message.reply_text("📊 Нет данных за неделю")
            return
        with open(path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=f"📊 Usage — week ending {today}")

    @auth_check
    async def cmd_usage_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
        year_month = datetime.now(timezone.utc).strftime("%Y-%m")
        path = charts.generate_heatmap(year_month)
        if not path:
            await update.message.reply_text("📊 Нет данных за этот месяц")
            return
        with open(path, "rb") as f:
            await update.message.reply_photo(photo=f, caption=f"📊 Heatmap — {year_month}")

    return [
        CallbackQueryHandler(show_limits, pattern=f"^{CB_LIMITS}$"),
        CommandHandler("usage", show_limits),
        CommandHandler("usage_day", cmd_usage_day),
        CommandHandler("usage_week", cmd_usage_week),
        CommandHandler("usage_heatmap", cmd_usage_heatmap),
    ]
