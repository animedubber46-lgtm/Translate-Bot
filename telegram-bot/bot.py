"""
Hinglish SRT Subtitle Translator Bot
Main entry point — initializes the Telegram bot and registers all handlers.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from handlers import (
    start_handler,
    help_handler,
    mode_handler,
    sample_handler,
    document_handler,
    mystatus_handler,
    grant_handler,
    listpremium_handler,
    premium_callback,
)
from premium import OWNER_ID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Commands shown to every user
PUBLIC_COMMANDS = [
    BotCommand("start",     "Bot start karo / Welcome"),
    BotCommand("help",      "How to use this bot"),
    BotCommand("mode",      "Translation mode dekho ya change karo"),
    BotCommand("sample",    "Example Hindi dub translation dekho"),
    BotCommand("mystatus",  "Apna premium status check karo"),
]

# Extra commands shown only to the owner
OWNER_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand("p1",          "1 month premium do — /p1 <user_id>"),
    BotCommand("p2",          "2 month premium do — /p2 <user_id>"),
    BotCommand("listpremium", "Saare active premium users dekho"),
]


async def post_init(application: Application) -> None:
    """Set bot command menu after startup."""
    # All private chats see public commands
    await application.bot.set_my_commands(
        PUBLIC_COMMANDS,
        scope=BotCommandScopeAllPrivateChats(),
    )
    # Owner sees extended command list
    await application.bot.set_my_commands(
        OWNER_COMMANDS,
        scope=BotCommandScopeChat(chat_id=OWNER_ID),
    )
    logger.info("Bot command menu registered.")


def main() -> None:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable is not set.")

    app = (
        Application.builder()
        .token(token)
        .concurrent_updates(True)   # multiple users handled in parallel
        .post_init(post_init)       # register command menu on startup
        .build()
    )

    app.add_handler(CommandHandler("start",        start_handler))
    app.add_handler(CommandHandler("help",         help_handler))
    app.add_handler(CommandHandler("mode",         mode_handler))
    app.add_handler(CommandHandler("sample",       sample_handler))
    app.add_handler(CommandHandler("mystatus",     mystatus_handler))
    app.add_handler(CommandHandler("p1",           grant_handler))
    app.add_handler(CommandHandler("p2",           grant_handler))
    app.add_handler(CommandHandler("listpremium",  listpremium_handler))
    app.add_handler(CallbackQueryHandler(premium_callback, pattern="^show_premium$"))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))

    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
