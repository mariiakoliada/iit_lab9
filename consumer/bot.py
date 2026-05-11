import telebot
import pika
import json
import os
import time
import threading
import requests
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.environ.get('TELEGRAM_TOKEN')
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
FLUENTD_URL = os.environ.get('FLUENTD_URL', 'http://localhost:8080/app.delivery')

bot = telebot.TeleBot(TOKEN)
user_chat_id = None

STATUS_EMOJI = {
    "pickup": "🏪",
    "delivering": "🛵",
    "delivered": "✅",
    "cancelled": "❌"
}

def send_log(event_type, data):
    payload = {"event": event_type, **data}
    try:
        requests.post(
            FLUENTD_URL,
            data=json.dumps(payload, ensure_ascii=False),
            headers={"Content-Type": "application/json"},
            timeout=3
        )
        print(f"Лог відправлено: {payload}")
    except Exception as e:
        print(f"Помилка логування: {e}")

def get_rabbitmq_connection():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST)
            )
            return connection
        except Exception:
            print("RabbitMQ ще не готовий, чекаємо...")
            time.sleep(3)

def check_queue():
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue='delivery_queue', durable=True)
    messages = []
    while True:
        method, properties, body = channel.basic_get(queue='delivery_queue')
        if method:
            data = json.loads(body)
            messages.append(data)
            channel.basic_ack(method.delivery_tag)
        else:
            break
    connection.close()
    return messages

def send_notifications():
    if user_chat_id is None:
        print("Немає користувача для сповіщення")
        return
    messages = check_queue()
    if messages:
        for msg in messages:
            emoji = STATUS_EMOJI.get(msg['type'], '🔔')
            text = (
                f"{emoji} *Оновлення замовлення!*\n\n"
                f"👤 Кур'єр: {msg['courier']}\n"
                f"📋 {msg['text']}"
            )
            bot.send_message(user_chat_id, text, parse_mode='Markdown')
            send_log("notification_delivered", {
                "chat_id": user_chat_id,
                "status": msg['type'],
                "courier": msg['courier'],
                "bot": "consumer"
            })
            print(f"Надіслано: {text}")
    else:
        print("Черга порожня")

def scheduler():
    while True:
        print("Перевіряємо чергу...")
        send_notifications()
        time.sleep(900)

def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔍 Перевірити статус"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    global user_chat_id
    user_chat_id = message.chat.id
    send_log("bot_start", {
        "chat_id": message.chat.id,
        "user": message.from_user.first_name,
        "bot": "consumer"
    })
    bot.reply_to(message,
        "📦 Привіт!\n\n"
        "Я буду сповіщати тебе про статус твого замовлення!\n"
        "Натисни кнопку нижче щоб перевірити статус 👇",
        reply_markup=get_main_menu()
    )
    send_notifications()

@bot.message_handler(func=lambda m: m.text == "🔍 Перевірити статус")
@bot.message_handler(commands=['check'])
def check_status(message):
    global user_chat_id
    user_chat_id = message.chat.id
    send_log("manual_check", {
        "chat_id": message.chat.id,
        "user": message.from_user.first_name
    })
    messages = check_queue()
    if messages:
        for msg in messages:
            emoji = STATUS_EMOJI.get(msg['type'], '🔔')
            text = (
                f"{emoji} *Оновлення замовлення!*\n\n"
                f"👤 Кур'єр: {msg['courier']}\n"
                f"📋 {msg['text']}"
            )
            bot.send_message(message.chat.id, text, parse_mode='Markdown')
            send_log("notification_delivered", {
                "chat_id": message.chat.id,
                "status": msg['type'],
                "courier": msg['courier']
            })
    else:
        bot.reply_to(message,
            "📭 Нових оновлень немає!\n"
            "Ми сповістимо тебе як тільки статус зміниться 😊",
            reply_markup=get_main_menu()
        )

print("Бот Клієнт запущено...")
scheduler_thread = threading.Thread(target=scheduler)
scheduler_thread.daemon = True
scheduler_thread.start()
bot.infinity_polling()