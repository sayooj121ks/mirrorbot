import telebot
import time
import logging
import traceback
from threading import Thread
from flask import Flask
import os

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot running", 200

@app.route('/health')
def health():
    return "OK", 200

def start_flask():
    port = int(os.getenv("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)

def run_bot():
    """Run bot with crash recovery"""
    restart_count = 0
    max_restarts = 50  # Prevent infinite loops
    
    while restart_count < max_restarts:
        try:
            restart_count += 1
            logger.info(f"🔄 Starting bot (attempt {restart_count})...")
            
            # Your existing bot initialization
            MONGO_URI = os.getenv("MONGO_URI")
            TOKEN = os.getenv("BOT_TOKEN")
            
            # Initialize MongoDB and bot
            from pymongo import MongoClient
            mongo_client = MongoClient(MONGO_URI)
            db = mongo_client.mirror_bot
            collection = db.channels
            channels = [doc["chat_id"] for doc in collection.find()]
            
            bot = telebot.TeleBot(TOKEN)
            
            # Your existing handlers
            @bot.channel_post_handler(commands=['add'])
            def add_channel(message):
                chat_id = message.chat.id
                if chat_id not in channels:
                    channels.append(chat_id)
                    collection.insert_one({"chat_id": chat_id})
                    bot.send_message(chat_id, f"✅ Channel added! Total: {len(channels)}")
                    logger.info(f"➕ Added channel: {chat_id}")

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
                    # Add other types...
                except Exception as e:
                    logger.error(f"Send failed: {e}")

            @bot.channel_post_handler(content_types=['text', 'photo', 'video', 'document'])
            def mirror_message(message):
                source_chat = message.chat.id
                if source_chat in channels:
                    logger.info(f"Mirroring from {source_chat}")
                    for target_chat in channels:
                        if target_chat != source_chat:
                            send_to_channel(target_chat, message)

            # Start bot with crash protection
            logger.info("🤖 Bot started successfully")
            bot.polling(
                none_stop=True,
                timeout=60,
                long_polling_timeout=60,
                skip_pending=True
            )
            
        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
            logger.error(traceback.format_exc())
            
            # Wait before restart
            wait_time = min(restart_count * 10, 60)  # Max 60 seconds
            logger.info(f"🕒 Restarting in {wait_time} seconds...")
            time.sleep(wait_time)
    
    logger.error("❌ Max restarts reached. Bot stopped.")

def heartbeat():
    """Log heartbeat every 2 minutes"""
    while True:
        logger.info("💓 Bot heartbeat - running")
        time.sleep(120)  # 2 minutes

if __name__ == "__main__":
    logger.info("🚀 Starting mirror bot...")
    
    # Start Flask
    flask_thread = Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    # Start heartbeat
    heartbeat_thread = Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    
    # Start bot with crash recovery
    run_bot()


