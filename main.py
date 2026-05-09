# main.py - Logo Bing Bingo Telegram Bot
# Complete working version - NO internal library imports

import os
import sqlite3
import random
import string
import threading
from datetime import datetime
from flask import Flask, request, jsonify

# ✅ CORRECT imports for python-telegram-bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)
from telegram.constants import ParseMode

# ============================================
# CONFIGURATION - READ FROM ENVIRONMENT
# ============================================

BOT_TOKEN = os.environ.get('8575015302:AAFnH6MKdm4uJEMnbN_0Krz0NW9J3DG4D38')
if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN environment variable not set!")
    print("Please add it in Render Dashboard → Environment")
    exit(1)

GAME_URL = os.environ.get('GAME_URL', 'https://logo-bingo-game.vercel.app')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', '@Fix6T')
TELEBIRR_NUMBER = os.environ.get('TELEBIRR_NUMBER', '0931721793')
OWNER_NAME = os.environ.get('OWNER_NAME', 'Wendesen Tamene')

CARD_PRICE = int(os.environ.get('CARD_PRICE', '10'))
MIN_WITHDRAW = int(os.environ.get('MIN_WITHDRAW', '50'))
WINNER_PERCENTAGE = int(os.environ.get('WINNER_PERCENTAGE', '70'))

print("=" * 50)
print("🎯 Logo Bing Bingo Bot Starting...")
print(f"🎮 Game URL: {GAME_URL}")
print(f"👑 Admin: {ADMIN_USERNAME}")
print(f"💰 Card Price: {CARD_PRICE} ETB")
print(f"🏆 Winner gets: {WINNER_PERCENTAGE}%")
print(f"🤖 Bot Token: {'✅ Set' if BOT_TOKEN else '❌ MISSING'}")
print("=" * 50)

# Conversation states
DEPOSIT_STATE = 1
WITHDRAW_STATE = 2

# Flask app
app = Flask(__name__)
ADMIN_ID = None

# ============================================
# DATABASE SETUP
# ============================================

def init_db():
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            balance REAL DEFAULT 0,
            total_deposited REAL DEFAULT 0,
            total_withdrawn REAL DEFAULT 0,
            total_won REAL DEFAULT 0,
            games_played INTEGER DEFAULT 0,
            games_won INTEGER DEFAULT 0,
            registered_date TEXT,
            is_admin INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS deposit_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            transaction_id TEXT,
            status TEXT DEFAULT 'pending',
            request_date TEXT,
            verified_by INTEGER,
            verified_date TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdraw_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            withdrawal_method TEXT,
            account_info TEXT,
            status TEXT DEFAULT 'pending',
            request_date TEXT,
            processed_by INTEGER,
            processed_date TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

def get_user(user_id):
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'user_id': row[0],
            'username': row[1],
            'first_name': row[2],
            'last_name': row[3],
            'balance': row[4],
            'total_deposited': row[5],
            'total_withdrawn': row[6],
            'total_won': row[7],
            'games_played': row[8],
            'games_won': row[9],
            'registered_date': row[10],
            'is_admin': row[11]
        }
    return None

def create_user(user_id, username, first_name, last_name=None):
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    try:
        registered_date = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_name, balance, registered_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username or '', first_name, last_name or '', 0, registered_date))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def update_balance(user_id, amount, operation='add'):
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row:
        if operation == 'add':
            new_balance = row[0] + amount
        else:
            if row[0] < amount:
                conn.close()
                return False
            new_balance = row[0] - amount
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def add_deposit_request(user_id, amount, transaction_id):
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    request_date = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO deposit_requests (user_id, amount, transaction_id, request_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, amount, transaction_id, request_date))
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return request_id

def add_withdraw_request(user_id, amount, method, account_info):
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    request_date = datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO withdraw_requests (user_id, amount, withdrawal_method, account_info, request_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, amount, method, account_info, request_date))
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return request_id

def get_pending_deposits():
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT dr.id, dr.user_id, dr.amount, dr.transaction_id, 
               dr.request_date, u.username, u.first_name
        FROM deposit_requests dr
        JOIN users u ON dr.user_id = u.user_id
        WHERE dr.status = 'pending'
        ORDER BY dr.request_date ASC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return rows

def verify_deposit(request_id, admin_id):
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, amount, status FROM deposit_requests WHERE id = ?', (request_id,))
    row = cursor.fetchone()
    if not row or row[2] != 'pending':
        conn.close()
        return False, 0
    user_id, amount, _ = row
    cursor.execute('UPDATE deposit_requests SET status = 'approved', verified_by = ?, verified_date = ? WHERE id = ?',
                   (admin_id, datetime.now().isoformat(), request_id))
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    current = cursor.fetchone()
    new_balance = current[0] + amount
    cursor.execute('UPDATE users SET balance = ?, total_deposited = total_deposited + ? WHERE user_id = ?',
                   (new_balance, amount, user_id))
    conn.commit()
    conn.close()
    return True, amount

# ============================================
# FLASK API ROUTES
# ============================================

@app.route('/')
def index():
    return jsonify({
        'status': 'online',
        'bot': 'Logo Bing Bingo Bot',
        'game_url': GAME_URL,
        'version': '1.0'
    })

@app.route('/api/user/<int:user_id>', methods=['GET'])
def api_get_user(user_id):
    user = get_user(user_id)
    if user:
        return jsonify({
            'success': True,
            'user': {
                'userId': user_id,
                'balance': user['balance'],
                'firstName': user['first_name']
            }
        })
    return jsonify({'success': False, 'user': None})

@app.route('/api/game', methods=['POST'])
def api_game():
    data = request.json
    user_id = data.get('telegramId')
    action = data.get('action')
    game_data = data.get('data', {})
    
    if action == 'updateBalance':
        balance = game_data.get('balance')
        update_balance(user_id, balance, 'add')
        return jsonify({'success': True})
    
    elif action == 'recordWin':
        win_amount = game_data.get('winAmount')
        update_balance(user_id, win_amount, 'add')
        conn = sqlite3.connect('bingo_bot.db')
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET total_won = total_won + ?, games_played = games_played + 1, games_won = games_won + 1 WHERE user_id = ?',
                       (win_amount, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    
    return jsonify({'success': False})

# ============================================
# TELEGRAM BOT HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = get_user(user.id)
    
    if not existing:
        create_user(user.id, user.username, user.first_name, user.last_name)
        if user.username and f"@{user.username}" == ADMIN_USERNAME:
            conn = sqlite3.connect('bingo_bot.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user.id,))
            conn.commit()
            conn.close()
            global ADMIN_ID
            ADMIN_ID = user.id
            await update.message.reply_text("✅ You are registered as ADMIN!")
    
    user_data = get_user(user.id)
    welcome = f"""
🎯 *WELCOME TO LOGO BING BINGO!*

Hello {user.first_name}! 👋

💰 *Balance:* {user_data['balance']:.2f} ETB
🎮 *Games Played:* {user_data['games_played']}
🏆 *Games Won:* {user_data['games_won']}

*Commands:*
/register - Create account
/balance - Check balance
/deposit - Deposit via Telebirr
/withdraw - Withdraw winnings
/play - Play Bingo 🎯
/instruction - How to play
/profile - Your stats
/help - All commands

🎮 *Ready?* Use /play to start!
    """
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = get_user(user.id)
    if existing:
        await update.message.reply_text(f"✅ Already registered! Balance: {existing['balance']:.2f} ETB")
    else:
        create_user(user.id, user.username, user.first_name, user.last_name)
        await update.message.reply_text("✅ Registration successful!")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if user_data:
        await update.message.reply_text(
            f"💰 *YOUR BALANCE*\n\n"
            f"💵 Available: *{user_data['balance']:.2f} ETB*\n"
            f"📈 Deposited: {user_data['total_deposited']:.2f} ETB\n"
            f"🏆 Won: {user_data['total_won']:.2f} ETB",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ Please /register first!")

async def instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""
🎯 *HOW TO PLAY*

1️⃣ Buy cards ({CARD_PRICE} ETB each, max 2)
2️⃣ Numbers called every 3 seconds
3️⃣ Tap matching numbers on your card
4️⃣ Complete: Row, Column, Diagonal, or Corners
5️⃣ Click BINGO! to win {WINNER_PERCENTAGE}% of prize pool

*Min Withdraw:* {MIN_WITHDRAW} ETB

Use /play to start!
    """
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("❌ Please /register first!")
        return
    
    session_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    game_url = f"{GAME_URL}/?user_id={user_id}&session={session_id}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎮 LAUNCH BINGO GAME 🎯", url=game_url)],
        [InlineKeyboardButton("💰 Balance", callback_data="balance"),
         InlineKeyboardButton("📖 Instructions", callback_data="instructions")]
    ])
    
    await update.message.reply_text(
        f"🎯 *PLAY LOGO BING BINGO*\n\n"
        f"💰 Balance: {user_data['balance']:.2f} ETB\n"
        f"🎮 Card Price: {CARD_PRICE} ETB (max 2)\n"
        f"🏆 Winner gets {WINNER_PERCENTAGE}% of pool\n\n"
        f"👇 Click below to play!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data:
        await update.message.reply_text("❌ Please /register first!")
        return
    
    win_rate = (user_data['games_won'] / user_data['games_played'] * 100) if user_data['games_played'] > 0 else 0
    text = f"""
👤 *PROFILE*

Name: {user_data['first_name']}
Username: @{user_data['username'] or 'N/A'}

💰 Balance: {user_data['balance']:.2f} ETB
🎮 Games: {user_data['games_played']}
🏆 Wins: {user_data['games_won']}
📈 Win Rate: {win_rate:.1f}%
💎 Total Won: {user_data['total_won']:.2f} ETB
    """
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = f"""
📚 *COMMANDS*

/start - Welcome
/register - Create account
/balance - Check balance
/deposit - Add funds (Telebirr {TELEBIRR_NUMBER})
/withdraw - Cash out
/play - Play Bingo
/instruction - Rules
/profile - Your stats

*Deposit:* Send to {TELEBIRR_NUMBER} ({OWNER_NAME}), then /deposit amount TXN_ID
*Withdraw:* /withdraw amount phone_number
    """
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💳 *DEPOSIT MONEY*\n\n"
        f"Send to Telebirr: *{TELEBIRR_NUMBER}*\n"
        f"Name: *{OWNER_NAME}*\n\n"
        f"Then send: `/deposit amount TRANSACTION_ID`\n"
        f"Example: `/deposit 100 TXN12345`\n\n"
        f"Minimum: 10 ETB",
        parse_mode=ParseMode.MARKDOWN
    )
    return DEPOSIT_STATE

async def handle_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    
    try:
        parts = update.message.text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ Format: /deposit amount TXN_ID")
            return DEPOSIT_STATE
        
        amount = float(parts[1])
        txn_id = parts[2]
        
        if amount < 10:
            await update.message.reply_text("❌ Minimum 10 ETB")
            return DEPOSIT_STATE
        
        request_id = add_deposit_request(user_id, amount, txn_id)
        
        await update.message.reply_text(
            f"✅ Deposit request #{request_id} created!\n"
            f"Amount: {amount:.2f} ETB\n"
            f"Pending admin approval @Fix6T"
        )
        
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Invalid amount")
        return DEPOSIT_STATE

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💸 *WITHDRAW*\n\n"
        f"Send: `/withdraw amount phone_number`\n"
        f"Example: `/withdraw 200 0912345678`\n\n"
        f"Minimum: {MIN_WITHDRAW} ETB",
        parse_mode=ParseMode.MARKDOWN
    )
    return WITHDRAW_STATE

async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    
    try:
        parts = update.message.text.split()
        if len(parts) < 3:
            await update.message.reply_text("❌ Format: /withdraw amount phone")
            return WITHDRAW_STATE
        
        amount = float(parts[1])
        phone = parts[2]
        
        user_data = get_user(user_id)
        if not user_data or user_data['balance'] < amount or amount < MIN_WITHDRAW:
            await update.message.reply_text("❌ Insufficient balance or below minimum")
            return WITHDRAW_STATE
        
        update_balance(user_id, amount, 'subtract')
        request_id = add_withdraw_request(user_id, amount, 'Telebirr', phone)
        
        await update.message.reply_text(
            f"✅ Withdrawal #{request_id} created!\n"
            f"Amount: {amount:.2f} ETB\n"
            f"Pending admin approval"
        )
        
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Invalid")
        return WITHDRAW_STATE

async def pending_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data or not user_data.get('is_admin', 0):
        await update.message.reply_text("❌ Admin only")
        return
    
    deposits = get_pending_deposits()
    message = "📋 *PENDING DEPOSITS*\n\n"
    for d in deposits[:10]:
        message += f"• #{d[0]} | {d[5]} | {d[2]:.2f} ETB | TXN: {d[3]}\n"
    
    if not deposits:
        message += "No pending deposits"
    
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

async def verify_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data or not user_data.get('is_admin', 0):
        await update.message.reply_text("❌ Admin only")
        return
    
    deposits = get_pending_deposits()
    keyboard = []
    for d in deposits[:10]:
        keyboard.append([InlineKeyboardButton(
            f"✅ Deposit #{d[0]} - {d[2]:.2f} ETB", 
            callback_data=f"dep_{d[0]}"
        )])
    
    if not keyboard:
        keyboard.append([InlineKeyboardButton("📭 No requests", callback_data="noop")])
    
    await update.message.reply_text(
        "🔐 *Admin Panel*\nSelect to approve:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("dep_"):
        request_id = int(data.split("_")[1])
        success, amount = verify_deposit(request_id, query.from_user.id)
        if success:
            await query.edit_message_text(f"✅ Deposit #{request_id} approved! {amount} ETB added.")
        else:
            await query.edit_message_text(f"❌ Failed to approve #{request_id}")

async def players_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data or not user_data.get('is_admin', 0):
        await update.message.reply_text("❌ Admin only")
        return
    
    conn = sqlite3.connect('bingo_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT first_name, username, balance, games_played, games_won FROM users ORDER BY balance DESC LIMIT 20')
    players = cursor.fetchall()
    conn.close()
    
    msg = "👥 *TOP PLAYERS*\n\n"
    for i, p in enumerate(players, 1):
        msg += f"{i}. {p[0]} @{p[1] or 'N/A'} | 💰 {p[2]:.2f} ETB\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled")
    return ConversationHandler.END

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "balance":
        await balance(update, context)
    elif query.data == "instructions":
        await instruction(update, context)

# ============================================
# RUN BOT
# ============================================

def run_bot():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("instruction", instruction))
    application.add_handler(CommandHandler("play", play))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("help", help_command))
    
    # Admin commands
    application.add_handler(CommandHandler("pending", pending_requests))
    application.add_handler(CommandHandler("verify", verify_menu))
    application.add_handler(CommandHandler("players", players_list))
    
    # Conversation handlers
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("deposit", deposit)],
        states={DEPOSIT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deposit)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("withdraw", withdraw)],
        states={WITHDRAW_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdraw)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    ))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^dep_"))
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    print("🤖 Bot is running!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

def run_web():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    init_db()
    print("🚀 Starting Logo Bing Bingo Bot...")
    
    # Run web server in background thread
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()
    
    # Run bot (this blocks)
    run_bot()
