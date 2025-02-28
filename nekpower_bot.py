import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging
import nest_asyncio
from telegram.error import NetworkError

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Включение поддержки нескольких асинхронных вызовов
nest_asyncio.apply()

# Инициализация базы данных
conn = sqlite3.connect("pushup_stats.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS stats (
                    chat_id INTEGER PRIMARY KEY, 
                    pushups_count INTEGER DEFAULT 0
                )''')
conn.commit()


# Стартовая команда
async def start(update: Update, context):
    chat_id = update.effective_chat.id
    cursor.execute("INSERT OR IGNORE INTO stats (chat_id, pushups_count) VALUES (?, ?)", (chat_id, 0))
    conn.commit()
    await update.message.reply_text('Привет! Я буду напоминать тебе об отжиманиях.')


# Обработка кнопок
async def button(update: Update, context):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    count = int(query.data)

    cursor.execute("UPDATE stats SET pushups_count = pushups_count + ? WHERE chat_id = ?", (count, chat_id))
    conn.commit()

    await query.edit_message_text(text=f"Вы сделали {count} отжиманий!")


# Напоминание о выполнении отжиманий
async def send_reminder(application, chat_id):
    logger.info(f"Отправка напоминания пользователю с chat_id: {chat_id}")
    keyboard = [
        [InlineKeyboardButton("20", callback_data='20')],
        [InlineKeyboardButton("30", callback_data='30')],
        [InlineKeyboardButton("40", callback_data='40')],
        [InlineKeyboardButton("50", callback_data='50')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await application.bot.send_message(chat_id=chat_id, text="Время отжиманий! Сколько раз вы хотите отжаться?",
                                       reply_markup=reply_markup)


# Команда для просмотра статистики
async def stats(update: Update, context):
    chat_id = update.effective_chat.id
    cursor.execute("SELECT pushups_count FROM stats WHERE chat_id = ?", (chat_id,))
    result = cursor.fetchone()
    total_pushups = result[0] if result else 0
    await update.message.reply_text(f"Общее количество отжиманий: {total_pushups}")


# Создание планировщика заданий
scheduler = AsyncIOScheduler()  # Создаём планировщик


def create_scheduler(application):
    chat_ids = get_all_chat_ids()  # Получаем всех chat_id из базы данных
    logger.info(f"Полученные chat_id для напоминаний: {chat_ids}")

    for chat_id in chat_ids:
        # Проверяем наличие задачи и добавляем, если её нет
        if not scheduler.get_job(str(chat_id) + '_morning'):
            scheduler.add_job(send_reminder, CronTrigger(hour=8, minute=30), args=[application, chat_id],
                              id=str(chat_id) + '_morning')

        if not scheduler.get_job(str(chat_id) + '_afternoon'):
            scheduler.add_job(send_reminder, CronTrigger(hour=15, minute=0), args=[application, chat_id],
                              id=str(chat_id) + '_afternoon')

        if not scheduler.get_job(str(chat_id) + '_evening'):
            scheduler.add_job(send_reminder, CronTrigger(hour=20, minute=0), args=[application, chat_id],
                              id=str(chat_id) + '_evening')

    scheduler.start()
    logger.info("Планировщик заданий запущен.")


def get_all_chat_ids():
    cursor.execute("SELECT chat_id FROM stats")
    return list(set(row[0] for row in cursor.fetchall()))  # Уникальные chat_id


# Основная функция
async def main():
    application = Application.builder().token("7620012752:AAHLdjQSZpXE72rI-qDJb-cmjIv_duDkA-0").build()

    # Регистрация команд и обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("stats", stats))

    # Создание планировщика
    create_scheduler(application)

    # Запуск бота
    try:
        await application.initialize()  # Явная инициализация приложения
        await application.start()
        await application.updater.start_polling()  # Запуск обработки обновлений

        # Используем asyncio.Event для блокировки, пока не произойдет остановка
        stop_event = asyncio.Event()
        await stop_event.wait()  # Ожидание, пока не будет установлено значение события
    except NetworkError as e:
        logger.error(f"Произошла ошибка сети: {e}")
        await asyncio.sleep(5)  # Ждем перед повторной попыткой


if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()  # Получаем текущий цикл
        loop.run_until_complete(main())  # Запускаем main в текущем цикле
    except RuntimeError:
        logger.error("Ошибка в цикле событий.")
