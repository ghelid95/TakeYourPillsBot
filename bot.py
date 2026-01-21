import logging
import ollama
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
from config import (
    TELEGRAM_TOKEN,
    OLLAMA_MODEL,
    OLLAMA_HOST,
    MAX_CONTEXT_LENGTH,
    MAX_RESPONSE_TOKENS,
    TEMPERATURE,
    LOG_LEVEL
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Хранилище разговоров (в продакшене лучше использовать БД)
user_conversations = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    user_conversations[user_id] = []

    welcome_message = (
        '👋 Привет! Я бот с локальной LLM.\n\n'
        f'🤖 Модель: {OLLAMA_MODEL}\n\n'
        'Команды:\n'
        '/start - начать заново\n'
        '/clear - очистить историю\n'
        '/help - помощь\n'
        '/info - информация о боте'
    )

    await update.message.reply_text(welcome_message)
    logger.info(f"Пользователь {user_id} запустил бота")


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /clear - очистка истории"""
    user_id = update.effective_user.id
    user_conversations[user_id] = []
    await update.message.reply_text('🗑 История диалога очищена!')
    logger.info(f"Пользователь {user_id} очистил историю")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    help_text = (
        'ℹ️ *Справка по использованию*\n\n'
        'Просто отправь мне текстовое сообщение, и я отвечу используя локальную LLM.\n\n'
        '*Доступные команды:*\n'
        '/start - начать диалог заново\n'
        '/clear - очистить историю разговора\n'
        '/info - информация о модели\n'
        '/help - эта справка'
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /info - информация о боте"""
    info_text = (
        f'🤖 *Информация о боте*\n\n'
        f'Модель: `{OLLAMA_MODEL}`\n'
        f'Хост: `{OLLAMA_HOST}`\n'
        f'Максимальный контекст: {MAX_CONTEXT_LENGTH} токенов\n'
        f'Максимальный ответ: {MAX_RESPONSE_TOKENS} токенов\n'
        f'Температура: {TEMPERATURE}'
    )
    await update.message.reply_text(info_text, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text

    logger.info(f"Получено сообщение от {user_id}: {user_message[:50]}...")

    # Инициализация истории для нового пользователя
    if user_id not in user_conversations:
        user_conversations[user_id] = []

    # Добавление сообщения пользователя
    user_conversations[user_id].append({
        'role': 'user',
        'content': user_message
    })

    # Ограничение истории (последние 10 сообщений = 5 пар)
    if len(user_conversations[user_id]) > 10:
        user_conversations[user_id] = user_conversations[user_id][-10:]

    # Индикатор печати
    await update.message.chat.send_action(action="typing")

    try:
        # Настройка клиента Ollama
        client = ollama.Client(host=OLLAMA_HOST)

        # Запрос к модели
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=user_conversations[user_id],
            options={
                'num_ctx': MAX_CONTEXT_LENGTH,
                'num_predict': MAX_RESPONSE_TOKENS,
                'temperature': TEMPERATURE,
            }
        )

        bot_response = response['message']['content']

        # Добавление ответа в историю
        user_conversations[user_id].append({
            'role': 'assistant',
            'content': bot_response
        })

        # Отправка ответа
        await update.message.reply_text(bot_response)
        logger.info(f"Ответ отправлен пользователю {user_id}")

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {e}", exc_info=True)
        await update.message.reply_text(
            '❌ Произошла ошибка при обработке запроса.\n'
            'Попробуйте позже или используйте /clear для очистки истории.'
        )


def main():
    """Запуск бота"""
    logger.info(f"Запуск бота с моделью {OLLAMA_MODEL} на {OLLAMA_HOST}")

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    logger.info("Бот успешно запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()