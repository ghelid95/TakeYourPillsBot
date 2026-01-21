import aiosqlite
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
                active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
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


async def add_reminder(user_id: int, time: str) -> int:
    """Add a new reminder for a user. Returns reminder ID."""
    await get_or_create_user(user_id)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute(
            'INSERT INTO reminders (user_id, time) VALUES (?, ?)',
            (user_id, time)
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
