import os
import telebot
from pymongo import MongoClient
from flask import Flask
import threading
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Telegram Mirror Bot is running!", 200

@app.route('/health')
def health():
    return {
        "status": "healthy", 
        "service": "telegram-mirror-bot",
        "channels_count": len(channels)
    }, 200

@app.route('/ping')
def ping():
    return "pong", 200

# Get environment variables
MONGO_URI = os.getenv("MONGO_URI")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN environment variable is missing!")
    raise ValueError("BOT_TOKEN environment variable is required")

if not MONGO_URI:
    logger.error("❌ MONGO_URI environment variable is missing!")
    raise ValueError("MONGO_URI environment variable is required")

# Initialize MongoDB
try:
    logger.info("🔗 Connecting to MongoDB...")
    mongo_client = MongoClient(MONGO_URI)
    DB_NAME = "mirror_bot"
    COLLECTION_NAME = "channels"
    db = mongo_client[DB_NAME]
    collection = db[COLLECTION_NAME]
    
    # Test connection
    mongo_client.admin.command('ping')
    logger.info("✅ Connected to MongoDB successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    raise

# Load channels from MongoDB
try:
    channels = [doc["chat_id"] for doc in collection.find()]
    logger.info(f"✅ Loaded {len(channels)} channels from MongoDB.")
except Exception as e:
    logger.error(f"❌ Failed to load channels: {e}")
    channels = []

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# ───────────────────────────────
# Command: /add → Add this channel
# ───────────────────────────────
@bot.channel_post_handler(commands=['add'])
def add_channel(message):
    try:
        chat_id = message.chat.id
        if chat_id not in channels:
            channels.append(chat_id)
            collection.insert_one({"chat_id": chat_id})
            bot.send_message(chat_id, f"✅ Channel added and saved!\nTotal channels: {len(channels)}")
            logger.info(f"➕ Added channel: {chat_id}")
        else:
            bot.send_message(chat_id, "ℹ️ Channel already added.")
    except Exception as e:
        logger.error(f"❌ Error in add_channel: {e}")

# ───────────────────────────────
# Function: Send message to target channel
# ───────────────────────────────
def send_to_channel(target_chat, message):
    try:
        ctype = message.content_type
        caption = getattr(message, 'caption', '') or ""
        caption_entities = getattr(message, 'caption_entities', None)
        entities = getattr(message, 'entities', None)

        if ctype == 'text':
            bot.send_message(target_chat, message.text, entities=entities)

        elif ctype == 'photo':
            file_id = message.photo[-1].file_id
            bot.send_photo(target_chat, file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'video':
            bot.send_video(target_chat, message.video.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'document':
            bot.send_document(target_chat, message.document.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'audio':
            bot.send_audio(target_chat, message.audio.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'voice':
            bot.send_voice(target_chat, message.voice.file_id, caption=caption)

        elif ctype == 'animation':
            bot.send_animation(target_chat, message.animation.file_id, caption=caption, caption_entities=caption_entities)

        elif ctype == 'sticker':
            bot.send_sticker(target_chat, message.sticker.file_id)

        elif ctype == 'video_note':
            bot.send_video_note(target_chat, message.video_note.file_id)

        elif ctype == 'poll':
            question = message.poll.question
            options = [opt.text for opt in message.poll.options]
            bot.send_poll(target_chat, question, options)

        elif ctype == 'location':
            bot.send_location(target_chat, message.location.latitude, message.location.longitude)

        elif ctype == 'contact':
            bot.send_contact(target_chat, message.contact.phone_number, message.contact.first_name)

        else:
            logger.warning(f"⚠️ Unsupported message type: {ctype}")
            if hasattr(message, 'text') and message.text:
                bot.send_message(target_chat, f"[{ctype}] {message.text}")

    except Exception as e:
        logger.error(f"❌ Failed to send {ctype} to {target_chat}: {e}")

# ───────────────────────────────
# Mirror messages between channels
# ───────────────────────────────
@bot.channel_post_handler(content_types=[
    'text', 'photo', 'video', 'document', 'audio', 'voice', 
    'animation', 'sticker', 'video_note', 'poll', 'location', 'contact'
])
def mirror_message(message):
    try:
        source_chat = message.chat.id
        if source_chat in channels:
            logger.info(f"🔄 Mirroring {message.content_type} from {source_chat} to {len(channels)-1} channels")
            for target_chat in channels:
                if target_chat != source_chat:
                    send_to_channel(target_chat, message)
    except Exception as e:
        logger.error(f"❌ Error in mirror_message: {e}")

# ───────────────────────────────
# Handle media groups (albums)
# ───────────────────────────────
@bot.channel_post_handler(content_types=['media_group'])
def handle_media_group(messages):
    try:
        logger.info(f"🖼️ Media group detected with {len(messages)} items")
        for message in messages:
            mirror_message(message)
    except Exception as e:
        logger.error(f"❌ Error in handle_media_group: {e}")

# ───────────────────────────────
# Bot polling with error handling
# ───────────────────────────────
def start_bot():
    logger.info("🤖 Starting Telegram Bot...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            logger.error(f"❌ Bot polling error: {e}")
            logger.info("🔄 Restarting bot in 10 seconds...")
            time.sleep(10)

# ───────────────────────────────
# Flask server for health checks
# ───────────────────────────────
def start_flask():
    port = int(os.getenv("PORT", 8080))
    logger.info(f"🌐 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

# ───────────────────────────────
# Main execution
# ───────────────────────────────
if __name__ == "__main__":
    logger.info("🚀 Initializing Telegram Mirror Bot on Railway...")
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=start_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Give Flask a moment to start
    time.sleep(2)
    
    # Start the bot
    start_bot()

