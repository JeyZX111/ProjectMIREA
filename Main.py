import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from datetime import datetime
import json
import os
import aiosqlite
from ai_helper import AIHelper
from database import create_database, DATABASE_PATH
from db_connection import (
    get_all_cars, add_car, get_car_diagnostics,
    is_admin, add_admin, get_pending_cars, approve_car, reject_car,
    add_pending_car, init_db, get_moderation_stats, get_moderation_history,
    get_all_admins
)
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, BotCommand,
    ReplyKeyboardMarkup, KeyboardButton
)
from validators import is_valid_brand, is_valid_model
import asyncio

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Создаем экземпляр AI помощника
ai_helper = AIHelper()

# Токен бота
BOT_TOKEN = "7279537099:AAHjMze0OJ40O8K12RAC7xqXEXnu9iqz1_A"

# Создаем объекты бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Emoji для статусов
EMOJI_PENDING = "⏳"
EMOJI_APPROVED = "✅"
EMOJI_WARNING = "⚠️"
EMOJI_QUESTION = "❓"
EMOJI_TOOLS = "🔧"
EMOJI_CAR = "🚗"
EMOJI_REJECTED = "❌"
EMOJI_ADMIN = "👑"
EMOJI_PLUS = "➕"
EMOJI_MENU = "📚"
EMOJI_APPROVE = "✅"
EMOJI_REJECT = "❌"

async def get_cars_from_db():
    """Получить список всех автомобилей из базы данных"""
    try:
        return await get_all_cars()
    except Exception as e:
        logging.error(f"Error getting cars from DB: {e}")
        return []

# Класс для хранения состояний диалога добавления автомобиля
class CarForm(StatesGroup):
    waiting_for_brand = State()
    waiting_for_model = State()
    waiting_for_year = State()

class QuestionForm(StatesGroup):
    waiting_for_car = State()
    waiting_for_category = State()
    waiting_for_question = State()

class ModerationForm(StatesGroup):
    waiting_for_reject_reason = State()

# Категории проблем
PROBLEM_CATEGORIES = {
    "1": "ДВИГАТЕЛЬ И ТОПЛИВНАЯ СИСТЕМА",
    "2": "ТРАНСМИССИЯ",
    "3": "ПОДВЕСКА И УПРАВЛЕНИЕ",
    "4": "ТОРМОЗНАЯ СИСТЕМА",
    "5": "ЭЛЕКТРИКА И ЭЛЕКТРОНИКА",
    "6": "КУЗОВ И КОМФОРТ",
    "7": "ПЛАНОВОЕ ОБСЛУЖИВАНИЕ"
}

# Функция для создания клавиатуры главного меню
async def get_main_menu_keyboard() -> types.ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=f"{EMOJI_CAR} Мои автомобили"))
    builder.add(types.KeyboardButton(text=f"{EMOJI_QUESTION} Задать вопрос"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# Хэндлеры команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    logger.info(f"Команда /start от пользователя {message.from_user.id}")
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=f"{EMOJI_CAR} Мои автомобили"))
    builder.add(types.KeyboardButton(text=f"{EMOJI_QUESTION} Задать вопрос"))
    builder.adjust(2)
    
    await message.answer(
        "Привет! Я бот для диагностики автомобилей. Чтобы начать, добавьте свой автомобиль.",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    logger.info(f"Команда /help от пользователя {message.from_user.id}")
    help_text = (
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/add_car - Добавить автомобиль\n"
        "/help - Показать это сообщение\n"
    )
    if await is_admin(message.from_user.id):
        help_text += (
            "\nКоманды администратора:\n"
            "/add_admin - Добавить администратора\n"
            "/pending_cars - Просмотр ожидающих проверки автомобилей\n"
            "/moderation_stats - Статистика модерации\n"
            "/moderation_history - История модерации"
        )
    await message.answer(help_text)

@dp.message(Command("add_car"))
async def cmd_add_car(message: types.Message, state: FSMContext):
    logger.info(f"Команда /add_car от пользователя {message.from_user.id}")
    await state.set_state(CarForm.waiting_for_brand)
    await message.answer("Введите марку автомобиля:")

@dp.message(Command("add_admin"))
async def cmd_add_admin(message: types.Message):
    logger.info(f"Команда /add_admin от пользователя {message.from_user.id}")
    try:
        # Проверяем, есть ли уже администраторы
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute('SELECT COUNT(*) FROM admins') as cursor:
                admin_count = (await cursor.fetchone())[0]
                logger.info(f"Текущее количество администраторов: {admin_count}")
        
        # Если администраторов нет, первый использующий команду становится админом
        if admin_count == 0:
            logger.info(f"Добавление первого администратора: {message.from_user.id}")
            await add_admin(message.from_user.id, message.from_user.username)
            await message.answer(f"Вы успешно добавлены как первый администратор.")
            return
        
        # Если администраторы уже есть, проверяем права
        is_user_admin = await is_admin(message.from_user.id)
        logger.info(f"Пользователь {message.from_user.id} является администратором: {is_user_admin}")
        
        if not is_user_admin:
            logger.info("Отказано в доступе: пользователь не является администратором")
            await message.answer("У вас нет прав для выполнения этой команды.")
            return
        
        # Проверяем, был ли указан ID нового администратора
        args = message.text.split()
        if len(args) != 2:
            logger.info("Неверный формат команды")
            await message.answer("Использование: /add_admin <user_id>")
            return
        
        try:
            new_admin_id = int(args[1])
            # Проверяем, не является ли пользователь уже администратором
            if await is_admin(new_admin_id):
                logger.info(f"Пользователь {new_admin_id} уже является администратором")
                await message.answer("Этот пользователь уже является администратором.")
                return
                
            logger.info(f"Добавление нового администратора: {new_admin_id}")
            await add_admin(new_admin_id, None)  # Добавляем без username, так как мы его не знаем
            await message.answer(f"Пользователь {new_admin_id} успешно добавлен как администратор.")
        except ValueError:
            logger.error("Ошибка: ID пользователя не является числом")
            await message.answer("ID пользователя должен быть числом.")
            
    except Exception as e:
        logger.error(f"Ошибка в команде add_admin: {e}", exc_info=True)
        await message.answer("Произошла ошибка при добавлении администратора. Попробуйте позже.")

@dp.message(Command("pending_cars"))
async def cmd_pending_cars(message: types.Message):
    logger.info(f"Команда /pending_cars от пользователя {message.from_user.id}")
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    pending_cars = await get_pending_cars()
    if not pending_cars:
        await message.answer("Нет автомобилей, ожидающих одобрения.")
        return

    for car in pending_cars:
        # Создаем инлайн-клавиатуру для каждого автомобиля
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{EMOJI_APPROVED} Одобрить",
                    callback_data=f"approve_{car['id']}"
                ),
                InlineKeyboardButton(
                    text=f"{EMOJI_WARNING} Отклонить",
                    callback_data=f"reject_{car['id']}"
                )
            ]
        ])
        
        await message.answer(
            f"🆔 ID: {car['id']}\n"
            f"👤 Пользователь: {car['user_id']}\n"
            f"🚗 Автомобиль: {car['brand']} {car['model']} ({car['year']})",
            reply_markup=keyboard
        )

@dp.message(Command("moderation_stats"))
async def cmd_moderation_stats(message: types.Message):
    logger.info(f"Команда /moderation_stats от пользователя {message.from_user.id}")
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    stats = await get_moderation_stats()
    if not stats:
        await message.answer("Статистика модерации пуста.")
        return

    response = "📊 Статистика модерации:\n\n"
    response += f"✅ Одобрено: {stats['approved']}\n"
    response += f"❌ Отклонено: {stats['rejected']}\n"
    response += f"⏳ Ожидает проверки: {stats['pending']}\n"
    
    await message.answer(response)

@dp.message(Command("moderation_history"))
async def cmd_moderation_history(message: types.Message):
    logger.info(f"Команда /moderation_history от пользователя {message.from_user.id}")
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    history = await get_moderation_history()
    if not history:
        await message.answer("История модерации пуста.")
        return

    response = "📋 История модерации:\n\n"
    for record in history[:10]:  # Показываем только последние 10 записей
        action_emoji = "✅" if record['action'] == 'approve' else "❌"
        response += (f"{action_emoji} {record['brand']} {record['model']} ({record['year']})\n"
                    f"👤 Модератор: {record['admin_name']}\n"
                    f"📅 Дата: {record['created_at']}\n")
        if record['reason']:
            response += f"📝 Причина: {record['reason']}\n"
        response += "\n"

    await message.answer(response)

# Обработчик текстовых сообщений (кнопки меню и состояния)
@dp.message(F.text)
async def handle_text(message: types.Message, state: FSMContext):
    logger.info(f"Текстовое сообщение: {message.text} от пользователя {message.from_user.id}")
    
    # Проверяем текущее состояние
    current_state = await state.get_state()
    logger.info(f"Текущее состояние: {current_state}")
    
    if current_state is not None:
        # Если есть активное состояние, передаем управление соответствующему обработчику
        if current_state == CarForm.waiting_for_brand:
            await process_brand(message, state)
        elif current_state == CarForm.waiting_for_model:
            await process_model(message, state)
        elif current_state == CarForm.waiting_for_year:
            await process_year(message, state)
        elif current_state == QuestionForm.waiting_for_car:
            await process_car_selection(message, state)
        elif current_state == QuestionForm.waiting_for_category:
            await process_category_selection(message, state)
        elif current_state == QuestionForm.waiting_for_question:
            await process_question(message, state)
        elif current_state == ModerationForm.waiting_for_reject_reason:
            await process_reject_reason(message, state)
        return
    
    # Если нет активного состояния, обрабатываем кнопки меню
    if message.text == f"{EMOJI_CAR} Мои автомобили":
        await show_cars(message)
    elif message.text == f"{EMOJI_QUESTION} Задать вопрос":
        await ask_question(message, state)
    elif message.text == f"{EMOJI_PLUS} Добавить автомобиль":
        await cmd_add_car(message, state)
    else:
        # Если не команда и не кнопка меню, показываем подсказку
        builder = ReplyKeyboardBuilder()
        builder.add(types.KeyboardButton(text=f"{EMOJI_CAR} Мои автомобили"))
        builder.add(types.KeyboardButton(text=f"{EMOJI_QUESTION} Задать вопрос"))
        builder.adjust(2)
        
        await message.answer(
            "Пожалуйста, используйте кнопки меню или команды. Для списка команд введите /help",
            reply_markup=builder.as_markup(resize_keyboard=True)
        )

# Обработка ввода марки автомобиля
@dp.message(CarForm.waiting_for_brand)
async def process_brand(message: types.Message, state: FSMContext):
    logger.info(f"Обработка марки автомобиля: {message.text}")
    await state.update_data(brand=message.text)
    await state.set_state(CarForm.waiting_for_model)
    await message.answer("Теперь введите модель автомобиля:")

# Обработка ввода модели автомобиля
@dp.message(CarForm.waiting_for_model)
async def process_model(message: types.Message, state: FSMContext):
    logger.info(f"Обработка модели автомобиля: {message.text}")
    await state.update_data(model=message.text)
    await state.set_state(CarForm.waiting_for_year)
    await message.answer("Введите год выпуска автомобиля:")

# Обработка ввода года выпуска
@dp.message(CarForm.waiting_for_year)
async def process_year(message: types.Message, state: FSMContext):
    logger.info(f"Обработка года выпуска: {message.text}")
    try:
        year = int(message.text)
        current_year = datetime.now().year
        
        if year < 1900 or year > current_year:
            logger.warning(f"Некорректный год: {year}")
            await message.answer(f"Пожалуйста, введите корректный год от 1900 до {current_year}")
            return

        user_data = await state.get_data()
        brand = user_data['brand']
        model = user_data['model']
        
        logger.info(f"Добавление автомобиля: {brand} {model} {year}")
        
        try:
            # Добавляем автомобиль в список ожидающих проверки
            await add_pending_car(
                user_id=message.from_user.id,
                brand=brand,
                model=model,
                year=year
            )
            logger.info("Автомобиль успешно добавлен в список ожидающих проверки")
            
            # Отправляем сообщение пользователю
            await message.answer(
                "✅ Ваш автомобиль добавлен в список ожидающих проверки.\n"
                "Администратор проверит данные и подтвердит добавление автомобиля."
            )
            
            # Уведомляем администраторов о новом автомобиле
            admins = await get_all_admins()
            logger.info(f"Отправка уведомлений администраторам: {admins}")
            
            for admin in admins:
                try:
                    admin_id = admin['user_id']
                    logger.info(f"Отправка уведомления администратору {admin_id}")
                    await bot.send_message(
                        admin_id,
                        f"🚗 Новый автомобиль ожидает проверки:\n"
                        f"Марка: {brand}\n"
                        f"Модель: {model}\n"
                        f"Год: {year}\n"
                        f"От пользователя: {message.from_user.id}\n\n"
                        f"Используйте /pending_cars для просмотра"
                    )
                except Exception as e:
                    logger.error(f"Ошибка при отправке уведомления администратору {admin_id}: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка при добавлении автомобиля: {e}", exc_info=True)
            await message.answer(
                "❌ Ошибка при добавлении автомобиля. Пожалуйста, попробуйте позже."
            )
            return
        finally:
            await state.clear()
            
    except ValueError:
        logger.warning(f"Некорректный формат года: {message.text}")
        await message.answer("Пожалуйста, введите год в виде числа (например, 2020)")
        return

# Функция для проверки выбранного автомобиля
async def check_car_selection(message: types.Message) -> bool:
    cars = await get_cars_from_db()
    return any(
        f"{car['brand']} {car['model']} ({car['year']})" == message.text
        for car in cars
    )

# Хэндлер на кнопку "Мои автомобили"
@dp.message(F.text == f"{EMOJI_CAR} Мои автомобили")
async def show_cars(message: types.Message):
    # Получаем список автомобилей
    cars = await get_cars_from_db()
    
    # Создаем клавиатуру
    builder = ReplyKeyboardBuilder()
    
    # Добавляем автомобили, если они есть
    if cars:
        for car in cars:
            builder.add(types.KeyboardButton(text=f"{car['brand']} {car['model']} ({car['year']})"))
    
    # Добавляем кнопки управления
    builder.add(types.KeyboardButton(text=f"{EMOJI_PLUS} Добавить автомобиль"))
    builder.add(types.KeyboardButton(text=f"{EMOJI_MENU} Главное меню"))
    
    # Настраиваем расположение кнопок (по одной в строке)
    builder.adjust(1)

    if not cars:
        message_text = "У вас пока нет добавленных автомобилей. Нажмите 'Добавить автомобиль' чтобы начать."
    else:
        message_text = "Ваши автомобили:"

    await message.answer(
        message_text,
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# Обработчик кнопки "Добавить автомобиль" в меню автомобилей
@dp.message(F.text == f"{EMOJI_PLUS} Добавить автомобиль")
async def handle_add_car(message: types.Message, state: FSMContext):
    # Вызываем существующий обработчик добавления автомобиля
    await cmd_add_car(message, state)

# Хэндлер на кнопку "Задать вопрос"
@dp.message(F.text == f"{EMOJI_QUESTION} Задать вопрос")
async def ask_question(message: types.Message, state: FSMContext):
    # Получаем список автомобилей
    cars = await get_cars_from_db()
    
    # Создаем клавиатуру
    builder = ReplyKeyboardBuilder()
    
    # Добавляем автомобили, если они есть
    if cars:
        for car in cars:
            builder.add(types.KeyboardButton(text=f"{car['brand']} {car['model']} ({car['year']})"))
    
    # Добавляем кнопку добавления автомобиля и возврата в главное меню
    builder.add(types.KeyboardButton(text=f"{EMOJI_PLUS} Добавить автомобиль"))
    builder.add(types.KeyboardButton(text=f"{EMOJI_MENU} Главное меню"))
    
    # Настраиваем расположение кнопок (по одной в строке)
    builder.adjust(1)

    if not cars:
        message_text = "У вас пока нет добавленных автомобилей. Выберите 'Добавить автомобиль' чтобы начать."
    else:
        message_text = "Выберите автомобиль, о котором хотите задать вопрос:"

    await message.answer(
        message_text,
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.set_state(QuestionForm.waiting_for_car)

# Обработчик кнопки "Добавить автомобиль" в меню выбора
@dp.message(QuestionForm.waiting_for_car, F.text == f"{EMOJI_PLUS} Добавить автомобиль")
async def add_car_from_question(message: types.Message, state: FSMContext):
    # Сбрасываем текущее состояние вопроса
    await state.clear()
    # Вызываем существующий обработчик добавления автомобиля
    await cmd_add_car(message, state)

# Обработчик кнопки "Главное меню"
@dp.message(F.text == f"{EMOJI_MENU} Главное меню")
async def handle_main_menu(message: types.Message, state: FSMContext):
    # Сбрасываем текущее состояние
    await state.clear()
    
    await message.answer(
        "Вы вернулись в главное меню. Чем могу помочь?",
        reply_markup=await get_main_menu_keyboard()
    )

# Обработчик выбора автомобиля для вопроса
@dp.message(QuestionForm.waiting_for_car)
async def process_car_selection(message: types.Message, state: FSMContext):
    # Проверяем, существует ли такой автомобиль
    cars = await get_cars_from_db()
    selected_car = next(
        (car for car in cars if f"{car['brand']} {car['model']} ({car['year']})" == message.text),
        None
    )
    
    if not selected_car:
        await message.answer("Пожалуйста, выберите автомобиль из списка")
        return

    # Сохраняем выбранный автомобиль
    await state.update_data(selected_car=message.text)

    # Создаем клавиатуру с категориями проблем
    builder = ReplyKeyboardBuilder()
    for num, category in PROBLEM_CATEGORIES.items():
        builder.add(types.KeyboardButton(text=f"{num}. {category}"))
    builder.adjust(1)

    await message.answer(
        "Выберите категорию проблемы:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.set_state(QuestionForm.waiting_for_category)

# Обработчик выбора категории проблемы
@dp.message(QuestionForm.waiting_for_category)
async def process_category_selection(message: types.Message, state: FSMContext):
    # Проверяем, существует ли такая категория
    selected_category = None
    for num, category in PROBLEM_CATEGORIES.items():
        if message.text.startswith(f"{num}. "):
            selected_category = category
            break
    
    if not selected_category:
        await message.answer("Пожалуйста, выберите категорию из списка")
        return

    # Сохраняем выбранную категорию
    await state.update_data(selected_category=selected_category)

    # Создаем обычную клавиатуру
    builder = ReplyKeyboardBuilder()
    builder.add(types.KeyboardButton(text=f"{EMOJI_CAR} Мои автомобили"))
    builder.add(types.KeyboardButton(text=f"{EMOJI_QUESTION} Задать вопрос"))
    builder.adjust(2)
    
    await message.answer(
        "Теперь опишите вашу проблему подробно:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )
    await state.set_state(QuestionForm.waiting_for_question)

# Обработчик вопроса
@dp.message(QuestionForm.waiting_for_question)
async def process_question(message: types.Message, state: FSMContext):
    # Получаем сохраненные данные
    data = await state.get_data()
    selected_car = data.get('selected_car')
    selected_category = data.get('selected_category')

    # Формируем контекст вопроса
    question_context = f"Автомобиль: {selected_car}\nКатегория проблемы: {selected_category}\nВопрос: {message.text}"
    
    # Получаем ответ от AI
    response = await ai_helper.get_gemini_response(question_context)
    
    # Отправляем ответ пользователю
    await message.answer(response)
    
    # Сбрасываем состояние
    await state.clear()

    # Возвращаем главное меню
    await message.answer(
        "Чем еще могу помочь?",
        reply_markup=await get_main_menu_keyboard()
    )

# Обработчик кнопок одобрения/отклонения
@dp.callback_query(lambda c: c.data.startswith(('approve_', 'reject_')))
async def process_car_moderation(callback_query: types.CallbackQuery, state: FSMContext):
    logger.info(f"Обработка callback: {callback_query.data}")
    action, car_id = callback_query.data.split('_')
    car_id = int(car_id)

    try:
        if action == 'approve':
            logger.info(f"Одобрение автомобиля {car_id}")
            # Одобряем автомобиль
            user_id = await approve_car(car_id, callback_query.from_user.id)
            
            # Отправляем уведомление пользователю
            await bot.send_message(
                user_id,
                "✅ Ваш автомобиль успешно проверен и одобрен!\n"
                "Теперь вы можете задавать вопросы об этом автомобиле."
            )
            
            # Отвечаем на callback
            await callback_query.answer("Автомобиль одобрен")
            await callback_query.message.edit_text(
                callback_query.message.text + "\n\n✅ Одобрено"
            )
            
        elif action == 'reject':
            logger.info(f"Подготовка к отклонению автомобиля {car_id}")
            # Сохраняем информацию для последующего отклонения
            await state.set_state(ModerationForm.waiting_for_reject_reason)
            await state.update_data(car_id=car_id)
            
            # Просим указать причину отклонения
            await callback_query.message.reply(
                "Пожалуйста, укажите причину отклонения:"
            )
            await callback_query.answer()
            
    except Exception as e:
        logger.error(f"Ошибка при модерации автомобиля: {e}", exc_info=True)
        await callback_query.answer(
            "Произошла ошибка. Пожалуйста, попробуйте позже.",
            show_alert=True
        )

# Обработчик причины отклонения
@dp.message(ModerationForm.waiting_for_reject_reason)
async def process_reject_reason(message: types.Message, state: FSMContext):
    logger.info("Обработка причины отклонения")
    try:
        # Получаем сохраненный car_id
        data = await state.get_data()
        car_id = data['car_id']
        
        logger.info(f"Отклонение автомобиля {car_id} с причиной: {message.text}")
        
        # Отклоняем автомобиль
        user_id = await reject_car(car_id, message.from_user.id, message.text)
        
        # Отправляем уведомление пользователю
        await bot.send_message(
            user_id,
            f"❌ Ваш автомобиль не прошел проверку.\n"
            f"Причина: {message.text}\n\n"
            f"Вы можете добавить другой автомобиль с помощью команды /add_car"
        )
        
        # Подтверждаем модератору
        await message.answer("Автомобиль отклонен")
        
    except Exception as e:
        logger.error(f"Ошибка при отклонении автомобиля: {e}", exc_info=True)
        await message.answer(
            "Произошла ошибка при отклонении автомобиля. Пожалуйста, попробуйте позже."
        )
    finally:
        # Очищаем состояние в любом случае
        await state.clear()

async def update_pending_cars_message(message: types.Message):
    """Обновить сообщение со списком ожидающих проверки автомобилей"""
    pending_cars = await get_pending_cars()
    if not pending_cars:
        await message.answer("Нет автомобилей, ожидающих проверки.")
        return

    for car in pending_cars:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить",
                    callback_data=f"approve_{car['id']}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject_{car['id']}"
                )
            ]
        ])

        await message.answer(
            f"🚗 {car['brand']} {car['model']} ({car['year']})\n"
            f"👤 ID пользователя: {car['user_id']}\n"
            f"📅 Добавлен: {car['created_at']}",
            reply_markup=keyboard
        )

# Команда для просмотра статистики модерации (только для администраторов)
@dp.message(Command("moderation_stats"))
async def cmd_moderation_stats(message: types.Message):
    """Показать статистику модерации"""
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для просмотра статистики модерации.")
        return

    stats = await get_moderation_stats()
    if not stats:
        await message.answer("Статистика модерации пуста.")
        return

    response = "📊 Статистика модерации:\n\n"
    for stat in stats:
        response += (f"👤 {stat['admin_name']}:\n"
                    f"✅ Одобрено: {stat['approvals']}\n"
                    f"❌ Отклонено: {stat['rejections']}\n"
                    f"📝 Всего действий: {stat['total_actions']}\n\n")

    await message.answer(response)

# Команда для просмотра истории модерации (только для администраторов)
@dp.message(Command("moderation_history"))
async def cmd_moderation_history(message: types.Message):
    """Показать историю модерации"""
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для просмотра истории модерации.")
        return

    history = await get_moderation_history()
    if not history:
        await message.answer("История модерации пуста.")
        return

    response = "📋 История модерации:\n\n"
    for record in history[:10]:  # Показываем только последние 10 записей
        action_emoji = "✅" if record['action'] == 'approve' else "❌"
        response += (f"{action_emoji} {record['brand']} {record['model']} ({record['year']})\n"
                    f"👤 Модератор: {record['admin_name']}\n"
                    f"📅 Дата: {record['created_at']}\n")
        if record['reason']:
            response += f"📝 Причина: {record['reason']}\n"
        response += "\n"

    await message.answer(response)

async def set_commands(bot: Bot):
    """Установка команд бота"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Показать справку"),
        BotCommand(command="add_car", description="Добавить автомобиль"),
        BotCommand(command="add_admin", description="Добавить администратора (только для владельца)"),
        BotCommand(command="pending_cars", description="Просмотр автомобилей на проверке (для админов)")
    ]
    await bot.set_my_commands(commands)

async def main():
    # Создаем базу данных
    await create_database()
    
    # Устанавливаем команды бота
    await set_commands(bot)
    
    # Запускаем бота
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    # Запускаем бота
    asyncio.run(main())
