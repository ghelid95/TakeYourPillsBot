import aiosqlite
import calendar
from datetime import datetime, date
from typing import Optional
from config import DATABASE_PATH


async def init_db():
    """Initialize the database with required tables."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                timezone TEXT DEFAULT 'UTC',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                time TEXT NOT NULL,
                frequency TEXT DEFAULT 'daily',
                day_of_week INTEGER,
                day_of_month INTEGER,
                month_fallback TEXT DEFAULT 'last_day',
                daily_mode TEXT DEFAULT 'simple',
                even_day_time TEXT,
                odd_day_time TEXT,
                weekend_override INTEGER DEFAULT 0,
                weekend_time_no_work TEXT,
                weekend_time_with_work TEXT,
                ask_work_time TEXT DEFAULT '18:00',
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS weekend_work_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reminder_id INTEGER NOT NULL,
                target_date DATE NOT NULL,
                has_work INTEGER,
                asked_at TIMESTAMP,
                responded INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (reminder_id) REFERENCES reminders (id),
                UNIQUE(reminder_id, target_date)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS reminder_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                reminder_id INTEGER NOT NULL,
                reminder_date DATE NOT NULL,
                last_sent TIMESTAMP,
                acknowledged INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (reminder_id) REFERENCES reminders (id),
                UNIQUE(reminder_id, reminder_date)
            )
        ''')

        # Миграция: добавление новых колонок если их нет
        migrations = [
            'ALTER TABLE reminders ADD COLUMN frequency TEXT DEFAULT "daily"',
            'ALTER TABLE reminders ADD COLUMN day_of_week INTEGER',
            'ALTER TABLE reminders ADD COLUMN day_of_month INTEGER',
            'ALTER TABLE reminders ADD COLUMN month_fallback TEXT DEFAULT "last_day"',
            'ALTER TABLE reminders ADD COLUMN daily_mode TEXT DEFAULT "simple"',
            'ALTER TABLE reminders ADD COLUMN even_day_time TEXT',
            'ALTER TABLE reminders ADD COLUMN odd_day_time TEXT',
            'ALTER TABLE reminders ADD COLUMN weekend_override INTEGER DEFAULT 0',
            'ALTER TABLE reminders ADD COLUMN weekend_time_no_work TEXT',
            'ALTER TABLE reminders ADD COLUMN weekend_time_with_work TEXT',
            'ALTER TABLE reminders ADD COLUMN ask_work_time TEXT DEFAULT "18:00"',
        ]
        for migration in migrations:
            try:
                await db.execute(migration)
            except:
                pass

        await db.commit()


async def get_or_create_user(user_id: int) -> dict:
    """Get user or create if not exists."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        )
        row = await cursor.fetchone()

        if row:
            return dict(row)

        await db.execute(
            'INSERT INTO users (user_id) VALUES (?)', (user_id,)
        )
        await db.commit()

        cursor = await db.execute(
            'SELECT * FROM users WHERE user_id = ?', (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row)


async def set_user_timezone(user_id: int, timezone: str) -> bool:
    """Set user's timezone."""
    await get_or_create_user(user_id)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'UPDATE users SET timezone = ? WHERE user_id = ?',
            (timezone, user_id)
        )
        await db.commit()
        return True


async def get_user_timezone(user_id: int) -> str:
    """Get user's timezone."""
    user = await get_or_create_user(user_id)
    return user['timezone']


async def add_reminder(
    user_id: int,
    time: str,
    frequency: str = 'daily',
    day_of_week: Optional[int] = None,
    day_of_month: Optional[int] = None,
    month_fallback: str = 'last_day',
    daily_mode: str = 'simple',
    even_day_time: Optional[str] = None,
    odd_day_time: Optional[str] = None,
    weekend_override: bool = False,
    weekend_time_no_work: Optional[str] = None,
    weekend_time_with_work: Optional[str] = None,
    ask_work_time: str = '18:00'
) -> int:
    """
    Add a new reminder for a user. Returns reminder ID.

    Args:
        user_id: Telegram user ID
        time: Time in HH:MM format (for simple daily, weekly, monthly)
        frequency: 'daily', 'weekly', or 'monthly'
        day_of_week: 0-6 (Monday-Sunday) for weekly reminders
        day_of_month: 1-31 for monthly reminders
        month_fallback: 'last_day' or 'skip' for months without the specified day
        daily_mode: 'simple' or 'advanced' for daily reminders
        even_day_time: Time for even days (advanced daily)
        odd_day_time: Time for odd days (advanced daily)
        weekend_override: Whether to use special weekend times
        weekend_time_no_work: Time for weekends without work
        weekend_time_with_work: Time for weekends with work
        ask_work_time: When to ask about next day's work
    """
    await get_or_create_user(user_id)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            '''INSERT INTO reminders
               (user_id, time, frequency, day_of_week, day_of_month, month_fallback,
                daily_mode, even_day_time, odd_day_time, weekend_override,
                weekend_time_no_work, weekend_time_with_work, ask_work_time)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, time, frequency, day_of_week, day_of_month, month_fallback,
             daily_mode, even_day_time, odd_day_time, int(weekend_override),
             weekend_time_no_work, weekend_time_with_work, ask_work_time)
        )
        await db.commit()
        return cursor.lastrowid


async def get_user_reminders(user_id: int) -> list:
    """Get all active reminders for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM reminders WHERE user_id = ? AND active = 1 ORDER BY time',
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_all_active_reminders() -> list:
    """Get all active reminders from all users."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT r.*, u.timezone
            FROM reminders r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.active = 1
        ''')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def remove_reminder(user_id: int, reminder_id: int) -> bool:
    """Remove a reminder by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            'UPDATE reminders SET active = 0 WHERE id = ? AND user_id = ?',
            (reminder_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_reminder_state(reminder_id: int, reminder_date: date) -> Optional[dict]:
    """Get reminder state for a specific date."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM reminder_states WHERE reminder_id = ? AND reminder_date = ?',
            (reminder_id, reminder_date.isoformat())
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_or_update_reminder_state(
    user_id: int,
    reminder_id: int,
    reminder_date: date,
    acknowledged: bool = False
) -> dict:
    """Create or update reminder state for a specific date."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            'SELECT * FROM reminder_states WHERE reminder_id = ? AND reminder_date = ?',
            (reminder_id, reminder_date.isoformat())
        )
        existing = await cursor.fetchone()

        if existing:
            await db.execute('''
                UPDATE reminder_states
                SET last_sent = ?, acknowledged = ?
                WHERE reminder_id = ? AND reminder_date = ?
            ''', (datetime.utcnow().isoformat(), int(acknowledged),
                  reminder_id, reminder_date.isoformat()))
        else:
            await db.execute('''
                INSERT INTO reminder_states (user_id, reminder_id, reminder_date, last_sent, acknowledged)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, reminder_id, reminder_date.isoformat(),
                  datetime.utcnow().isoformat(), int(acknowledged)))

        await db.commit()

        cursor = await db.execute(
            'SELECT * FROM reminder_states WHERE reminder_id = ? AND reminder_date = ?',
            (reminder_id, reminder_date.isoformat())
        )
        row = await cursor.fetchone()
        return dict(row)


async def acknowledge_reminder(reminder_id: int, reminder_date: date) -> bool:
    """Mark a reminder as acknowledged for a specific date."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute('''
            UPDATE reminder_states
            SET acknowledged = 1
            WHERE reminder_id = ? AND reminder_date = ?
        ''', (reminder_id, reminder_date.isoformat()))
        await db.commit()
        return cursor.rowcount > 0


async def is_reminder_acknowledged(reminder_id: int, reminder_date: date) -> bool:
    """Check if a reminder has been acknowledged for a specific date."""
    state = await get_reminder_state(reminder_id, reminder_date)
    return state is not None and state['acknowledged'] == 1


async def get_reminder_by_id(reminder_id: int) -> Optional[dict]:
    """Get a reminder by its ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM reminders WHERE id = ?', (reminder_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


def should_reminder_trigger(reminder: dict, check_date: date) -> bool:
    """
    Check if a reminder should trigger on a specific date based on its frequency.

    Args:
        reminder: Reminder dict with frequency, day_of_week, day_of_month, month_fallback
        check_date: Date to check

    Returns:
        True if reminder should trigger on this date
    """
    frequency = reminder.get('frequency', 'daily')

    if frequency == 'daily':
        return True

    elif frequency == 'weekly':
        day_of_week = reminder.get('day_of_week')
        if day_of_week is None:
            return True  # Fallback to daily if not set
        # Python weekday: Monday=0, Sunday=6
        return check_date.weekday() == day_of_week

    elif frequency == 'monthly':
        day_of_month = reminder.get('day_of_month')
        if day_of_month is None:
            return True  # Fallback to daily if not set

        month_fallback = reminder.get('month_fallback', 'last_day')
        last_day_of_month = calendar.monthrange(check_date.year, check_date.month)[1]

        if day_of_month <= last_day_of_month:
            # Day exists in this month
            return check_date.day == day_of_month
        else:
            # Day doesn't exist in this month (e.g., 31st in February)
            if month_fallback == 'last_day':
                # Trigger on last day of month
                return check_date.day == last_day_of_month
            else:  # 'skip'
                # Don't trigger this month
                return False

    return False


def get_frequency_description(reminder: dict) -> str:
    """Get human-readable description of reminder frequency."""
    frequency = reminder.get('frequency', 'daily')

    if frequency == 'daily':
        daily_mode = reminder.get('daily_mode', 'simple')
        if daily_mode == 'advanced':
            return 'Ежедневно (расширенный)'
        return 'Ежедневно'

    elif frequency == 'weekly':
        day_of_week = reminder.get('day_of_week', 0)
        days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
        return f'Еженедельно ({days[day_of_week]})'

    elif frequency == 'monthly':
        day_of_month = reminder.get('day_of_month', 1)
        month_fallback = reminder.get('month_fallback', 'last_day')
        fallback_text = 'последний день' if month_fallback == 'last_day' else 'пропустить'
        return f'Ежемесячно ({day_of_month}-е число, иначе {fallback_text})'

    return frequency


# --- Функции для работы со статусом работы в выходные ---

async def get_weekend_work_status(reminder_id: int, target_date: date) -> Optional[dict]:
    """Get weekend work status for a specific date."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            'SELECT * FROM weekend_work_status WHERE reminder_id = ? AND target_date = ?',
            (reminder_id, target_date.isoformat())
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def set_weekend_work_status(
    user_id: int,
    reminder_id: int,
    target_date: date,
    has_work: bool
) -> dict:
    """Set weekend work status for a specific date."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            'SELECT * FROM weekend_work_status WHERE reminder_id = ? AND target_date = ?',
            (reminder_id, target_date.isoformat())
        )
        existing = await cursor.fetchone()

        if existing:
            await db.execute('''
                UPDATE weekend_work_status
                SET has_work = ?, responded = 1
                WHERE reminder_id = ? AND target_date = ?
            ''', (int(has_work), reminder_id, target_date.isoformat()))
        else:
            await db.execute('''
                INSERT INTO weekend_work_status
                (user_id, reminder_id, target_date, has_work, asked_at, responded)
                VALUES (?, ?, ?, ?, ?, 1)
            ''', (user_id, reminder_id, target_date.isoformat(),
                  int(has_work), datetime.utcnow().isoformat()))

        await db.commit()

        cursor = await db.execute(
            'SELECT * FROM weekend_work_status WHERE reminder_id = ? AND target_date = ?',
            (reminder_id, target_date.isoformat())
        )
        row = await cursor.fetchone()
        return dict(row)


async def create_work_question(user_id: int, reminder_id: int, target_date: date) -> dict:
    """Create a pending work question for a weekend day."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            'SELECT * FROM weekend_work_status WHERE reminder_id = ? AND target_date = ?',
            (reminder_id, target_date.isoformat())
        )
        existing = await cursor.fetchone()

        if not existing:
            await db.execute('''
                INSERT INTO weekend_work_status
                (user_id, reminder_id, target_date, asked_at, responded)
                VALUES (?, ?, ?, ?, 0)
            ''', (user_id, reminder_id, target_date.isoformat(),
                  datetime.utcnow().isoformat()))
            await db.commit()

        cursor = await db.execute(
            'SELECT * FROM weekend_work_status WHERE reminder_id = ? AND target_date = ?',
            (reminder_id, target_date.isoformat())
        )
        row = await cursor.fetchone()
        return dict(row)


async def get_pending_work_questions(user_id: int) -> list:
    """Get all pending (unanswered) work questions for a user."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT wws.*, r.time, r.weekend_time_no_work, r.weekend_time_with_work
            FROM weekend_work_status wws
            JOIN reminders r ON wws.reminder_id = r.id
            WHERE wws.user_id = ? AND wws.responded = 0 AND r.active = 1
            ORDER BY wws.target_date
        ''', (user_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_advanced_daily_reminders_needing_questions() -> list:
    """Get all advanced daily reminders that need work questions asked."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT r.*, u.timezone
            FROM reminders r
            JOIN users u ON r.user_id = u.user_id
            WHERE r.active = 1
              AND r.frequency = 'daily'
              AND r.daily_mode = 'advanced'
              AND r.weekend_override = 1
        ''')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


def get_reminder_time_for_date(reminder: dict, check_date: date, has_work: Optional[bool] = None) -> Optional[str]:
    """
    Get the appropriate reminder time for a specific date based on reminder settings.

    Args:
        reminder: Reminder dict with all settings
        check_date: Date to check
        has_work: Whether user has work on this day (for weekends)

    Returns:
        Time string (HH:MM) or None if reminder shouldn't trigger
    """
    frequency = reminder.get('frequency', 'daily')

    if frequency != 'daily':
        return reminder.get('time')

    daily_mode = reminder.get('daily_mode', 'simple')

    if daily_mode == 'simple':
        return reminder.get('time')

    # Advanced daily mode
    is_weekend = check_date.weekday() >= 5  # Saturday=5, Sunday=6
    weekend_override = reminder.get('weekend_override', 0)

    if is_weekend and weekend_override:
        # Weekend with special settings
        if has_work is None:
            # Work status unknown - will need to use default or ask
            return reminder.get('weekend_time_no_work') or reminder.get('time')
        elif has_work:
            return reminder.get('weekend_time_with_work') or reminder.get('time')
        else:
            return reminder.get('weekend_time_no_work') or reminder.get('time')
    else:
        # Regular weekday - use even/odd logic
        day_of_month = check_date.day
        if day_of_month % 2 == 0:  # Even day
            return reminder.get('even_day_time') or reminder.get('time')
        else:  # Odd day
            return reminder.get('odd_day_time') or reminder.get('time')
