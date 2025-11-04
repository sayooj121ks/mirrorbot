import os
import time
import logging
import traceback
from threading import Thread
from flask import Flask
import telebot
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

# Enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running", 200

@app.route('/health')
def health():
    return {"status": "healthy", "timestamp": time.time()}, 200

def start_flask():
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🌐 Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

# Initialize bot with retry logic
def initialize_bot():
    max_retries = 5
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Initializing bot (attempt {attempt + 1})...")
            
            # MongoDB connection
            MONGO_URI = os.getenv("MONGO_URI")
            TOKEN = os.getenv("BOT_TOKEN")
            
            mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
            mongo_client.admin.command('ping')
            
            db = mongo_client.mirror_bot
            collection = db.channels
            
            # Load channels
            channels = [doc["chat_id"] for doc in collection.find()]
            logger.info(f"✅ Loaded {len(channels)} channels")
            
            # Initialize bot
            bot = telebot.TeleBot(TOKEN)
            logger.info("✅ Bot initialized successfully")
            
            return bot, channels, collection, mongo_client
            
        except Exception as e:
            logger.error(f"❌ Initialization failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                raise e

def run_bot_with_restart():
    """Run bot with auto-restart on failure"""
    while True:
        try:
            logger.info("🚀 Starting/Restarting bot...")
            
            # Initialize bot components
            bot, channels, collection, mongo_client = initialize_bot()
            
            # Your existing bot handlers
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
                    # Add other content types...
                except Exception as e:
                    logger.error(f"Failed to send to {target_chat}: {e}")

            @bot.channel_post_handler(content_types=['text', 'photo', 'video', 'document'])
            def mirror_message(message):
                source_chat = message.chat.id
                if source_chat in channels:
                    logger.info(f"🔄 Mirroring from {source_chat}")
                    for target_chat in channels:
                        if target_chat != source_chat:
                            send_to_channel(target_chat, message)

            # Start polling with timeout
            logger.info("🤖 Starting bot polling...")
            bot.polling(none_stop=True,timeout=60, long_polling_timeout=60,skip_pending=True )
        except Exception as e:
            logger.error(f"💥 Bot crashed: {e}")
            logger.error(traceback.format_exc())
            logger.info("🔄 Restarting in 10 seconds...")
            time.sleep(10)

def periodic_heartbeat():
    """Log heartbeat every 5 minutes to confirm bot is alive"""
    while True:
        logger.info("💓 Bot heartbeat - still running")
        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    logger.info("🎯 Starting Mirror Bot with auto-restart...")
    
    # Start Flask in background
    flask_thread = Thread(target=start_flask, daemon=True)
    flask_thread.start()
    
    # Start heartbeat
    heartbeat_thread = Thread(target=periodic_heartbeat, daemon=True)
    heartbeat_thread.start()
    
    # Start bot with auto-restart
    run_bot_with_restart()

