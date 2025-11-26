import os
import logging
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from bot.handlers import (
    start_command, help_command, handle_message,
    add_task_command, list_tasks_command, complete_task_command,
    search_command, app_status_command,
    handle_photo, handle_audio,
    gmail_command, drive_command, calendar_command, docs_command,
)
from bot.db import init_db

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def main():
    # Initialize Database
    init_db()

    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Error: TELEGRAM_TOKEN not found in .env")
        return

    app = ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("task", add_task_command))
    app.add_handler(CommandHandler("list", list_tasks_command))
    app.add_handler(CommandHandler("done", complete_task_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("gmail", gmail_command))
    app.add_handler(CommandHandler("drive", drive_command))
    app.add_handler(CommandHandler("calendar", calendar_command))
    app.add_handler(CommandHandler("docs", docs_command))
    app.add_handler(CommandHandler("app_status", app_status_command))

    # Messages (Text) - Make sure this is last so it doesn't block commands if using filters.text
    # Note: CommandHandler handles commands, MessageHandler handles non-command text.
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
