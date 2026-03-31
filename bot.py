import asyncio
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from calendar_client import get_events, CalendarError
from llm import answer_question, summarize_events, LLMError

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Australia/Brisbane"))
ALLOWED_USERS: set[int] = set()


class _AllowedUsersFilter(filters.MessageFilter):
    def filter(self, message) -> bool:
        return message.from_user is not None and message.from_user.id in ALLOWED_USERS


allowed_filter = _AllowedUsersFilter()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! I'm your calendar assistant. Ask me anything about your schedule, "
        "or use /today or /week for quick summaries."
    )


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    try:
        now = datetime.now(TIMEZONE)
        today_str = now.strftime("%Y-%m-%d")
        events = await asyncio.to_thread(get_events, today_str, today_str)
        reply = await summarize_events(events, "today's events")
        await update.message.reply_text(reply)
    except (CalendarError, LLMError) as e:
        logger.error("Error in /today: %s", e)
        await update.message.reply_text(
            "Sorry, I had trouble checking your calendar. Please try again."
        )


async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    try:
        now = datetime.now(TIMEZONE)
        monday = now - timedelta(days=now.weekday())
        sunday = monday + timedelta(days=6)
        events = await asyncio.to_thread(
            get_events, monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")
        )
        reply = await summarize_events(events, "this week's events")
        await update.message.reply_text(reply)
    except (CalendarError, LLMError) as e:
        logger.error("Error in /week: %s", e)
        await update.message.reply_text(
            "Sorry, I had trouble checking your calendar. Please try again."
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.chat.send_action("typing")
    try:
        reply = await answer_question(update.message.text)
        await update.message.reply_text(reply)
    except (CalendarError, LLMError) as e:
        logger.error("Error handling message: %s", e)
        await update.message.reply_text(
            "Sorry, I had trouble answering that. Please try again."
        )


def main() -> None:
    global ALLOWED_USERS

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    allowed = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    ALLOWED_USERS = {int(uid.strip()) for uid in allowed.split(",") if uid.strip()}

    if not ALLOWED_USERS:
        logger.warning("No allowed users configured — bot will reject all messages")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command, filters=allowed_filter))
    app.add_handler(CommandHandler("today", today_command, filters=allowed_filter))
    app.add_handler(CommandHandler("week", week_command, filters=allowed_filter))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & allowed_filter, handle_message
        )
    )

    logger.info("Bot starting in polling mode...")
    app.run_polling()


if __name__ == "__main__":
    main()
