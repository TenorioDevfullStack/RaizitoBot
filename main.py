import logging
from dotenv import load_dotenv

# Load environment variables before importing modules that read them at import time.
load_dotenv()

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

def main():
    # Initialize Database
    init_db()

    try:
        app = build_application()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
