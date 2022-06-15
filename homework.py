import os
import telegram
import time
import requests
import logging
import sys
import enum
import threading

from dotenv import load_dotenv
from exeptions import (
    APIConnectionError, UnknownStatusError, IncorrectKeyError)
from typing import Union

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(stream=sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s %(levelname)s %(message)s'
)
handler.setFormatter(formatter)
logger.addHandler(handler)


class State(enum.Enum):
    """Установки для repl."""

    INITIAL = 0
    RUNNING = 1
    STOPPED = 2


state = State.INITIAL
state_lock = threading.Lock()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def send_message(bot: telegram.Bot, message: str) -> None:
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.info(f'Бот отправил сообщение: {message}')
    except Exception as error:
        logger.error(f'Бот не смог отправить сообщение, ошибка: {error}')


def get_api_answer(current_timestamp: int) -> list:
    """Делает запрос к единственному эндпоинту API."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT, headers=HEADERS, params=params)
        logger.info(f'Запрос выполнен: {response.status_code}')
    except Exception as error:
        raise APIConnectionError(f'Ошибка подключения к API: {error}')
    else:
        status_code = response.status_code
        if status_code == 200:
            return response.json()
        elif status_code == 404:
            logger.error('Сбой в работе программы: '
                         'Эндпоинт https://practicum.yandex.ru'
                         '/api/user_api/homework_statuses/ недоступен. '
                         'Код ответа API: 404')
            raise APIConnectionError(
                f'Ошибка подключения к API: {status_code}')
        else:
            logger.error(f'Сбой в работе программы: '
                         f'Код ответа API: {status_code} ')
            raise APIConnectionError(
                f'Ошибка подключения к API: {status_code}')


def check_response(response: dict) -> Union[list, None]:
    """Проверяет ответ API на корректность."""
    if not isinstance(response['homeworks'], list):
        raise TypeError(
            f'Ответ от API не является списком: response = {response}'
        )
    try:
        homeworks = response['homeworks']
    except Exception as error:
        logger.error(f'Нет ключа "homeworks" в ответе API '
                     f'Ошибка: {error}.')
        homeworks = None
        raise IncorrectKeyError(
            f'Неккоректный ключ в ответе API, ошибка: {error}')
    return homeworks


def parse_status(homework: dict) -> str:
    """Извлекает из информации о конкретной домашней работе статус."""
    homework_name = homework['homework_name']
    homework_status = homework['status']
    try:
        verdict = HOMEWORK_STATUSES[homework_status]
    except Exception as error:
        print(error)
        verdict = 'Статус домашней работы неизвестен.'
        raise UnknownStatusError(
            f'Неизвестный статус домашней работы, ошибка: {error}')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверяет доступность переменных окружения."""
    return all((
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    ))


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        error_message = (
            'Отсутствуют переменные окружения: '
            'PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.'
            'Программа принудительно остановлена.'
        )
        logger.critical(error_message)
        sys.exit(error_message)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time())

    global state
    with state_lock:
        state = State.RUNNING

    curr_message = None
    prev_message = curr_message

    while True:
        with state_lock:
            if state == State.STOPPED:
                break

        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if len(homeworks) > 0:
                curr_message = parse_status(homeworks[0])
            current_timestamp = response['current_date']
            if curr_message == prev_message:
                logger.debug('Нет обновления статуса домашней работы.')
            else:
                send_message(bot, curr_message)
                prev_message = curr_message
            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            time.sleep(RETRY_TIME)


def repl():
    """Плавное завершение."""
    global state
    while True:
        command = input('Please, press "s" to stop')
        if command == 's':
            with state_lock:
                state = State.STOPPED
            break


if __name__ == '__main__':

    repl_thread = threading.Thread(target=repl)
    repl_thread.start()

    main()
