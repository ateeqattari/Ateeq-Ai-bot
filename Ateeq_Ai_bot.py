
# ==========================================
# 1. CREDENTIALS & API KEYS CONFIGURATION (SECURE)
# ==========================================
import os
import telebot
import urllib.request
import json
import sqlite3
import time

# Reading tokens safely from environment variables (Render / Cloud environment)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

# Admin Telegram User ID
ADMIN_CHAT_ID = 123456789  

# ==========================================
# 2. AGENT RULES & SYSTEM PROMPT (ENGLISH)
# ==========================================
SYSTEM_PROMPT = """
You are a respectful, authentic, and highly professional AI assistant.
Your rules:
1. Always communicate with politeness and absolute respect.
2. Provide accurate, well-researched, and detailed answers with references where applicable.
3. Always respond in clear and professional English.
4. Maintain high ethical standards at all times.
"""

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)

# ==========================================
# 3. DATABASE SETUP (SQLite Persistent Memory)
# ==========================================
DB_FILE = "bot_memory.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id INTEGER,
            role TEXT,
            content TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            is_vip INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def save_message(chat_id, role, content):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO chat_history (chat_id, role, content) VALUES (?, ?, ?)', (chat_id, role, content))
    conn.commit()
    conn.close()

def get_chat_history(chat_id, limit=6):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT role, content FROM chat_history WHERE chat_id = ? ORDER BY rowid DESC LIMIT ?', (chat_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for role, content in reversed(rows):
        history.append({"role": role, "parts": [{"text": content}]})
    return history

print("=====================================================")
print("🚀 Telegram Ultra Pro Max AI Bot Fully Configured & Started!")
print("=====================================================")

# ==========================================
# 4. COMMAND HANDLERS (/start, /help)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    username = message.from_user.username or "User"
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (chat_id, username, is_vip) VALUES (?, ?, 0)', (chat_id, username))
    conn.commit()
    conn.close()
    
    welcome_text = (
        f"Hello {username}!\n\n"
        "Welcome to Ateeq's Ultra Pro Max AI Companion. You can ask me any question, "
        "have me read PDFs, or perform live web searches for you!\n\n"
        "Type /help to view the available commands list."
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = (
        "🤖 *Ateeq AI Bot Help Menu*\n\n"
        "• Direct Text: Ask me any general or professional question.\n"
        "• PDF Reader: Upload any document to analyze its contents.\n"
        "• Image Analysis: Send photos for instant AI evaluation.\n\n"
        "Commands:\n"
        "/start - Start the bot and view the welcome message\n"
        "/help - View this help and features menu\n"
        "/broadcast - Send an announcement (Admin Only)"
    )
    bot.reply_to(message, help_text, parse_mode='Markdown')

# ==========================================
# 5. ADMIN BROADCAST COMMAND
# ==========================================
@bot.message_handler(commands=['broadcast'])
def broadcast_message(message):
    if message.from_user.id != ADMIN_CHAT_ID and ADMIN_CHAT_ID != 123456789:
        bot.reply_to(message, "This command is restricted to the administrator only!")
        return
        
    text_to_broadcast = message.text.replace('/broadcast', '').strip()
    if not text_to_broadcast:
        bot.reply_to(message, "Please provide a message to broadcast! Example: `/broadcast Hello everyone!`")
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT chat_id FROM users')
    users = cursor.fetchall()
    conn.close()
    
    success_count = 0
    for (chat_id,) in users:
        try:
            bot.send_message(chat_id, f"📢 *Announcement*\n\n{text_to_broadcast}", parse_mode='Markdown')
            success_count += 1
        except Exception:
            pass
            
    bot.reply_to(message, f"Broadcast completed successfully! Sent to {success_count} users.")

# ==========================================
# 6. MAIN MESSAGE & MULTIMEDIA HANDLER
# ==========================================
@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'document', 'voice'])
def handle_incoming(message):
    chat_id = message.chat.id
    user_text = message.text or message.caption or "Please analyze this file or image."
    
    wait_msg = bot.reply_to(message, "Thinking... ⏳")
    bot.send_chat_action(chat_id, 'typing')
    
    save_message(chat_id, "user", user_text)
    history = get_chat_history(chat_id, limit=6)
    
    data = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": history
    }
    
    req = urllib.request.Request(
        GEMINI_URL, 
        data=json.dumps(data).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            reply_text = result['candidates'][0]['content']['parts'][0]['text']
            
            save_message(chat_id, "model", reply_text)
            bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=reply_text)
            
    except urllib.error.HTTPError as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text="Apologies, the server is currently busy. Please try again in a moment.")
    except Exception as e:
        bot.edit_message_text(chat_id=chat_id, message_id=wait_msg.message_id, text=f"An error occurred: {e}")

if __name__ == "__main__":
    while True:
        try:
            print("Connecting to Telegram servers...")
            bot.polling(none_stop=True, interval=3, timeout=20)
        except Exception as e:
            print(f"Network connection warning: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
