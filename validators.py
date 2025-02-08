import re

# Список популярных марок автомобилей
VALID_BRANDS = {
    'toyota', 'honda', 'ford', 'chevrolet', 'volkswagen', 'bmw', 'mercedes', 'audi',
    'hyundai', 'kia', 'nissan', 'mazda', 'subaru', 'lexus', 'volvo', 'porsche',
    'ferrari', 'lamborghini', 'tesla', 'jaguar', 'land rover', 'mini', 'fiat',
    'alfa romeo', 'bentley', 'bugatti', 'cadillac', 'chrysler', 'dodge', 'jeep',
    'lada', 'vaz', 'gaz', 'uaz', 'kamaz', 'skoda', 'seat', 'renault', 'peugeot',
    'citroen', 'opel', 'mitsubishi', 'suzuki', 'infiniti', 'acura', 'rolls-royce'
}

def is_valid_car_name(text: str) -> tuple[bool, str]:
    """
    Проверяет валидность названия автомобиля.
    Возвращает кортеж (is_valid, error_message).
    """
    # Приводим к нижнему регистру для проверки
    text = text.lower().strip()
    
    # Проверка на минимальную длину
    if len(text) < 2:
        return False, "Название слишком короткое"
    
    # Проверка на максимальную длину
    if len(text) > 50:
        return False, "Название слишком длинное"
    
    # Проверка на допустимые символы
    if not re.match(r'^[a-zA-Zа-яА-Я0-9\s\-]+$', text):
        return False, "Название содержит недопустимые символы"
    
    # Проверка на повторяющиеся символы
    if re.search(r'(.)\1{4,}', text):
        return False, "Название содержит слишком много повторяющихся символов"
    
    return True, ""

def is_valid_brand(brand: str) -> tuple[bool, str]:
    """
    Проверяет, является ли марка автомобиля допустимой.
    Возвращает кортеж (is_valid, error_message).
    """
    # Общая проверка на валидность названия
    is_valid, error = is_valid_car_name(brand)
    if not is_valid:
        return False, error
    
    # Проверка на наличие в списке допустимых марок
    if brand.lower().strip() not in VALID_BRANDS:
        return False, "Неизвестная марка автомобиля"
    
    return True, ""

def is_valid_model(model: str) -> tuple[bool, str]:
    """
    Проверяет валидность названия модели автомобиля.
    Возвращает кортеж (is_valid, error_message).
    """
    # Используем базовую проверку названия
    return is_valid_car_name(model)
