import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables before importing modules that read them at import time.
load_dotenv()

from bot.admin_panel import configure_admin_logging, start_admin_panel
from bot.app import build_application
from bot.db import init_db

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logging.getLogger("googleapiclient.discovery_cache").setLevel(logging.WARNING)
configure_admin_logging()


def _configure_file_logging():
    log_file = os.getenv("LOG_FILE", "data/bot.log")
    log_path = Path(log_file)
    if log_path.parent != Path("."):
        log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(handler)


def main():
    # Initialize Database
    init_db()
    _configure_file_logging()
    start_admin_panel()

    try:
        app = build_application()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
