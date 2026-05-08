import logging
from dotenv import load_dotenv
from bot.app import build_application
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

    try:
        app = build_application()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    print("Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()
