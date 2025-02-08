import os
import aiosqlite

DATABASE_DIR = 'database'
DATABASE_PATH = os.path.join(DATABASE_DIR, 'bot.db')

async def create_database():
    """Создает базу данных и все необходимые таблицы"""
    # Create database directory if it doesn't exist
    if not os.path.exists(DATABASE_DIR):
        os.makedirs(DATABASE_DIR)
    
    # Connect to database
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Drop existing tables if they exist
        await db.execute('DROP TABLE IF EXISTS diagnostics')
        await db.execute('DROP TABLE IF EXISTS cars')
        await db.execute('DROP TABLE IF EXISTS pending_cars')
        await db.execute('DROP TABLE IF EXISTS admins')
        await db.execute('DROP TABLE IF EXISTS moderation_history')
        
        # Create tables
        await db.execute('''
            CREATE TABLE admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                added_at TEXT NOT NULL
            )
        ''')
        
        await db.execute('''
            CREATE TABLE cars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                year INTEGER,
                vin TEXT UNIQUE,
                user_id INTEGER NOT NULL,
                approved_by INTEGER,
                approved_at TEXT,
                FOREIGN KEY (approved_by) REFERENCES admins (id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE pending_cars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                model TEXT NOT NULL,
                year INTEGER,
                vin TEXT UNIQUE,
                user_id INTEGER NOT NULL,
                submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                admin_comment TEXT
            )
        ''')
        
        await db.execute('''
            CREATE TABLE diagnostics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER,
                date TEXT NOT NULL,
                mileage INTEGER,
                description TEXT,
                FOREIGN KEY (car_id) REFERENCES cars (id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE moderation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_id INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL CHECK(action IN ('approve', 'reject')),
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (car_id) REFERENCES pending_cars (id),
                FOREIGN KEY (admin_id) REFERENCES admins (id)
            )
        ''')
        
        # Add indexes
        await db.execute('CREATE INDEX IF NOT EXISTS idx_cars_user_id ON cars(user_id)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_pending_cars_user_id ON pending_cars(user_id)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_pending_cars_status ON pending_cars(status)')
        
        await db.commit()

if __name__ == "__main__":
    import asyncio
    asyncio.run(create_database())
