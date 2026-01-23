import logging
import re
from datetime import datetime, date
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from config import (
    TELEGRAM_TOKEN,
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

# Состояния для ConversationHandler
WAITING_FOR_TIME = 1

# Регионы часовых поясов
TIMEZONE_REGIONS = {
    'europe': 'Европа',
    'asia': 'Азия',
    'america': 'Америка',
    'africa': 'Африка',
    'australia': 'Австралия',
    'pacific': 'Тихий океан',
}

# Популярные часовые пояса по регионам
TIMEZONES_BY_REGION = {
    'europe': [
        ('Europe/Moscow', 'Москва (MSK)'),
        ('Europe/Kaliningrad', 'Калининград (EET)'),
        ('Europe/Samara', 'Самара (SAMT)'),
        ('Europe/Kiev', 'Киев (EET)'),
        ('Europe/Minsk', 'Минск (MSK)'),
        ('Europe/London', 'Лондон (GMT)'),
        ('Europe/Paris', 'Париж (CET)'),
        ('Europe/Berlin', 'Берлин (CET)'),
        ('Europe/Rome', 'Рим (CET)'),
        ('Europe/Madrid', 'Мадрид (CET)'),
        ('Europe/Warsaw', 'Варшава (CET)'),
        ('Europe/Istanbul', 'Стамбул (TRT)'),
    ],
    'asia': [
        ('Asia/Yekaterinburg', 'Екатеринбург (YEKT)'),
        ('Asia/Omsk', 'Омск (OMST)'),
        ('Asia/Novosibirsk', 'Новосибирск (NOVT)'),
        ('Asia/Krasnoyarsk', 'Красноярск (KRAT)'),
        ('Asia/Irkutsk', 'Иркутск (IRKT)'),
        ('Asia/Yakutsk', 'Якутск (YAKT)'),
        ('Asia/Vladivostok', 'Владивосток (VLAT)'),
        ('Asia/Magadan', 'Магадан (MAGT)'),
        ('Asia/Kamchatka', 'Камчатка (PETT)'),
        ('Asia/Almaty', 'Алматы (ALMT)'),
        ('Asia/Tashkent', 'Ташкент (UZT)'),
        ('Asia/Baku', 'Баку (AZT)'),
        ('Asia/Tbilisi', 'Тбилиси (GET)'),
        ('Asia/Yerevan', 'Ереван (AMT)'),
        ('Asia/Dubai', 'Дубай (GST)'),
        ('Asia/Tokyo', 'Токио (JST)'),
        ('Asia/Shanghai', 'Шанхай (CST)'),
        ('Asia/Singapore', 'Сингапур (SGT)'),
        ('Asia/Bangkok', 'Бангкок (ICT)'),
        ('Asia/Kolkata', 'Индия (IST)'),
    ],
    'america': [
        ('America/New_York', 'Нью-Йорк (EST)'),
        ('America/Chicago', 'Чикаго (CST)'),
        ('America/Denver', 'Денвер (MST)'),
        ('America/Los_Angeles', 'Лос-Анджелес (PST)'),
        ('America/Toronto', 'Торонто (EST)'),
        ('America/Mexico_City', 'Мехико (CST)'),
        ('America/Sao_Paulo', 'Сан-Паулу (BRT)'),
        ('America/Buenos_Aires', 'Буэнос-Айрес (ART)'),
        ('America/Lima', 'Лима (PET)'),
        ('America/Bogota', 'Богота (COT)'),
    ],
    'africa': [
        ('Africa/Cairo', 'Каир (EET)'),
        ('Africa/Johannesburg', 'Йоханнесбург (SAST)'),
        ('Africa/Lagos', 'Лагос (WAT)'),
        ('Africa/Nairobi', 'Найроби (EAT)'),
        ('Africa/Casablanca', 'Касабланка (WET)'),
    ],
    'australia': [
        ('Australia/Sydney', 'Сидней (AEST)'),
        ('Australia/Melbourne', 'Мельбурн (AEST)'),
        ('Australia/Brisbane', 'Брисбен (AEST)'),
        ('Australia/Perth', 'Перт (AWST)'),
        ('Australia/Adelaide', 'Аделаида (ACST)'),
    ],
    'pacific': [
        ('Pacific/Auckland', 'Окленд (NZST)'),
        ('Pacific/Fiji', 'Фиджи (FJT)'),
        ('Pacific/Honolulu', 'Гонолулу (HST)'),
        ('Pacific/Guam', 'Гуам (ChST)'),
    ],
}


def get_main_menu_keyboard():
    """Создать инлайн-клавиатуру главного меню"""
    keyboard = [
        [InlineKeyboardButton("Добавить напоминание", callback_data='menu_add')],
        [InlineKeyboardButton("Мои напоминания", callback_data='menu_list')],
        [InlineKeyboardButton("Часовой пояс", callback_data='menu_timezone')],
        [InlineKeyboardButton("Помощь", callback_data='menu_help')],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_persistent_keyboard():
    """Создать постоянную клавиатуру под полем ввода"""
    keyboard = [[KeyboardButton("Меню")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id

    await get_or_create_user(user_id)
    user_tz = await get_user_timezone(user_id)
    tz = pytz.timezone(user_tz)
    current_time = datetime.now(tz).strftime('%H:%M')

    welcome_message = (
        'Привет! Я бот-напоминалка о приёме таблеток.\n\n'
        f'Ваш часовой пояс: {user_tz}\n'
        f'Текущее время: {current_time}\n\n'
        'Выберите действие:'
    )

    # Отправляем сообщение с постоянной клавиатурой
    await update.message.reply_text(
        welcome_message,
        reply_markup=get_persistent_keyboard()
    )
    # Отправляем инлайн-меню
    await update.message.reply_text(
        'Главное меню:',
        reply_markup=get_main_menu_keyboard()
    )
    logger.info(f"Пользователь {user_id} запустил бота")


async def menu_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия кнопки Меню"""
    user_id = update.effective_user.id
    user_tz = await get_user_timezone(user_id)
    tz = pytz.timezone(user_tz)
    current_time = datetime.now(tz).strftime('%H:%M')

    text = (
        'Главное меню\n\n'
        f'Часовой пояс: {user_tz}\n'
        f'Текущее время: {current_time}\n\n'
        'Выберите действие:'
    )

    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать главное меню"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    user_tz = await get_user_timezone(user_id)
    tz = pytz.timezone(user_tz)
    current_time = datetime.now(tz).strftime('%H:%M')

    text = (
        'Главное меню\n\n'
        f'Часовой пояс: {user_tz}\n'
        f'Текущее время: {current_time}\n\n'
        'Выберите действие:'
    )

    await query.edit_message_text(text, reply_markup=get_main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    keyboard = [[InlineKeyboardButton("« Назад в меню", callback_data='menu_back')]]

    help_text = (
        '*Справка по использованию*\n\n'
        'Этот бот напоминает о приёме таблеток.\n\n'
        '*Как пользоваться:*\n'
        '1. Установите свой часовой пояс\n'
        '2. Добавьте напоминания на нужное время\n'
        '3. Когда придёт время, бот пришлёт напоминание\n'
        '4. Нажмите кнопку, когда примете таблетки\n\n'
        'Бот будет напоминать каждые 5 минут, пока вы не подтвердите приём.'
    )
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать справку через меню"""
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("« Назад в меню", callback_data='menu_back')]]

    help_text = (
        '*Справка по использованию*\n\n'
        'Этот бот напоминает о приёме таблеток.\n\n'
        '*Как пользоваться:*\n'
        '1. Установите свой часовой пояс\n'
        '2. Добавьте напоминания на нужное время\n'
        '3. Когда придёт время, бот пришлёт напоминание\n'
        '4. Нажмите кнопку, когда примете таблетки\n\n'
        'Бот будет напоминать каждые 5 минут, пока вы не подтвердите приём.'
    )
    await query.edit_message_text(help_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать добавление напоминания"""
    query = update.callback_query
    await query.answer()

    keyboard = [[InlineKeyboardButton("« Отмена", callback_data='menu_back')]]

    await query.edit_message_text(
        'Введите время напоминания в формате ЧЧ:ММ\n\n'
        'Например: 09:00 или 21:30',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return WAITING_FOR_TIME


async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время от пользователя"""
    user_id = update.effective_user.id
    time_str = update.message.text.strip()

    if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data='menu_back')]]
        await update.message.reply_text(
            'Неверный формат времени. Используйте ЧЧ:ММ\n'
            'Например: 09:00 или 21:30',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_TIME

    if len(time_str) == 4:
        time_str = '0' + time_str

    reminder_id = await add_reminder(user_id, time_str)
    user_tz = await get_user_timezone(user_id)

    await update.message.reply_text(
        f'Напоминание добавлено!\n\n'
        f'Время: {time_str}\n'
        f'Часовой пояс: {user_tz}',
        reply_markup=get_main_menu_keyboard()
    )
    logger.info(f"Пользователь {user_id} добавил напоминание на {time_str}")

    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена разговора"""
    query = update.callback_query
    if query:
        await query.answer()
        await show_main_menu(update, context)
    return ConversationHandler.END


async def menu_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список напоминаний с кнопками удаления"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    reminders = await get_user_reminders(user_id)
    user_tz = await get_user_timezone(user_id)

    if not reminders:
        keyboard = [[InlineKeyboardButton("« Назад в меню", callback_data='menu_back')]]
        await query.edit_message_text(
            'У вас пока нет напоминаний.\n\n'
            'Нажмите "Добавить напоминание" в меню.',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = f'*Ваши напоминания*\nЧасовой пояс: {user_tz}\n\n'

    keyboard = []
    for r in reminders:
        text += f'• {r["time"]}\n'
        keyboard.append([
            InlineKeyboardButton(f'Удалить {r["time"]}', callback_data=f'delete_{r["id"]}')
        ])

    keyboard.append([InlineKeyboardButton("« Назад в меню", callback_data='menu_back')])

    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def delete_reminder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить напоминание"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    reminder_id = int(query.data.replace('delete_', ''))

    success = await remove_reminder(user_id, reminder_id)

    if success:
        logger.info(f"Пользователь {user_id} удалил напоминание {reminder_id}")

    # Показать обновлённый список
    reminders = await get_user_reminders(user_id)
    user_tz = await get_user_timezone(user_id)

    if not reminders:
        keyboard = [[InlineKeyboardButton("« Назад в меню", callback_data='menu_back')]]
        await query.edit_message_text(
            'Напоминание удалено!\n\n'
            'У вас больше нет напоминаний.',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    text = f'Напоминание удалено!\n\n*Ваши напоминания*\nЧасовой пояс: {user_tz}\n\n'

    keyboard = []
    for r in reminders:
        text += f'• {r["time"]}\n'
        keyboard.append([
            InlineKeyboardButton(f'Удалить {r["time"]}', callback_data=f'delete_{r["id"]}')
        ])

    keyboard.append([InlineKeyboardButton("« Назад в меню", callback_data='menu_back')])

    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню выбора часового пояса"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    current_tz = await get_user_timezone(user_id)
    tz = pytz.timezone(current_tz)
    current_time = datetime.now(tz).strftime('%H:%M')

    keyboard = []
    for region_id, region_name in TIMEZONE_REGIONS.items():
        keyboard.append([InlineKeyboardButton(region_name, callback_data=f'tz_region_{region_id}')])

    keyboard.append([InlineKeyboardButton("« Назад в меню", callback_data='menu_back')])

    await query.edit_message_text(
        f'*Выбор часового пояса*\n\n'
        f'Текущий: {current_tz}\n'
        f'Время: {current_time}\n\n'
        'Выберите регион:',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def timezone_region_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать часовые пояса региона"""
    query = update.callback_query
    await query.answer()

    region = query.data.replace('tz_region_', '')
    region_name = TIMEZONE_REGIONS.get(region, region)
    timezones = TIMEZONES_BY_REGION.get(region, [])

    keyboard = []
    for tz_id, tz_name in timezones:
        keyboard.append([InlineKeyboardButton(tz_name, callback_data=f'tz_set_{tz_id}')])

    keyboard.append([InlineKeyboardButton("« Назад к регионам", callback_data='menu_timezone')])

    await query.edit_message_text(
        f'*{region_name}*\n\nВыберите город:',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def timezone_set_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Установить выбранный часовой пояс"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    timezone_str = query.data.replace('tz_set_', '')

    await set_user_timezone(user_id, timezone_str)

    tz = pytz.timezone(timezone_str)
    current_time = datetime.now(tz).strftime('%H:%M')

    logger.info(f"Пользователь {user_id} установил часовой пояс {timezone_str}")

    await query.edit_message_text(
        f'Часовой пояс установлен!\n\n'
        f'Часовой пояс: {timezone_str}\n'
        f'Текущее время: {current_time}',
        reply_markup=get_main_menu_keyboard()
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
    logger.info("Запуск бота напоминаний о таблетках")

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # ConversationHandler для добавления напоминания
    add_reminder_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_add_callback, pattern='^menu_add$')],
        states={
            WAITING_FOR_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^Меню$'), receive_time),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            CommandHandler("start", start),
            MessageHandler(filters.Regex('^Меню$'), menu_button_handler),
        ],
    )

    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Регистрация обработчика кнопки "Меню"
    application.add_handler(MessageHandler(filters.Regex('^Меню$'), menu_button_handler))

    # Регистрация ConversationHandler
    application.add_handler(add_reminder_handler)

    # Регистрация обработчиков меню
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern='^menu_back$'))
    application.add_handler(CallbackQueryHandler(menu_help_callback, pattern='^menu_help$'))
    application.add_handler(CallbackQueryHandler(menu_list_callback, pattern='^menu_list$'))
    application.add_handler(CallbackQueryHandler(menu_timezone_callback, pattern='^menu_timezone$'))

    # Регистрация обработчиков часовых поясов
    application.add_handler(CallbackQueryHandler(timezone_region_callback, pattern=r'^tz_region_'))
    application.add_handler(CallbackQueryHandler(timezone_set_callback, pattern=r'^tz_set_'))

    # Регистрация обработчика удаления напоминаний
    application.add_handler(CallbackQueryHandler(delete_reminder_callback, pattern=r'^delete_\d+$'))

    # Регистрация обработчика подтверждения приёма таблеток
    application.add_handler(CallbackQueryHandler(took_pills_callback, pattern=r'^took_pills_\d+$'))

    # Запуск бота
    logger.info("Бот успешно запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()