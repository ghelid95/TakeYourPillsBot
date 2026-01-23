import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен в .env файле!")

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Reminders
REMINDER_INTERVAL = int(os.getenv('REMINDER_INTERVAL', '300'))  # 5 minutes in seconds
DATABASE_PATH = os.getenv('DATABASE_PATH', 'reminders.db')