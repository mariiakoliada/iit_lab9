import telebot
import pika
import json
import os
import time
import requests
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.environ.get('TELEGRAM_TOKEN')
RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'localhost')
FLUENTD_URL = os.environ.get('FLUENTD_URL', 'http://localhost:8080/app.delivery')

bot = telebot.TeleBot(TOKEN)

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

def send_to_queue(payload):
    connection = get_rabbitmq_connection()
    channel = connection.channel()
    channel.queue_declare(queue='delivery_queue', durable=True)
    channel.basic_publish(
        exchange='',
        routing_key='delivery_queue',
        body=json.dumps(payload, ensure_ascii=False)
    )
    connection.close()

def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🏪 Забрав замовлення"))
    markup.row(KeyboardButton("🛵 Їду до клієнта"))
    markup.row(KeyboardButton("✅ Доставив замовлення"))
    markup.row(KeyboardButton("❌ Скасувати замовлення"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    send_log("bot_start", {
        "courier_id": message.from_user.id,
        "courier_name": message.from_user.first_name,
        "bot": "producer"
    })
    bot.reply_to(message,
        "🚴 Привіт, Кур'єре!\n\n"
        "Я допоможу сповіщати клієнтів про статус замовлення.\n"
        "Обери статус з меню нижче 👇",
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "🏪 Забрав замовлення")
def picked_up(message):
    payload = {
        "type": "pickup",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id,
        "text": "Кур'єр забрав ваше замовлення з ресторану і вже іде до вас!"
    }
    send_to_queue(payload)
    send_log("status_update", {
        "status": "pickup",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id
    })
    bot.reply_to(message,
        "✅ Клієнта сповіщено!\n🏪 Статус: Замовлення забрано з ресторану",
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "🛵 Їду до клієнта")
def delivering(message):
    payload = {
        "type": "delivering",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id,
        "text": "Кур'єр вже поруч! Очікуйте доставку найближчим часом 🛵"
    }
    send_to_queue(payload)
    send_log("status_update", {
        "status": "delivering",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id
    })
    bot.reply_to(message,
        "✅ Клієнта сповіщено!\n🛵 Статус: Їду до клієнта",
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "✅ Доставив замовлення")
def delivered(message):
    payload = {
        "type": "delivered",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id,
        "text": "Ваше замовлення доставлено! Смачного! 🍽✅"
    }
    send_to_queue(payload)
    send_log("status_update", {
        "status": "delivered",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id
    })
    bot.reply_to(message,
        "✅ Клієнта сповіщено!\n✅ Статус: Замовлення доставлено",
        reply_markup=get_main_menu()
    )

@bot.message_handler(func=lambda m: m.text == "❌ Скасувати замовлення")
def cancelled(message):
    bot.reply_to(message, "❌ Вкажи причину скасування:")
    bot.register_next_step_handler(message, process_cancel_reason)

def process_cancel_reason(message):
    payload = {
        "type": "cancelled",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id,
        "text": f"На жаль, ваше замовлення скасовано. Причина: {message.text}"
    }
    send_to_queue(payload)
    send_log("status_update", {
        "status": "cancelled",
        "courier": message.from_user.first_name,
        "courier_id": message.from_user.id,
        "cancel_reason": message.text
    })
    bot.reply_to(message,
        "✅ Клієнта сповіщено про скасування!",
        reply_markup=get_main_menu()
    )

print("Бот Кур'єр запущено...")
bot.infinity_polling()