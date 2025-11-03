import os
import telebot
from pymongo import MongoClient
from flask import Flask
import threading
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Telegram Mirror Bot is running!", 200

@app.route('/health')
def health():
    return "OK", 200

# Environment variables
BOT_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URI = os.environ.get('MONGO_URI')

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is required!")

# Initialize bot and database
bot = telebot.TeleBot(BOT_TOKEN)

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client.mirror_bot
    collection = db.channels
    mongo_client.admin.command('ping')
    logger.info("✅ MongoDB connected")
except Exception as e:
    logger.error(f"❌ MongoDB error: {e}")
    raise

# Load channels
channels = [doc["chat_id"] for doc in collection.find()]
logger.info(f"📊 Loaded {len(channels)} channels")

# Your existing bot functions here (add_channel, send_to_channel, mirror_message)
@bot.channel_post_handler(commands=['add'])
def add_channel(message):
    chat_id = message.chat.id
    if chat_id not in channels:
        channels.append(chat_id)
        collection.insert_one({"chat_id": chat_id})
        bot.send_message(chat_id, f"✅ Channel added! Total: {len(channels)}")
        logger.info(f"➕ Added channel: {chat_id}")
    else:
        bot.send_message(chat_id, "ℹ️ Channel already added.")

def send_to_channel(target_chat, message):
    try:
        ctype = message.content_type
        caption = getattr(message, 'caption', '') or ""
        
        if ctype == 'text':
            bot.send_message(target_chat, message.text)
        elif ctype == 'photo':
            file_id = message.photo[-1].file_id
            bot.send_photo(target_chat, file_id, caption=caption)
        elif ctype == 'video':
            bot.send_video(target_chat, message.video.file_id, caption=caption)
        # Add other content types as needed
    except Exception as e:
        logger.error(f"Failed to send to {target_chat}: {e}")

@bot.channel_post_handler(content_types=['text', 'photo', 'video', 'document'])
def mirror_message(message):
    source_chat = message.chat.id
    if source_chat in channels:
        logger.info(f"Mirroring from {source_chat}")
        for target_chat in channels:
            if target_chat != source_chat:
                send_to_channel(target_chat, message)

def run_bot():
    logger.info("🤖 Starting bot...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(10)

def run_web():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()
    run_bot()


