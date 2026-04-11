import logging
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from analytics.charts import UsageCharts
from core.limit_tracker import LimitTracker

logger = logging.getLogger(__name__)

CB_LIMITS = "limits"
CB_BACK_MAIN = "main_menu"
CB_CHART_DAY = "chart_day"
CB_CHART_WEEK = "chart_week"
CB_CHART_HEATMAP = "chart_heatmap"


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

        keyboard = [
            [
                InlineKeyboardButton("📈 День", callback_data=CB_CHART_DAY),
                InlineKeyboardButton("📈 Неделя", callback_data=CB_CHART_WEEK),
                InlineKeyboardButton("🗓 Heatmap", callback_data=CB_CHART_HEATMAP),
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data=CB_BACK_MAIN)],
        ]
        markup = InlineKeyboardMarkup(keyboard)

        if update.callback_query:
            await update.callback_query.answer()
            # If coming from a photo message (chart), delete it and send new text
            if update.callback_query.message.photo:
                await update.callback_query.message.delete()
                await update.callback_query.message.chat.send_message(
                    text, reply_markup=markup, parse_mode="HTML",
                )
            else:
                await update.callback_query.edit_message_text(
                    text, reply_markup=markup, parse_mode="HTML",
                )
        else:
            await update.message.reply_text(
                text, reply_markup=markup, parse_mode="HTML",
            )

    _chart_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📈 День", callback_data=CB_CHART_DAY),
            InlineKeyboardButton("📈 Неделя", callback_data=CB_CHART_WEEK),
            InlineKeyboardButton("🗓 Heatmap", callback_data=CB_CHART_HEATMAP),
        ],
        [InlineKeyboardButton("📊 К лимитам", callback_data=CB_LIMITS)],
    ])

    async def _send_chart(update: Update, path: str | None, caption: str):
        await update.callback_query.answer()
        if not path:
            await update.callback_query.edit_message_text(
                f"📊 {caption}: нет данных",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📊 К лимитам", callback_data=CB_LIMITS)]]
                ),
            )
            return
        # Delete the text message, send photo instead
        await update.callback_query.message.delete()
        with open(path, "rb") as f:
            await update.callback_query.message.chat.send_photo(
                photo=f, caption=caption, reply_markup=_chart_kb,
            )

    @auth_check
    async def chart_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await _send_chart(update, charts.generate_day(today), f"📈 Usage — {today}")

    @auth_check
    async def chart_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await _send_chart(update, charts.generate_week(today), f"📈 Usage — week ending {today}")

    @auth_check
    async def chart_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
        year_month = datetime.now(timezone.utc).strftime("%Y-%m")
        await _send_chart(update, charts.generate_heatmap(year_month), f"🗓 Heatmap — {year_month}")

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
        CallbackQueryHandler(chart_day, pattern=f"^{CB_CHART_DAY}$"),
        CallbackQueryHandler(chart_week, pattern=f"^{CB_CHART_WEEK}$"),
        CallbackQueryHandler(chart_heatmap, pattern=f"^{CB_CHART_HEATMAP}$"),
        CommandHandler("usage", show_limits),
        CommandHandler("usage_day", cmd_usage_day),
        CommandHandler("usage_week", cmd_usage_week),
        CommandHandler("usage_heatmap", cmd_usage_heatmap),
    ]
