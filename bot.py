import logging
import re
from datetime import datetime, date, timedelta
import ollama
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
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
    LOG_LEVEL,
    REMINDER_INTERVAL
)
from database import (
    init_db,
    get_or_create_user,
    set_user_timezone,
    get_user_timezone,
    add_reminder,
    get_user_reminders,
    get_all_active_reminders,
    remove_reminder,
    get_reminder_state,
    create_or_update_reminder_state,
    acknowledge_reminder,
    is_reminder_acknowledged,
    get_reminder_by_id
)
from meme_api import fetch_random_meme, get_fallback_message

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

    await get_or_create_user(user_id)

    welcome_message = (
        'Привет! Я бот-напоминалка о приёме таблеток.\n\n'
        f'Модель: {OLLAMA_MODEL}\n\n'
        'Команды:\n'
        '/start - начать заново\n'
        '/clear - очистить историю\n'
        '/help - помощь\n'
        '/info - информация о боте\n\n'
        'Напоминания:\n'
        '/add_reminder HH:MM - добавить напоминание\n'
        '/list_reminders - список напоминаний\n'
        '/remove_reminder ID - удалить напоминание\n'
        '/set_timezone Region/City - установить часовой пояс\n'
        '/my_timezone - показать текущий часовой пояс'
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
        '*Справка по использованию*\n\n'
        'Просто отправь мне текстовое сообщение, и я отвечу используя локальную LLM.\n\n'
        '*Основные команды:*\n'
        '/start - начать диалог заново\n'
        '/clear - очистить историю разговора\n'
        '/info - информация о модели\n'
        '/help - эта справка\n\n'
        '*Команды напоминаний:*\n'
        '/add\\_reminder HH:MM - добавить напоминание (пример: /add\\_reminder 09:00)\n'
        '/list\\_reminders - показать все напоминания\n'
        '/remove\\_reminder ID - удалить напоминание по ID\n'
        '/set\\_timezone Region/City - установить часовой пояс (пример: /set\\_timezone Europe/Moscow)\n'
        '/my\\_timezone - показать текущий часовой пояс'
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
            'Произошла ошибка при обработке запроса.\n'
            'Попробуйте позже или используйте /clear для очистки истории.'
        )


async def add_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /add_reminder - добавить напоминание"""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            'Укажите время в формате HH:MM\n'
            'Пример: /add_reminder 09:00'
        )
        return

    time_str = context.args[0]

    if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        await update.message.reply_text(
            'Неверный формат времени. Используйте HH:MM\n'
            'Пример: /add_reminder 09:00'
        )
        return

    if len(time_str) == 4:
        time_str = '0' + time_str

    reminder_id = await add_reminder(user_id, time_str)
    user_tz = await get_user_timezone(user_id)

    await update.message.reply_text(
        f'Напоминание добавлено!\n'
        f'ID: {reminder_id}\n'
        f'Время: {time_str} ({user_tz})'
    )
    logger.info(f"Пользователь {user_id} добавил напоминание на {time_str}")


async def list_reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /list_reminders - список напоминаний"""
    user_id = update.effective_user.id
    reminders = await get_user_reminders(user_id)
    user_tz = await get_user_timezone(user_id)

    if not reminders:
        await update.message.reply_text(
            'У вас нет активных напоминаний.\n'
            'Добавьте: /add_reminder HH:MM'
        )
        return

    text = f'*Ваши напоминания* (часовой пояс: {user_tz}):\n\n'
    for r in reminders:
        text += f'ID: {r["id"]} - {r["time"]}\n'

    await update.message.reply_text(text, parse_mode='Markdown')


async def remove_reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /remove_reminder - удалить напоминание"""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            'Укажите ID напоминания\n'
            'Пример: /remove_reminder 1\n'
            'Список напоминаний: /list_reminders'
        )
        return

    try:
        reminder_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text('ID должен быть числом')
        return

    success = await remove_reminder(user_id, reminder_id)

    if success:
        await update.message.reply_text(f'Напоминание {reminder_id} удалено')
        logger.info(f"Пользователь {user_id} удалил напоминание {reminder_id}")
    else:
        await update.message.reply_text('Напоминание не найдено')


async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /set_timezone - установить часовой пояс"""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            'Укажите часовой пояс в формате Region/City\n'
            'Примеры:\n'
            '/set_timezone Europe/Moscow\n'
            '/set_timezone America/New_York\n'
            '/set_timezone Asia/Tokyo'
        )
        return

    timezone_str = context.args[0]

    try:
        pytz.timezone(timezone_str)
    except pytz.UnknownTimeZoneError:
        await update.message.reply_text(
            f'Неизвестный часовой пояс: {timezone_str}\n'
            'Используйте формат Region/City\n'
            'Например: Europe/Moscow, America/New_York'
        )
        return

    await set_user_timezone(user_id, timezone_str)
    await update.message.reply_text(f'Часовой пояс установлен: {timezone_str}')
    logger.info(f"Пользователь {user_id} установил часовой пояс {timezone_str}")


async def my_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /my_timezone - показать текущий часовой пояс"""
    user_id = update.effective_user.id
    timezone = await get_user_timezone(user_id)

    tz = pytz.timezone(timezone)
    current_time = datetime.now(tz).strftime('%H:%M')

    await update.message.reply_text(
        f'Ваш часовой пояс: {timezone}\n'
        f'Текущее время: {current_time}'
    )


async def took_pills_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия кнопки 'Я принял таблетки'"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith('took_pills_'):
        return

    try:
        reminder_id = int(data.replace('took_pills_', ''))
    except ValueError:
        return

    reminder = await get_reminder_by_id(reminder_id)
    if not reminder:
        await query.edit_message_text('Напоминание не найдено')
        return

    user_id = query.from_user.id
    user_tz_str = await get_user_timezone(user_id)
    user_tz = pytz.timezone(user_tz_str)
    today = datetime.now(user_tz).date()

    await acknowledge_reminder(reminder_id, today)

    await query.edit_message_text(
        f'Отлично! Вы приняли таблетки в {reminder["time"]}.\n'
        'Хорошего дня!'
    )
    logger.info(f"Пользователь {user_id} подтвердил приём таблеток (напоминание {reminder_id})")


async def send_reminder_message(context: ContextTypes.DEFAULT_TYPE):
    """Отправить сообщение с напоминанием"""
    job = context.job
    user_id = job.data['user_id']
    reminder_id = job.data['reminder_id']
    reminder_time = job.data['time']

    user_tz_str = await get_user_timezone(user_id)
    user_tz = pytz.timezone(user_tz_str)
    today = datetime.now(user_tz).date()

    if await is_reminder_acknowledged(reminder_id, today):
        return

    await create_or_update_reminder_state(user_id, reminder_id, today)

    meme = await fetch_random_meme()

    keyboard = [[InlineKeyboardButton("Я принял таблетки", callback_data=f'took_pills_{reminder_id}')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if meme and meme.get('url'):
        try:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=meme['url'],
                caption=f'Время принять таблетки! ({reminder_time})',
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Error sending meme photo: {e}")
            await context.bot.send_message(
                chat_id=user_id,
                text=f'{get_fallback_message()}\n\nВремя: {reminder_time}',
                reply_markup=reply_markup
            )
    else:
        await context.bot.send_message(
            chat_id=user_id,
            text=f'{get_fallback_message()}\n\nВремя: {reminder_time}',
            reply_markup=reply_markup
        )

    logger.info(f"Отправлено напоминание пользователю {user_id} (ID: {reminder_id})")


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Проверка и отправка напоминаний"""
    reminders = await get_all_active_reminders()

    for reminder in reminders:
        user_id = reminder['user_id']
        reminder_id = reminder['id']
        reminder_time = reminder['time']
        user_tz_str = reminder['timezone']

        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.UTC

        now = datetime.now(user_tz)
        today = now.date()

        reminder_hour, reminder_minute = map(int, reminder_time.split(':'))
        reminder_datetime = user_tz.localize(
            datetime(today.year, today.month, today.day, reminder_hour, reminder_minute)
        )

        if await is_reminder_acknowledged(reminder_id, today):
            continue

        if now >= reminder_datetime:
            state = await get_reminder_state(reminder_id, today)

            should_send = False
            if state is None:
                should_send = True
            else:
                last_sent_str = state.get('last_sent')
                if last_sent_str:
                    last_sent = datetime.fromisoformat(last_sent_str)
                    last_sent_utc = pytz.UTC.localize(last_sent)
                    now_utc = now.astimezone(pytz.UTC)
                    if (now_utc - last_sent_utc).total_seconds() >= REMINDER_INTERVAL:
                        should_send = True
                else:
                    should_send = True

            if should_send:
                job_name = f'reminder_{user_id}_{reminder_id}_{today.isoformat()}'
                context.job_queue.run_once(
                    send_reminder_message,
                    when=0,
                    data={
                        'user_id': user_id,
                        'reminder_id': reminder_id,
                        'time': reminder_time
                    },
                    name=job_name
                )


async def post_init(application: Application):
    """Инициализация после запуска"""
    await init_db()
    logger.info("База данных инициализирована")

    application.job_queue.run_repeating(
        check_reminders,
        interval=60,
        first=10,
        name='check_reminders'
    )
    logger.info("Планировщик напоминаний запущен")


def main():
    """Запуск бота"""
    logger.info(f"Запуск бота с моделью {OLLAMA_MODEL} на {OLLAMA_HOST}")

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))

    # Регистрация обработчиков напоминаний
    application.add_handler(CommandHandler("add_reminder", add_reminder_command))
    application.add_handler(CommandHandler("list_reminders", list_reminders_command))
    application.add_handler(CommandHandler("remove_reminder", remove_reminder_command))
    application.add_handler(CommandHandler("set_timezone", set_timezone_command))
    application.add_handler(CommandHandler("my_timezone", my_timezone_command))

    # Регистрация обработчика callback-кнопок
    application.add_handler(CallbackQueryHandler(took_pills_callback, pattern=r'^took_pills_\d+$'))

    # Регистрация обработчика текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота
    logger.info("Бот успешно запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()