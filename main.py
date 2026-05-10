# main.py - Logo Bing Bingo Bot
# PRODUCTION READY - Render Deployment Version
# ✅ NO erroneous imports - completely clean

import os
import sqlite3
import random
import string
import threading
from datetime import datetime
from flask import Flask, request, jsonify

# Telegram imports - correct and complete
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.constants import ParseMode

# ============================================
# CONFIGURATION (Use Environment Variables for Production)
# ============================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "8575015302:AAFnH6MKdm4uJEMnbN_0Krz0NW9J3DG4D38")
GAME_URL = os.getenv("GAME_URL", "https://logo-bingo-game.vercel.app")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@Fix6T")
TELEBIRR_NUMBER = os.getenv("TELEBIRR_NUMBER", "0931721793")
OWNER_NAME = os.getenv("OWNER_NAME", "Wendesen Tamene")

CARD_PRICE = int(os.getenv("CARD_PRICE", "10"))
MIN_WITHDRAW = int(os.getenv("MIN_WITHDRAW", "50"))
WINNER_PERCENTAGE = int(os.getenv("WINNER_PERCENTAGE", "70"))

PORT = int(os.getenv("PORT", 8080))

print("🎯 Logo Bing Bingo Bot Starting...")
print(f"🤖 Token: {'✅' if BOT_TOKEN else '❌'}")

# Conversation states
DEPOSIT_STATE = 1
WITHDRAW_STATE = 2

app = Flask(__name__)
ADMIN_ID = None

# ============================================
# DATABASE (Thread-Safe SQLite)
# ============================================

def get_db_connection():
    """Get a thread-safe database connection"""
    conn = sqlite3.connect('bingo_bot.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance REAL DEFAULT 0,
        total_deposited REAL DEFAULT 0,
        total_withdrawn REAL DEFAULT 0,
        total_won REAL DEFAULT 0,
        games_played INTEGER DEFAULT 0,
        games_won INTEGER DEFAULT 0,
        registered_date TEXT,
        is_admin INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposit_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        transaction_id TEXT,
        status TEXT DEFAULT 'pending',
        request_date TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ Database ready")

def get_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def create_user(user_id, username, first_name):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (user_id, username, first_name, registered_date) VALUES (?, ?, ?, ?)',
                  (user_id, username or '', first_name, datetime.now().isoformat()))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return False
    finally:
        conn.close()

def update_balance(user_id, amount):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if row:
        new_balance = row['balance'] + amount
        c.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
        conn.commit()
    conn.close()

def add_deposit_request(user_id, amount, txn_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO deposit_requests (user_id, amount, transaction_id, request_date) VALUES (?, ?, ?, ?)',
              (user_id, amount, txn_id, datetime.now().isoformat()))
    rid = c.lastrowid
    conn.commit()
    conn.close()
    return rid

def get_pending_deposits():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT id, user_id, amount, transaction_id FROM deposit_requests WHERE status = "pending"')
    rows = c.fetchall()
    conn.close()
    return rows

def approve_deposit(req_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('SELECT user_id, amount FROM deposit_requests WHERE id = ?', (req_id,))
    row = c.fetchone()
    if row:
        user_id, amount = row['user_id'], row['amount']
        c.execute('UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id = ?',
                  (amount, amount, user_id))
        c.execute('UPDATE deposit_requests SET status = "approved" WHERE id = ?', (req_id,))
        conn.commit()
        conn.close()
        return True, amount
    conn.close()
    return False, 0

# ============================================
# FLASK API
# ============================================

@app.route('/')
def index():
    return jsonify({'status': 'online', 'bot': 'Logo Bing Bingo'})

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/api/user/<int:user_id>')
def get_user_api(user_id):
    user = get_user(user_id)
    if user:
        return jsonify({'success': True, 'user': {'userId': user_id, 'balance': user['balance'], 'firstName': user['first_name']}})
    return jsonify({'success': False, 'user': None}), 404

@app.route('/api/game', methods=['POST'])
def game_api():
    data = request.json or {}
    user_id = data.get('telegramId')
    action = data.get('action')
    if action == 'recordWin':
        win_amount = data.get('data', {}).get('winAmount', 0)
        if win_amount > 0:
            update_balance(user_id, win_amount)
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

# ============================================
# TELEGRAM COMMANDS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not get_user(user.id):
        create_user(user.id, user.username, user.first_name)
        if user.username and f"@{user.username}" == ADMIN_USERNAME:
            global ADMIN_ID
            ADMIN_ID = user.id
    u = get_user(user.id)
    await update.message.reply_text(
        f"🎯 *WELCOME!*\n\nHello {user.first_name}!\n💰 Balance: {u['balance']:.2f} ETB\n\n"
        f"Commands:\n/play - Start game\n/deposit - Add funds\n/withdraw - Cash out\n/balance - Check balance",
        parse_mode=ParseMode.MARKDOWN)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if not u:
        await update.message.reply_text("❌ Send /register first")
        return
    game_url = f"{GAME_URL}/?user_id={user_id}"
    keyboard = [[InlineKeyboardButton("🎮 PLAY BINGO 🎯", url=game_url)]]
    await update.message.reply_text(f"💰 Balance: {u['balance']:.2f} ETB\n👇 Click to play!",
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = get_user(update.effective_user.id)
    if u:
        await update.message.reply_text(f"💰 *Balance:* {u['balance']:.2f} ETB", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text("❌ Send /register first")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if get_user(user.id):
        await update.message.reply_text("✅ Already registered!")
    else:
        create_user(user.id, user.username, user.first_name)
        await update.message.reply_text("✅ Registered! Use /play to start.")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"💳 *DEPOSIT*\n\nSend to Telebirr: {TELEBIRR_NUMBER}\nName: {OWNER_NAME}\n\n"
        f"Then send: `/deposit amount TXN_ID`\nExample: `/deposit 100 TXN123`",
        parse_mode=ParseMode.MARKDOWN)
    return DEPOSIT_STATE

async def handle_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.split()
        amount = float(parts[1])
        txn = parts[2]
        if amount < CARD_PRICE:
            await update.message.reply_text(f"❌ Minimum {CARD_PRICE} ETB")
            return DEPOSIT_STATE
        rid = add_deposit_request(update.effective_user.id, amount, txn)
        await update.message.reply_text(f"✅ Deposit #{rid} created! Pending admin approval.")
        if ADMIN_ID:
            await context.bot.send_message(ADMIN_ID, f"🔔 Deposit #{rid}: {amount} ETB from @{update.effective_user.username}")
        return ConversationHandler.END
    except IndexError:
        await update.message.reply_text("❌ Format: /deposit amount TXN_ID")
        return DEPOSIT_STATE
    except ValueError:
        await update.message.reply_text("❌ Amount must be a number")
        return DEPOSIT_STATE
    except Exception as e:
        print(f"❌ Deposit error: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")
        return DEPOSIT_STATE

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"💸 *WITHDRAW*\n\nSend: `/withdraw amount phone`\nExample: `/withdraw 200 0912345678`\nMinimum: {MIN_WITHDRAW} ETB",
                                    parse_mode=ParseMode.MARKDOWN)
    return WITHDRAW_STATE

async def handle_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.split()
        amount = float(parts[1])
        phone = parts[2]
        u = get_user(update.effective_user.id)
        if not u or u['balance'] < amount or amount < MIN_WITHDRAW:
            await update.message.reply_text(f"❌ Insufficient funds or below minimum ({MIN_WITHDRAW} ETB)")
            return WITHDRAW_STATE
        update_balance(update.effective_user.id, -amount)
        await update.message.reply_text(f"✅ Withdrawal request sent! Pending admin approval.")
        if ADMIN_ID:
            await context.bot.send_message(ADMIN_ID, f"🔔 Withdrawal: {amount} ETB to {phone} from @{update.effective_user.username}")
        return ConversationHandler.END
    except IndexError:
        await update.message.reply_text("❌ Format: /withdraw amount phone")
        return WITHDRAW_STATE
    except ValueError:
        await update.message.reply_text("❌ Amount must be a number")
        return WITHDRAW_STATE
    except Exception as e:
        print(f"❌ Withdraw error: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again.")
        return WITHDRAW_STATE

async def pending_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only")
        return
    deposits = get_pending_deposits()
    if not deposits:
        await update.message.reply_text("No pending deposits")
        return
    msg = "📋 *Pending deposits:*\n"
    for d in deposits:
        msg += f"ID {d['id']}: {d['amount']} ETB (User {d['user_id']})\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def verify_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only")
        return
    deposits = get_pending_deposits()
    if not deposits:
        await update.message.reply_text("No pending deposits")
        return
    keyboard = []
    for d in deposits:
        keyboard.append([InlineKeyboardButton(f"Approve #{d['id']} - {d['amount']} ETB", callback_data=f"app_{d['id']}")])
    await update.message.reply_text("Select deposit to approve:", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("❌ Admin only")
        return
    if query.data.startswith("app_"):
        rid = int(query.data.split("_")[1])
        success, amount = approve_deposit(rid)
        if success:
            await query.edit_message_text(f"✅ Deposit #{rid} approved! {amount} ETB added.")
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT user_id FROM deposit_requests WHERE id = ?', (rid,))
            row = c.fetchone()
            conn.close()
            if row:
                try:
                    await context.bot.send_message(row['user_id'], f"✅ Your deposit of {amount} ETB has been approved!")
                except:
                    pass
        else:
            await query.edit_message_text(f"❌ Failed to approve #{rid}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled")
    return ConversationHandler.END

# ============================================
# MAIN ENTRY POINT
# ============================================

def run_bot():
    """Run the Telegram bot"""
    app_bot = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("play", play))
    app_bot.add_handler(CommandHandler("balance", balance_cmd))
    app_bot.add_handler(CommandHandler("register", register))
    app_bot.add_handler(CommandHandler("pending", pending_admin))
    app_bot.add_handler(CommandHandler("verify", verify_admin))
    
    # Conversation handlers
    app_bot.add_handler(ConversationHandler(
        entry_points=[CommandHandler("deposit", deposit)], 
        states={DEPOSIT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_deposit)]},
        fallbacks=[CommandHandler("cancel", cancel)]))
    
    app_bot.add_handler(ConversationHandler(
        entry_points=[CommandHandler("withdraw", withdraw)], 
        states={WITHDRAW_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_withdraw)]},
        fallbacks=[CommandHandler("cancel", cancel)]))
    
    # Callback handler for admin buttons
    app_bot.add_handler(CallbackQueryHandler(admin_callback, pattern="^app_"))
    
    print("🤖 Bot is running!")
    app_bot.run_polling(allowed_updates=Update.ALL_TYPES)

def run_web():
    """Run the Flask web server"""
    app.run(host='0.0.0.0', port=PORT)

if __name__ == '__main__':
    init_db()
    print("🚀 Starting Logo Bing Bingo Bot...")
    
    # Start Flask in a background thread
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    
    # Run Telegram bot (blocks main thread)
    run_bot()
