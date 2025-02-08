import logging
import json
import aiohttp
import ssl
from typing import Optional, Dict, Any, Tuple
from datetime import datetime

class AIHelper:
    def __init__(self):
        """Инициализация помощника с AI"""
        # API ключ Gemini
        self.api_key = 'AIzaSyDOTXy-gLb9oh9QQKCMTHitQLTaPnqSNLE'
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"
        
        # Конфигурация для генерации текста
        self.generation_config = {
            "temperature": 0.7,
            "topP": 0.8,
            "topK": 40,
            "maxOutputTokens": 1024,
        }
        
        # Параметры безопасности
        self.safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_MEDIUM_AND_ABOVE"
            }
        ]
        
        # Базовый промпт для автомобильных вопросов
        self.base_prompt = """Ты - опытный автомеханик и эксперт по автомобилям с более чем 20-летним опытом работы. 
Твоя задача - помогать пользователям с диагностикой и решением автомобильных проблем.

При ответе на вопросы следуй этим правилам:
1. Всегда учитывай марку, модель и год выпуска автомобиля
2. Давай конкретные рекомендации, основанные на особенностях модели
3. Указывай возможные причины проблемы в порядке вероятности
4. Если проблема серьезная, рекомендуй обратиться к специалисту
5. Используй технически корректную терминологию, но объясняй её простым языком

Классификация проблем по категориям:

1. ДВИГАТЕЛЬ И ТОПЛИВНАЯ СИСТЕМА:
- Запуск двигателя
- Холостой ход
- Потеря мощности
- Расход топлива
- Выхлопные газы
- Стуки и шумы двигателя

2. ТРАНСМИССИЯ:
- МКПП/АКПП
- Сцепление
- Приводы
- Раздаточная коробка
- Дифференциал

3. ПОДВЕСКА И УПРАВЛЕНИЕ:
- Амортизаторы
- Пружины/рессоры
- Рулевое управление
- Стабилизаторы
- Сайлентблоки/втулки
- Шаровые опоры
- Ступичные подшипники

4. ТОРМОЗНАЯ СИСТЕМА:
- Тормозные диски/колодки
- Тормозная жидкость
- ABS/ESP/TCS
- Стояночный тормоз
- Вакуумный усилитель

5. ЭЛЕКТРИКА И ЭЛЕКТРОНИКА:
- Аккумулятор
- Генератор
- Стартер
- Датчики
- Электронные блоки управления
- Освещение
- Предохранители

6. КУЗОВ И КОМФОРТ:
- Кондиционер
- Отопитель
- Замки и стеклоподъемники
- Шумоизоляция
- Протечки
- Коррозия

7. ПЛАНОВОЕ ОБСЛУЖИВАНИЕ:
- Замена масла и фильтров
- Регулировка клапанов
- Замена ремней и цепей
- Диагностика
- Сезонное обслуживание

Для каждой проблемы указывай:
1. Категорию проблемы
2. Возможные причины
3. Степень серьезности (низкая/средняя/высокая)
4. Приблизительную стоимость ремонта
5. Можно ли продолжать эксплуатацию
6. Рекомендации по устранению

Особые указания:
- Если вопрос касается безопасности, всегда рекомендуй обратиться к профессиональному механику
- Учитывай особенности конкретной модели и года выпуска
- Если есть типичные проблемы для данной модели - упомяни их
- При ответе используй техническую терминологию, но объясняй её простым языком
- Если вопрос не связан с автомобилями, вежливо напомни, что ты специализируешься только на автомобильной тематике"""

    async def _make_gemini_request(self, prompt: str) -> Optional[str]:
        """Отправляет запрос к Gemini API и возвращает ответ"""
        try:
            # Подготавливаем данные для запроса
            request_data = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }],
                "generationConfig": self.generation_config,
                "safetySettings": self.safety_settings
            }
            
            # Создаем SSL контекст без проверки сертификата
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Отправляем запрос
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}?key={self.api_key}",
                    json=request_data,
                    ssl=ssl_context
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        if result.get("candidates") and result["candidates"][0].get("content"):
                            return result["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        error_text = await response.text()
                        logging.error(f"Gemini API Error: {error_text}")
            return None
            
        except Exception as e:
            logging.error(f"Error in Gemini API request: {e}")
            return None

    async def get_gemini_response(self, question: str) -> str:
        """Получить ответ от Gemini на вопрос пользователя"""
        try:
            # Формируем полный промпт с вопросом пользователя
            full_prompt = f"{self.base_prompt}\n\nВопрос пользователя: {question}\n\nТвой профессиональный ответ:"
            
            # Отправляем запрос к API
            response = await self._make_gemini_request(full_prompt)
            
            if response:
                return response
            return "Извините, произошла ошибка при обработке вашего вопроса. Попробуйте позже."
            
        except Exception as e:
            logging.error(f"Error in get_gemini_response: {e}")
            return "Извините, произошла ошибка при обработке вашего вопроса. Попробуйте позже."

    async def check_car_details(self, brand: str, model: str, year: int) -> Tuple[bool, str]:
        """
        Проверяет валидность данных автомобиля через AI
        Возвращает (is_valid, reason)
        """
        prompt = f"""Проверь, существует ли автомобиль с такими характеристиками:
Марка: {brand}
Модель: {model}
Год выпуска: {year}

Проверь следующее:
1. Существует ли такая марка автомобиля
2. Существует ли такая модель у этой марки
3. Выпускалась ли эта модель в указанном году

Отвечай строго в формате:
VALID: да
или
VALID: нет

REASON: причина (укажи причину в любом случае)"""

        try:
            # Отправляем запрос к API
            response = await self._make_gemini_request(prompt)
            
            if response:
                # Парсим ответ
                lines = [line.strip() for line in response.strip().split('\n') if line.strip()]
                
                # Проверяем валидность
                valid_line = next((line for line in lines if line.lower().startswith('valid:')), None)
                reason_line = next((line for line in lines if line.lower().startswith('reason:')), None)
                
                if valid_line and reason_line:
                    is_valid = 'да' in valid_line.lower()
                    reason = reason_line.split(':', 1)[1].strip()
                    
                    if is_valid:
                        return True, "Автомобиль успешно проверен"
                    else:
                        return False, reason
                
            return False, "Ошибка при проверке данных автомобиля. Пожалуйста, попробуйте еще раз."
            
        except Exception as e:
            logging.error(f"Error checking car details: {e}")
            return False, "Произошла ошибка при проверке данных. Пожалуйста, попробуйте еще раз."

async def test_api():
    """Тестирование подключения к API"""
    helper = AIHelper()
    try:
        result = await helper.check_car_details("Toyota", "Camry", 2020)
        print(f"Test result: {result}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_api())
