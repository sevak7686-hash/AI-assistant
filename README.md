# Telegram AI Assistant Bot

## Настройка

1. Клонируй репозиторий
2. Создай виртуальное окружение:

git clone <ссылка-на-репозиторий>
cd telegram-assistant


2. Создай виртуальное окружение:

python -m venv venv
venv\Scripts\activate


3. Установи зависимости:

pip install -r requirements.txt


4. Создай файл `.env` в корне проекта и добавь туда:

BOT_TOKEN=твой_токен_от_BotFather
ALLOWED_USER_ID=твой_telegram_id


Токен получаешь у @BotFather в Telegram.
Свой Telegram ID можно узнать у @userinfobot.

5. Запусти бота:

python bot.py


## Структура проекта

telegram-assistant/
├── bot.py # точка входа, инициализация бота
├── handlers/ # обработчики команд и сообщений
│ ├── commands.py # /start, /help, /reminders
│ └── media.py # voice, photo, video, текст
├── middlewares/ # access control и логирование
│ └── access.py
├── downloads/ # сохранённые voice/photo/video файлы
├── bot.log # логи бота
└── .env # токен и ID (не публикуется в git)


## Команды

- `/start` — приветствие
- `/help` — список доступных команд
- `/reminders` — напоминания (пока заглушка, ждёт интеграции с backend)

## Статус

- ✅ Приём text, voice, photo, video сообщений
- ✅ Access control (только разрешённый user_id)
- ✅ Логирование сообщений
- ✅ Обработка ошибок (bot не падает на неподдерживаемых типах)
- ⬜ Интеграция с AI (DeepSeek) — в разработке
- ⬜ Реальная логика напоминаний — в разработке
