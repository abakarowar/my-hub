#!/usr/bin/env python3
"""
Скрипт для автоматической отправки информации о дежурных в YuChat
Парсит HTML файл, экспортированный из Confluence
"""
import sys
import os
import yaml
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
import html
import glob

# Настройка логирования (путь к логу определяется относительно директории скрипта)
script_dir = os.path.dirname(os.path.abspath(__file__))
log_file = os.path.join(script_dir, 'duty_notifier.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def load_config(config_path='config.yaml'):
    """Загрузка конфигурации"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_config_path = os.path.join(script_dir, config_path)
        
        with open(full_config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logger.error(f"Файл конфигурации {config_path} не найден")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"Ошибка парсинга YAML: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации: {e}")
        sys.exit(1)

def get_html_file(file_path):
    """
    Получение HTML содержимого из файла
    
    Args:
        file_path: Путь к HTML файлу
    
    Returns:
        HTML содержимое или None
    """
    try:
        if not os.path.exists(file_path):
            logger.error(f"Файл {file_path} не найден")
            return None
        
        logger.info(f"Чтение HTML файла: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        logger.info("HTML файл успешно прочитан")
        return content
        
    except Exception as e:
        logger.error(f"Ошибка чтения файла: {e}")
        return None

def parse_duty_table(html_content, target_date):
    """
    Парсинг таблицы дежурств из HTML
    
    Args:
        html_content: HTML содержимое страницы
        target_date: Дата для поиска (datetime объект)
    
    Returns:
        dict: {'основной': [список имен], 'резервный': [список имен]}
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Ищем таблицу
    table = soup.find('table', class_='confluenceTable')
    if not table:
        logger.error("Таблица с классом 'confluenceTable' не найдена на странице")
        return {'основной': [], 'резервный': []}
    
    # Получаем все строки таблицы
    rows = table.find_all('tr')
    if len(rows) < 2:
        logger.error("Таблица пуста или имеет неправильную структуру")
        return {'основной': [], 'резервный': []}
    
    # Ищем строку с заголовками дат (вторая строка обычно содержит даты)
    # Первая строка - "Сотрудник" и "Число месяца"
    # Вторая строка - конкретные даты: 01, 02, 03...
    header_row = None
    header_row_index = None
    
    for idx, row in enumerate(rows[:5]):  # Проверяем первые 5 строк
        cells = row.find_all(['th', 'td'])
        # Ищем строку, где есть числа от 01 до 31
        for cell in cells:
            text = cell.get_text(strip=True)
            # Убираем HTML-сущности и проверяем
            text_clean = html.unescape(text)
            # Ищем числа от 1 до 31
            if text_clean.isdigit() and 1 <= int(text_clean) <= 31:
                header_row = row
                header_row_index = idx
                break
        if header_row:
            break
    
    if not header_row:
        logger.error("Не найдена строка с заголовками дат")
        return {'основной': [], 'резервный': []}
    
    date_headers = header_row.find_all(['th', 'td'])
    
    # Находим индекс колонки с нужной датой
    target_day = target_date.day
    target_day_str = f"{target_day:02d}"
    
    date_column_index = None
    for idx, header in enumerate(date_headers):
        header_text = header.get_text(strip=True)
        header_text = html.unescape(header_text)  # Декодируем HTML-сущности
        # Убираем все нецифровые символы для сравнения
        header_digits = ''.join(filter(str.isdigit, header_text))
        if header_digits == target_day_str or header_digits == str(target_day):
            date_column_index = idx
            logger.info(f"Найдена колонка с датой {target_day} (индекс {date_column_index}, текст: '{header_text}')")
            break
    
    if date_column_index is None:
        logger.warning(f"Колонка с датой {target_day} не найдена в таблице")
        available_dates = [html.unescape(h.get_text(strip=True)) for h in date_headers[:10]]
        logger.debug(f"Доступные заголовки (первые 10): {available_dates}")
        return {'основной': [], 'резервный': []}
    
    # Проходим по строкам с сотрудниками (начинаем после строки с датами)
    duty_list = {'основной': [], 'резервный': []}
    
    # В строке заголовка колонка 0 = дата 01, колонка 16 = дата 17
    # В строке сотрудника колонка 0 = имя, колонка 1 = дежурство на 01, колонка 17 = дежурство на 17
    # Поэтому нужно использовать date_column_index + 1 для строк сотрудников
    employee_duty_column_index = date_column_index + 1
    
    for row in rows[header_row_index + 1:]:
        cells = row.find_all(['td', 'th'])
        if len(cells) <= employee_duty_column_index:
            continue
        
        # Первая ячейка - имя сотрудника
        employee_cell = cells[0]
        employee_name = employee_cell.get_text(strip=True)
        employee_name = html.unescape(employee_name)  # Декодируем HTML-сущности
        
        if not employee_name or employee_name.lower() in ['сотрудник', 'employee', '']:
            continue
        
        # Ячейка с датой (используем employee_duty_column_index, а не date_column_index)
        duty_cell = cells[employee_duty_column_index]
        duty_value = duty_cell.get_text(strip=True)
        duty_value = html.unescape(duty_value).upper()  # Декодируем и приводим к верхнему регистру
        
        # Определяем тип дежурства
        # В HTML могут быть: О (основной), Р (резервный), или пусто
        if duty_value == 'О' or duty_value == 'O':
            duty_list['основной'].append(employee_name)
            logger.debug(f"Найден основной дежурный: {employee_name}")
        elif duty_value == 'Р' or duty_value == 'P':
            duty_list['резервный'].append(employee_name)
            logger.debug(f"Найден резервный дежурный: {employee_name}")
    
    return duty_list

def format_message(date, duty_list):
    """
    Формирование сообщения для отправки
    
    Args:
        date: Дата (datetime объект)
        duty_list: Словарь с дежурными {'основной': [...], 'резервный': [...]}
    
    Returns:
        str: Отформатированное сообщение
    """
    date_str = date.strftime('%d.%m.%Y')
    
    message_parts = [f"Сегодня {date_str} дежурные:"]
    
    if duty_list['основной']:
        main_duty = ", ".join(duty_list['основной'])
        message_parts.append(f"Основной: {main_duty}")
    
    if duty_list['резервный']:
        reserve_duty = ", ".join(duty_list['резервный'])
        message_parts.append(f"Резервный: {reserve_duty}")
    
    if not duty_list['основной'] and not duty_list['резервный']:
        message_parts.append("Дежурных не назначено")
    
    return "\n".join(message_parts)

def send_to_yuchat(message, config):
    """Отправка сообщения в YuChat через API"""
    yuchat_config = config.get('yuchat', {})
    
    required_keys = ['token', 'workspace_id', 'chat_id']
    missing_keys = [key for key in required_keys if not yuchat_config.get(key)]
    
    if missing_keys:
        logger.error(f"Отсутствуют обязательные параметры YuChat: {', '.join(missing_keys)}")
        return False
    
    url = yuchat_config.get('api_url', 'https://chat-api.bft.ru/public/v1/chat.message.send')
    headers = {
        "Authorization": f"Bearer {yuchat_config['token']}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "workspaceId": yuchat_config['workspace_id'],
        "chatId": yuchat_config['chat_id'],
        "markdown": message
    }
    
    try:
        logger.info("Отправка сообщения в YuChat...")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"Сообщение успешно отправлено в YuChat (messageId: {result.get('messageId', 'N/A')})")
        return True
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP ошибка при отправке в YuChat: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            try:
                error_body = e.response.json()
                logger.error(f"Error response: {error_body}")
            except:
                logger.error(f"Response text: {e.response.text[:500]}")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса к YuChat: {e}")
        return False

def main():
    """Основная функция"""
    # Загружаем конфигурацию
    config = load_config()
    
    # Проверяем наличие секций конфигурации
    if 'yuchat' not in config:
        logger.error("Секция 'yuchat' не найдена в конфигурации")
        sys.exit(1)
    
    # Получаем текущую дату (нужна для поиска файла и определения дежурных)
    today = datetime.now()
    
    # Получаем путь к HTML файлу
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Вариант 1: Если указан конкретный файл в конфиге
    html_file = config.get('html_file')
    
    if html_file:
        # Если путь относительный, делаем его относительно директории скрипта
        if not os.path.isabs(html_file):
            html_file = os.path.join(script_dir, html_file)
    else:
        # Вариант 2: Автоматический поиск файла по месяцу
        # Ищем файлы вида: MM.YYYY.html или schedule_MM.YYYY.html и т.д.
        month_str = today.strftime("%m.%Y")
        logger.info(f"Автоматический поиск HTML файла для месяца {month_str}...")
        
        # Паттерны для поиска
        patterns = [
            f"{month_str}.html",
            f"schedule_{month_str}.html",
            f"duty_{month_str}.html",
            "*.html"  # Любой HTML файл, если не найдено по паттерну
        ]
        
        html_file = None
        for pattern in patterns:
            matches = glob.glob(os.path.join(script_dir, pattern))
            if matches:
                # Берем первый найденный файл
                html_file = matches[0]
                logger.info(f"Найден файл: {os.path.basename(html_file)}")
                break
        
        if not html_file:
            logger.error(f"HTML файл не найден в директории {script_dir}")
            logger.error(f"Поместите файл с графиком дежурств в эту директорию")
            logger.error(f"Или укажите путь в config.yaml: html_file: 'имя_файла.html'")
            sys.exit(1)
    
    logger.info(f"Поиск дежурных на {today.strftime('%d.%m.%Y')}")
    logger.info(f"Используется HTML файл: {html_file}")
    
    # Получаем HTML содержимое
    html_content = get_html_file(html_file)
    
    if not html_content:
        logger.error("Не удалось прочитать HTML файл")
        sys.exit(1)
    
    # Парсим таблицу
    duty_list = parse_duty_table(html_content, today)
    
    logger.info(f"Найдено дежурных: основной - {len(duty_list['основной'])}, резервный - {len(duty_list['резервный'])}")
    
    if duty_list['основной']:
        logger.info(f"Основные дежурные: {', '.join(duty_list['основной'])}")
    if duty_list['резервный']:
        logger.info(f"Резервные дежурные: {', '.join(duty_list['резервный'])}")
    
    # Формируем сообщение
    message = format_message(today, duty_list)
    logger.info(f"Сформировано сообщение:\n{message}")
    
    # Отправляем в YuChat
    if send_to_yuchat(message, config):
        logger.info("Скрипт выполнен успешно")
        sys.exit(0)
    else:
        logger.error("Ошибка отправки сообщения")
        sys.exit(1)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Прервано пользователем")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)

