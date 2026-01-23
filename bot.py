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
    get_reminder_by_id,
    should_reminder_trigger,
    get_frequency_description,
    get_weekend_work_status,
    set_weekend_work_status,
    create_work_question,
    get_pending_work_questions,
    get_advanced_daily_reminders_needing_questions,
    get_reminder_time_for_date
)
from meme_api import fetch_random_meme, get_fallback_message

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=getattr(logging, LOG_LEVEL)
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
SELECTING_FREQUENCY = 1
SELECTING_DAY_OF_WEEK = 2
SELECTING_DAY_OF_MONTH = 3
SELECTING_MONTH_FALLBACK = 4
WAITING_FOR_TIME = 5
# Состояния для расширенных ежедневных напоминаний
SELECTING_DAILY_MODE = 6
WAITING_FOR_EVEN_TIME = 7
WAITING_FOR_ODD_TIME = 8
SELECTING_WEEKEND_OVERRIDE = 9
WAITING_FOR_WEEKEND_NO_WORK_TIME = 10
WAITING_FOR_WEEKEND_WITH_WORK_TIME = 11
WAITING_FOR_ASK_WORK_TIME = 12

# Названия дней недели
DAYS_OF_WEEK = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
DAYS_OF_WEEK_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

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
    """Начать добавление напоминания - выбор частоты"""
    query = update.callback_query
    await query.answer()

    # Сбрасываем данные напоминания
    context.user_data['reminder'] = {}

    keyboard = [
        [InlineKeyboardButton("Ежедневно", callback_data='freq_daily')],
        [InlineKeyboardButton("Еженедельно", callback_data='freq_weekly')],
        [InlineKeyboardButton("Ежемесячно", callback_data='freq_monthly')],
        [InlineKeyboardButton("« Отмена", callback_data='menu_back')],
    ]

    await query.edit_message_text(
        '*Новое напоминание*\n\n'
        'Выберите частоту напоминания:',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return SELECTING_FREQUENCY


async def select_frequency_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора частоты"""
    query = update.callback_query
    await query.answer()

    frequency = query.data.replace('freq_', '')
    context.user_data['reminder']['frequency'] = frequency

    if frequency == 'daily':
        # Выбор режима: простой или расширенный
        keyboard = [
            [InlineKeyboardButton("Простой (одно время)", callback_data='daily_simple')],
            [InlineKeyboardButton("Расширенный (чёт/нечет + выходные)", callback_data='daily_advanced')],
            [InlineKeyboardButton("« Назад", callback_data='back_to_frequency')],
        ]
        await query.edit_message_text(
            '*Новое напоминание*\n'
            'Частота: Ежедневно\n\n'
            'Выберите режим настройки:',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_DAILY_MODE

    elif frequency == 'weekly':
        # Выбор дня недели
        keyboard = []
        for i, day in enumerate(DAYS_OF_WEEK):
            keyboard.append([InlineKeyboardButton(day, callback_data=f'dow_{i}')])
        keyboard.append([InlineKeyboardButton("« Назад", callback_data='back_to_frequency')])

        await query.edit_message_text(
            '*Новое напоминание*\n'
            'Частота: Еженедельно\n\n'
            'Выберите день недели:',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_DAY_OF_WEEK

    elif frequency == 'monthly':
        # Выбор дня месяца
        keyboard = []
        row = []
        for day in range(1, 32):
            row.append(InlineKeyboardButton(str(day), callback_data=f'dom_{day}'))
            if len(row) == 7:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("« Назад", callback_data='back_to_frequency')])

        await query.edit_message_text(
            '*Новое напоминание*\n'
            'Частота: Ежемесячно\n\n'
            'Выберите день месяца:',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_DAY_OF_MONTH


async def back_to_frequency_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Вернуться к выбору частоты"""
    query = update.callback_query
    await query.answer()

    context.user_data['reminder'] = {}

    keyboard = [
        [InlineKeyboardButton("Ежедневно", callback_data='freq_daily')],
        [InlineKeyboardButton("Еженедельно", callback_data='freq_weekly')],
        [InlineKeyboardButton("Ежемесячно", callback_data='freq_monthly')],
        [InlineKeyboardButton("« Отмена", callback_data='menu_back')],
    ]

    await query.edit_message_text(
        '*Новое напоминание*\n\n'
        'Выберите частоту напоминания:',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return SELECTING_FREQUENCY


async def select_day_of_week_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора дня недели"""
    query = update.callback_query
    await query.answer()

    day_of_week = int(query.data.replace('dow_', ''))
    context.user_data['reminder']['day_of_week'] = day_of_week

    keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]

    await query.edit_message_text(
        f'*Новое напоминание*\n'
        f'Частота: Еженедельно ({DAYS_OF_WEEK[day_of_week]})\n\n'
        'Введите время в формате ЧЧ:ММ\n'
        'Например: 09:00 или 21:30',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return WAITING_FOR_TIME


async def select_day_of_month_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора дня месяца"""
    query = update.callback_query
    await query.answer()

    day_of_month = int(query.data.replace('dom_', ''))
    context.user_data['reminder']['day_of_month'] = day_of_month

    # Если выбран день > 28, спрашиваем про fallback
    if day_of_month > 28:
        keyboard = [
            [InlineKeyboardButton("Последний день месяца", callback_data='fallback_last_day')],
            [InlineKeyboardButton("Пропустить месяц", callback_data='fallback_skip')],
            [InlineKeyboardButton("« Назад", callback_data='back_to_frequency')],
        ]

        await query.edit_message_text(
            f'*Новое напоминание*\n'
            f'Частота: Ежемесячно ({day_of_month}-е число)\n\n'
            f'Что делать, если {day_of_month}-го числа нет в месяце?\n'
            '(например, 30 февраля)',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECTING_MONTH_FALLBACK
    else:
        # Дни 1-28 есть в каждом месяце
        context.user_data['reminder']['month_fallback'] = 'last_day'

        keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]

        await query.edit_message_text(
            f'*Новое напоминание*\n'
            f'Частота: Ежемесячно ({day_of_month}-е число)\n\n'
            'Введите время в формате ЧЧ:ММ\n'
            'Например: 09:00 или 21:30',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return WAITING_FOR_TIME


async def select_month_fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора fallback для месяца"""
    query = update.callback_query
    await query.answer()

    fallback = query.data.replace('fallback_', '')
    context.user_data['reminder']['month_fallback'] = fallback

    day_of_month = context.user_data['reminder']['day_of_month']
    fallback_text = 'последний день месяца' if fallback == 'last_day' else 'пропустить'

    keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]

    await query.edit_message_text(
        f'*Новое напоминание*\n'
        f'Частота: Ежемесячно ({day_of_month}-е число)\n'
        f'Если дня нет: {fallback_text}\n\n'
        'Введите время в формате ЧЧ:ММ\n'
        'Например: 09:00 или 21:30',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return WAITING_FOR_TIME


# --- Обработчики для расширенных ежедневных напоминаний ---

async def select_daily_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора режима ежедневного напоминания"""
    query = update.callback_query
    await query.answer()

    mode = query.data.replace('daily_', '')
    context.user_data['reminder']['daily_mode'] = mode

    if mode == 'simple':
        keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]
        await query.edit_message_text(
            '*Новое напоминание*\n'
            'Частота: Ежедневно (простой)\n\n'
            'Введите время в формате ЧЧ:ММ\n'
            'Например: 09:00 или 21:30',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_TIME

    else:  # advanced
        keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]
        await query.edit_message_text(
            '*Новое напоминание*\n'
            'Частота: Ежедневно (расширенный)\n\n'
            '*Шаг 1 из 5:* Время для ЧЁТНЫХ дней месяца\n'
            '(2, 4, 6, 8... числа)\n\n'
            'Введите время в формате ЧЧ:ММ:',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_EVEN_TIME


async def receive_even_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время для чётных дней"""
    time_str = update.message.text.strip()

    if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data='menu_back')]]
        await update.message.reply_text(
            'Неверный формат времени. Используйте ЧЧ:ММ\n'
            'Например: 09:00 или 21:30',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_EVEN_TIME

    if len(time_str) == 4:
        time_str = '0' + time_str

    context.user_data['reminder']['even_day_time'] = time_str

    keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]
    await update.message.reply_text(
        '*Новое напоминание*\n'
        'Частота: Ежедневно (расширенный)\n\n'
        f'Чётные дни: {time_str}\n\n'
        '*Шаг 2 из 5:* Время для НЕЧЁТНЫХ дней месяца\n'
        '(1, 3, 5, 7... числа)\n\n'
        'Введите время в формате ЧЧ:ММ:',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_ODD_TIME


async def receive_odd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время для нечётных дней"""
    time_str = update.message.text.strip()

    if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data='menu_back')]]
        await update.message.reply_text(
            'Неверный формат времени. Используйте ЧЧ:ММ',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_ODD_TIME

    if len(time_str) == 4:
        time_str = '0' + time_str

    context.user_data['reminder']['odd_day_time'] = time_str
    even_time = context.user_data['reminder']['even_day_time']

    keyboard = [
        [InlineKeyboardButton("Да, настроить выходные", callback_data='weekend_yes')],
        [InlineKeyboardButton("Нет, использовать чёт/нечет", callback_data='weekend_no')],
        [InlineKeyboardButton("« Назад", callback_data='back_to_frequency')],
    ]
    await update.message.reply_text(
        '*Новое напоминание*\n'
        'Частота: Ежедневно (расширенный)\n\n'
        f'Чётные дни: {even_time}\n'
        f'Нечётные дни: {time_str}\n\n'
        '*Шаг 3 из 5:* Настроить особое время для выходных?\n\n'
        'Это позволит задать отдельное время для Сб и Вс,\n'
        'которое заменит правило чёт/нечет.',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECTING_WEEKEND_OVERRIDE


async def select_weekend_override_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора настройки выходных"""
    query = update.callback_query
    await query.answer()

    choice = query.data.replace('weekend_', '')
    even_time = context.user_data['reminder']['even_day_time']
    odd_time = context.user_data['reminder']['odd_day_time']

    if choice == 'no':
        context.user_data['reminder']['weekend_override'] = False
        # Сохраняем напоминание
        return await save_advanced_daily_reminder(update, context)

    else:  # yes
        context.user_data['reminder']['weekend_override'] = True
        keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]
        await query.edit_message_text(
            '*Новое напоминание*\n'
            'Частота: Ежедневно (расширенный)\n\n'
            f'Чётные дни: {even_time}\n'
            f'Нечётные дни: {odd_time}\n\n'
            '*Шаг 4 из 5:* Время в выходные БЕЗ работы\n\n'
            'Введите время в формате ЧЧ:ММ:',
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_WEEKEND_NO_WORK_TIME


async def receive_weekend_no_work_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время для выходных без работы"""
    time_str = update.message.text.strip()

    if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data='menu_back')]]
        await update.message.reply_text(
            'Неверный формат времени. Используйте ЧЧ:ММ',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_WEEKEND_NO_WORK_TIME

    if len(time_str) == 4:
        time_str = '0' + time_str

    context.user_data['reminder']['weekend_time_no_work'] = time_str
    even_time = context.user_data['reminder']['even_day_time']
    odd_time = context.user_data['reminder']['odd_day_time']

    keyboard = [[InlineKeyboardButton("« Назад", callback_data='back_to_frequency')]]
    await update.message.reply_text(
        '*Новое напоминание*\n'
        'Частота: Ежедневно (расширенный)\n\n'
        f'Чётные дни: {even_time}\n'
        f'Нечётные дни: {odd_time}\n'
        f'Выходные (без работы): {time_str}\n\n'
        '*Шаг 5 из 5:* Время в выходные С работой\n\n'
        'Введите время в формате ЧЧ:ММ:',
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_WEEKEND_WITH_WORK_TIME


async def receive_weekend_with_work_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время для выходных с работой"""
    time_str = update.message.text.strip()

    if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_str):
        keyboard = [[InlineKeyboardButton("« Отмена", callback_data='menu_back')]]
        await update.message.reply_text(
            'Неверный формат времени. Используйте ЧЧ:ММ',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return WAITING_FOR_WEEKEND_WITH_WORK_TIME

    if len(time_str) == 4:
        time_str = '0' + time_str

    context.user_data['reminder']['weekend_time_with_work'] = time_str

    # Сохраняем напоминание
    return await save_advanced_daily_reminder(update, context)


async def save_advanced_daily_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранить расширенное ежедневное напоминание"""
    user_id = update.effective_user.id
    reminder_data = context.user_data.get('reminder', {})

    even_time = reminder_data.get('even_day_time')
    odd_time = reminder_data.get('odd_day_time')
    weekend_override = reminder_data.get('weekend_override', False)
    weekend_no_work = reminder_data.get('weekend_time_no_work')
    weekend_with_work = reminder_data.get('weekend_time_with_work')

    await add_reminder(
        user_id=user_id,
        time=even_time,  # Основное время (для обратной совместимости)
        frequency='daily',
        daily_mode='advanced',
        even_day_time=even_time,
        odd_day_time=odd_time,
        weekend_override=weekend_override,
        weekend_time_no_work=weekend_no_work,
        weekend_time_with_work=weekend_with_work,
        ask_work_time='18:00'  # По умолчанию спрашиваем в 18:00
    )

    user_tz = await get_user_timezone(user_id)

    # Формируем описание
    desc = (
        f'Напоминание добавлено!\n\n'
        f'Режим: Ежедневно (расширенный)\n'
        f'Чётные дни: {even_time}\n'
        f'Нечётные дни: {odd_time}\n'
    )
    if weekend_override:
        desc += (
            f'Выходные без работы: {weekend_no_work}\n'
            f'Выходные с работой: {weekend_with_work}\n'
            f'\nБот будет спрашивать накануне выходных,\n'
            f'есть ли у вас работа на следующий день.'
        )
    desc += f'\n\nЧасовой пояс: {user_tz}'

    # Определяем источник сообщения
    if update.callback_query:
        await update.callback_query.edit_message_text(
            desc,
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            desc,
            reply_markup=get_main_menu_keyboard()
        )

    logger.info(f"Пользователь {user_id} добавил расширенное ежедневное напоминание")

    # Очищаем данные
    context.user_data.pop('reminder', None)

    return ConversationHandler.END


async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить время от пользователя и сохранить напоминание"""
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

    # Получаем данные напоминания из контекста
    reminder_data = context.user_data.get('reminder', {})
    frequency = reminder_data.get('frequency', 'daily')
    day_of_week = reminder_data.get('day_of_week')
    day_of_month = reminder_data.get('day_of_month')
    month_fallback = reminder_data.get('month_fallback', 'last_day')

    reminder_id = await add_reminder(
        user_id=user_id,
        time=time_str,
        frequency=frequency,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        month_fallback=month_fallback
    )

    user_tz = await get_user_timezone(user_id)

    # Формируем описание частоты
    freq_desc = 'Ежедневно'
    if frequency == 'weekly':
        freq_desc = f'Еженедельно ({DAYS_OF_WEEK[day_of_week]})'
    elif frequency == 'monthly':
        fallback_text = 'последний день' if month_fallback == 'last_day' else 'пропустить'
        if day_of_month > 28:
            freq_desc = f'Ежемесячно ({day_of_month}-е, иначе {fallback_text})'
        else:
            freq_desc = f'Ежемесячно ({day_of_month}-е число)'

    await update.message.reply_text(
        f'Напоминание добавлено!\n\n'
        f'Время: {time_str}\n'
        f'Частота: {freq_desc}\n'
        f'Часовой пояс: {user_tz}',
        reply_markup=get_main_menu_keyboard()
    )

    logger.info(f"Пользователь {user_id} добавил напоминание: {time_str}, {frequency}")

    # Очищаем данные
    context.user_data.pop('reminder', None)

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
        freq_desc = get_frequency_description(r)
        text += f'• {r["time"]} — {freq_desc}\n'
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
        freq_desc = get_frequency_description(r)
        text += f'• {r["time"]} — {freq_desc}\n'
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


async def check_weekend_work_questions(context: ContextTypes.DEFAULT_TYPE):
    """Проверка и отправка вопросов о работе в выходные"""
    from datetime import timedelta

    reminders = await get_advanced_daily_reminders_needing_questions()

    for reminder in reminders:
        user_id = reminder['user_id']
        reminder_id = reminder['id']
        ask_work_time = reminder.get('ask_work_time', '18:00')
        user_tz_str = reminder['timezone']

        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.UTC

        now = datetime.now(user_tz)
        today = now.date()
        tomorrow = today + timedelta(days=1)

        # Проверяем, является ли завтра выходным (Сб=5, Вс=6)
        if tomorrow.weekday() not in (5, 6):
            continue

        # Проверяем, пора ли спрашивать
        ask_hour, ask_minute = map(int, ask_work_time.split(':'))
        ask_datetime = user_tz.localize(
            datetime(today.year, today.month, today.day, ask_hour, ask_minute)
        )

        # Вопрос задаём в течение минуты после указанного времени
        if not (ask_datetime <= now < ask_datetime + timedelta(minutes=1)):
            continue

        # Проверяем, был ли уже задан вопрос на эту дату
        existing = await get_weekend_work_status(reminder_id, tomorrow)
        if existing:
            continue

        # Создаём вопрос и отправляем его
        await create_work_question(user_id, reminder_id, tomorrow)

        day_name = 'субботу' if tomorrow.weekday() == 5 else 'воскресенье'
        keyboard = [
            [
                InlineKeyboardButton("Да, работаю", callback_data=f'work_yes_{reminder_id}_{tomorrow.isoformat()}'),
                InlineKeyboardButton("Нет, выходной", callback_data=f'work_no_{reminder_id}_{tomorrow.isoformat()}')
            ]
        ]

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f'Привет! Завтра {day_name}.\n\n'
                     f'У тебя будет работа завтра?\n'
                     f'(Это нужно для выбора времени напоминания)',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"Отправлен вопрос о работе пользователю {user_id} на {tomorrow}")
        except Exception as e:
            logger.error(f"Ошибка отправки вопроса о работе: {e}")


async def work_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ответа на вопрос о работе в выходной"""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    # Парсим данные: work_yes_123_2025-01-25 или work_no_123_2025-01-25
    if data.startswith('work_yes_'):
        has_work = True
        rest = data.replace('work_yes_', '')
    elif data.startswith('work_no_'):
        has_work = False
        rest = data.replace('work_no_', '')
    else:
        return

    parts = rest.rsplit('_', 1)
    if len(parts) != 2:
        return

    try:
        reminder_id = int(parts[0])
        target_date = date.fromisoformat(parts[1])
    except (ValueError, IndexError):
        return

    await set_weekend_work_status(user_id, reminder_id, target_date, has_work)

    reminder = await get_reminder_by_id(reminder_id)
    if not reminder:
        await query.edit_message_text('Напоминание не найдено.')
        return

    if has_work:
        time_to_use = reminder.get('weekend_time_with_work', reminder['time'])
        status_text = 'с работой'
    else:
        time_to_use = reminder.get('weekend_time_no_work', reminder['time'])
        status_text = 'без работы'

    day_name = 'субботу' if target_date.weekday() == 5 else 'воскресенье'

    await query.edit_message_text(
        f'Принято! В {day_name} ({status_text}) напоминание придёт в {time_to_use}.'
    )
    logger.info(f"Пользователь {user_id} указал статус работы: {has_work} на {target_date}")


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Проверка и отправка напоминаний"""
    reminders = await get_all_active_reminders()

    for reminder in reminders:
        user_id = reminder['user_id']
        reminder_id = reminder['id']
        user_tz_str = reminder['timezone']

        try:
            user_tz = pytz.timezone(user_tz_str)
        except pytz.UnknownTimeZoneError:
            user_tz = pytz.UTC

        now = datetime.now(user_tz)
        today = now.date()

        # Проверяем, должно ли напоминание сработать сегодня (по частоте)
        if not should_reminder_trigger(reminder, today):
            continue

        # Определяем время напоминания в зависимости от настроек
        daily_mode = reminder.get('daily_mode', 'simple')

        if reminder.get('frequency') == 'daily' and daily_mode == 'advanced':
            # Для расширенного режима - определяем время в зависимости от дня и статуса работы
            is_weekend = today.weekday() >= 5
            has_work = None

            if is_weekend and reminder.get('weekend_override'):
                # Проверяем статус работы на сегодня
                work_status = await get_weekend_work_status(reminder_id, today)
                if work_status and work_status.get('responded'):
                    has_work = bool(work_status.get('has_work'))

            reminder_time = get_reminder_time_for_date(reminder, today, has_work)
        else:
            reminder_time = reminder['time']

        if not reminder_time:
            continue

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

    application.job_queue.run_repeating(
        check_weekend_work_questions,
        interval=60,
        first=15,
        name='check_weekend_work_questions'
    )
    logger.info("Планировщик вопросов о работе запущен")


def main():
    """Запуск бота"""
    logger.info("Запуск бота напоминаний о таблетках")

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # ConversationHandler для добавления напоминания
    add_reminder_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_add_callback, pattern='^menu_add$')],
        states={
            SELECTING_FREQUENCY: [
                CallbackQueryHandler(select_frequency_callback, pattern=r'^freq_'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            SELECTING_DAILY_MODE: [
                CallbackQueryHandler(select_daily_mode_callback, pattern=r'^daily_'),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            WAITING_FOR_EVEN_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^Меню$'), receive_even_time),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            WAITING_FOR_ODD_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^Меню$'), receive_odd_time),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            SELECTING_WEEKEND_OVERRIDE: [
                CallbackQueryHandler(select_weekend_override_callback, pattern=r'^weekend_'),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            WAITING_FOR_WEEKEND_NO_WORK_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^Меню$'), receive_weekend_no_work_time),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            WAITING_FOR_WEEKEND_WITH_WORK_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^Меню$'), receive_weekend_with_work_time),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            SELECTING_DAY_OF_WEEK: [
                CallbackQueryHandler(select_day_of_week_callback, pattern=r'^dow_\d$'),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            SELECTING_DAY_OF_MONTH: [
                CallbackQueryHandler(select_day_of_month_callback, pattern=r'^dom_\d+$'),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            SELECTING_MONTH_FALLBACK: [
                CallbackQueryHandler(select_month_fallback_callback, pattern=r'^fallback_'),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
            WAITING_FOR_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^Меню$'), receive_time),
                CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
                CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation, pattern='^menu_back$'),
            CallbackQueryHandler(back_to_frequency_callback, pattern='^back_to_frequency$'),
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

    # Регистрация обработчика ответа на вопрос о работе
    application.add_handler(CallbackQueryHandler(work_status_callback, pattern=r'^work_(yes|no)_\d+_'))

    # Запуск бота
    logger.info("Бот успешно запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()