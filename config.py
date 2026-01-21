import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен в .env файле!")

# Ollama
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'tinyllama')
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://localhost:11434')

# Bot settings
MAX_CONTEXT_LENGTH = int(os.getenv('MAX_CONTEXT_LENGTH', '2048'))
MAX_RESPONSE_TOKENS = int(os.getenv('MAX_RESPONSE_TOKENS', '256'))
TEMPERATURE = float(os.getenv('TEMPERATURE', '0.7'))

# Logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Reminders
REMINDER_INTERVAL = int(os.getenv('REMINDER_INTERVAL', '300'))  # 5 minutes in seconds
DATABASE_PATH = os.getenv('DATABASE_PATH', 'reminders.db')