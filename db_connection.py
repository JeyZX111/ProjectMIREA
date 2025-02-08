import sqlite3
from contextlib import contextmanager
import os
from datetime import datetime
from typing import Optional
import aiosqlite
import asyncio
import logging
from database import DATABASE_PATH

DATABASE_PATH = DATABASE_PATH

async def init_db():
    """Инициализация базы данных и создание таблиц"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS cars (
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
                CREATE TABLE IF NOT EXISTS pending_cars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    brand TEXT NOT NULL,
                    model TEXT NOT NULL,
                    year INTEGER NOT NULL,
                    admin_comment TEXT,
                    submitted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS diagnostics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    car_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    mileage INTEGER,
                    description TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (car_id) REFERENCES cars (id)
                )
            ''')

            await db.execute('''
                CREATE TABLE IF NOT EXISTS moderation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    car_id INTEGER NOT NULL,
                    admin_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (car_id) REFERENCES pending_cars (id),
                    FOREIGN KEY (admin_id) REFERENCES admins (id)
                )
            ''')
            
            await db.commit()
    except Exception as e:
        logging.error(f"Error initializing database: {e}")

async def add_admin(user_id: int, username: str = None):
    """Добавить нового администратора"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            'INSERT INTO admins (user_id, username, added_at) VALUES (?, ?, ?)',
            (user_id, username, datetime.now().isoformat())
        )
        await db.commit()

async def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            'SELECT 1 FROM admins WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

async def add_pending_car(user_id: int, brand: str, model: str, year: int, admin_comment: Optional[str] = None):
    """Добавить автомобиль в список ожидающих проверки"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            '''INSERT INTO pending_cars 
               (user_id, brand, model, year, admin_comment, submitted_at) 
               VALUES (?, ?, ?, ?, ?, ?)''',
            (user_id, brand, model, year, admin_comment, datetime.now().isoformat())
        )
        await db.commit()

async def get_pending_cars():
    """Получить список автомобилей, ожидающих проверки"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM pending_cars ORDER BY submitted_at DESC'
        ) as cursor:
            return await cursor.fetchall()

async def approve_car(pending_car_id: int, admin_id: int):
    """Одобрить ожидающий автомобиль"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            # Получаем информацию о машине
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM pending_cars WHERE id = ?',
                (pending_car_id,)
            ) as cursor:
                car = await cursor.fetchone()
                
            if not car:
                raise ValueError(f"Автомобиль с ID {pending_car_id} не найден")

            # Добавляем машину в основную таблицу
            await db.execute(
                '''INSERT INTO cars 
                   (brand, model, year, user_id, approved_by, approved_at)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (car['brand'], car['model'], car['year'], car['user_id'],
                 admin_id, datetime.now().isoformat())
            )

            # Добавляем запись в историю модерации
            await db.execute(
                '''INSERT INTO moderation_history 
                   (car_id, admin_id, action, created_at)
                   VALUES (?, ?, ?, ?)''',
                (pending_car_id, admin_id, 'approve', datetime.now().isoformat())
            )

            # Удаляем из списка ожидающих
            await db.execute(
                'DELETE FROM pending_cars WHERE id = ?',
                (pending_car_id,)
            )

            # Фиксируем все изменения
            await db.commit()

            # Возвращаем информацию о пользователе для уведомления
            return car['user_id']

        except Exception as e:
            # В случае ошибки откатываем изменения
            await db.rollback()
            raise e

async def reject_car(pending_car_id: int, admin_id: int, reason: str):
    """Отклонить ожидающий автомобиль"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Получаем информацию о машине для уведомления
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT user_id FROM pending_cars WHERE id = ?',
            (pending_car_id,)
        ) as cursor:
            car = await cursor.fetchone()
            if not car:
                raise ValueError("Автомобиль не найден")

        # Добавляем запись в историю модерации
        await db.execute(
            '''INSERT INTO moderation_history 
               (car_id, admin_id, action, reason, created_at)
               VALUES (?, ?, ?, ?, ?)''',
            (pending_car_id, admin_id, 'reject', reason, datetime.now().isoformat())
        )

        # Удаляем из списка ожидающих
        await db.execute(
            'DELETE FROM pending_cars WHERE id = ?',
            (pending_car_id,)
        )

        # Фиксируем все изменения
        await db.commit()

        # Возвращаем информацию о пользователе для уведомления
        return car['user_id']

async def add_moderation_history(car_id: int, admin_id: int, action: str, reason: str = None):
    """Добавить запись в историю модерации"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            INSERT INTO moderation_history (car_id, admin_id, action, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (car_id, admin_id, action, reason, datetime.now().isoformat()))
        await db.commit()

async def get_moderation_history(car_id: int = None):
    """Получить историю модерации для конкретного автомобиля или всю историю"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = '''
            SELECT 
                mh.*,
                pc.brand,
                pc.model,
                pc.year,
                a.username as admin_name
            FROM moderation_history mh
            JOIN pending_cars pc ON mh.car_id = pc.id
            JOIN admins a ON mh.admin_id = a.id
        '''
        params = []
        if car_id:
            query += ' WHERE mh.car_id = ?'
            params.append(car_id)
        query += ' ORDER BY mh.created_at DESC'
        
        async with db.execute(query, params) as cursor:
            return await cursor.fetchall()

async def get_moderation_stats():
    """Получить статистику модерации"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT 
                a.admin_name,
                COUNT(CASE WHEN mh.action = 'approve' THEN 1 END) as approvals,
                COUNT(CASE WHEN mh.action = 'reject' THEN 1 END) as rejections,
                COUNT(*) as total_actions
            FROM moderation_history mh
            JOIN admins a ON mh.admin_id = a.id
            GROUP BY a.id, a.admin_name
            ORDER BY total_actions DESC
        ''') as cursor:
            return await cursor.fetchall()

async def get_all_cars():
    """Получить список всех одобренных автомобилей"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM cars ORDER BY created_at DESC') as cursor:
            return await cursor.fetchall()

async def get_user_cars(user_id: int):
    """Получить список всех одобренных автомобилей пользователя"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM cars WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        ) as cursor:
            return await cursor.fetchall()

async def get_car_diagnostics(car_id: int):
    """Получить историю диагностики автомобиля"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT * FROM diagnostics WHERE car_id = ? ORDER BY date DESC',
            (car_id,)
        ) as cursor:
            return await cursor.fetchall()

async def add_car(brand: str, model: str, year: int, vin: str = None):
    """Добавить новый автомобиль в базу данных"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            INSERT INTO cars (brand, model, year, vin)
            VALUES (?, ?, ?, ?)
        ''', (brand, model, year, vin))
        await db.commit()
        return db.lastrowid

async def add_diagnostic(car_id: int, date: str, mileage: int, description: str):
    """Добавить запись о диагностике"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute('''
            INSERT INTO diagnostics (car_id, date, mileage, description)
            VALUES (?, ?, ?, ?)
        ''', (car_id, date, mileage, description))
        await db.commit()
        return db.lastrowid

async def get_car_by_id(car_id: int):
    """Получить информацию об автомобиле по ID"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM cars WHERE id = ?', (car_id,)) as cursor:
            return await cursor.fetchone()

async def get_all_cars():
    """Получить список всех автомобилей"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM cars') as cursor:
            return await cursor.fetchall()

async def get_all_admins():
    """Получить список всех администраторов"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM admins') as cursor:
            return await cursor.fetchall()

# Пример использования:
if __name__ == "__main__":
    asyncio.run(init_db())
    # Добавляем тестовый автомобиль
    asyncio.run(add_car("Toyota", "Camry", 2020, "ABC123456789"))
    # Добавляем тестовую запись о диагностике
    asyncio.run(add_diagnostic(1, "2025-01-14", 50000, "Плановое ТО"))
    # Получаем список всех автомобилей
    cars = asyncio.run(get_all_cars())
    print("Список всех автомобилей:", cars)
