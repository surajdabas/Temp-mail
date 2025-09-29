# telegram_bot.py

import logging
import json
import os
from pymailtm import MailTm, Account
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler
)

# --- Configuration ---
# Replace this with your bot token provided by BotFather.
BOT_TOKEN = "8214739360:AAFeDdGTTlPWP8SwuCmfnmepkrIQuZQxIkM"

# Replace this with your own Telegram user ID. You can get it from a bot like @userinfobot.
# This ID will be used to grant access to the admin panel.
ADMIN_ID = 7922285746 # TODO: Change this to your actual user ID

# File to store user accounts
DB_FILE = "db.json"

# Enable logging for a better understanding of the bot's behavior
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

# A simple in-memory dictionary to store user data.
# This will be loaded from and saved to the DB_FILE.
# The structure will be: {telegram_user_id: MailTm.Account}
user_accounts = {}
# Dictionary to store message details temporarily for full view
# Structure: {user_id: {message_id: message_object}}
user_inbox_cache = {}

# --- Data Persistence Helpers ---

def save_accounts():
    """Saves the user_accounts dictionary to a JSON file."""
    # We can't directly serialize the MailTm.Account object, so we convert it to a dictionary.
    data_to_save = {
        user_id: {
            'id': account.id_,
            'address': account.address,
            'password': account.password
        } for user_id, account in user_accounts.items()
    }
    with open(DB_FILE, 'w') as f:
        json.dump(data_to_save, f, indent=4)
    logging.info("User accounts saved to file.")

def load_accounts():
    """Loads user accounts from a JSON file into the user_accounts dictionary."""
    global user_accounts
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            try:
                data = json.load(f)
                # Reconstruct MailTm.Account objects from the saved data.
                user_accounts = {
                    int(user_id): Account(
                        id=details['id'],
                        address=details['address'],
                        password=details['password']
                    ) for user_id, details in data.items()
                }
                logging.info(f"Loaded {len(user_accounts)} user accounts from file.")
            except (json.JSONDecodeError, KeyError) as e:
                logging.error(f"Failed to load accounts from {DB_FILE}: {e}")
                user_accounts = {}
    else:
        logging.info("No existing user accounts file found.")
        user_accounts = {}

# --- UI Layouts ---

# Custom reply keyboard with buttons matching the image
main_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton("🚀 My Email")],
    [KeyboardButton("📝 Generate New Email"), KeyboardButton("📨 Inbox")],
    [KeyboardButton("📊 Status")]
], resize_keyboard=True)

# Confirmation keyboard for creating a new email
confirm_new_email_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("✅ Yes, create new", callback_data="confirm_new_email")],
    [InlineKeyboardButton("❌ No, keep my old email", callback_data="cancel_new_email")],
])

# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message and the custom keyboard when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hello, {user.mention_html()}! 👋\n"
        "I can provide you with a temporary email address. Use the buttons below to interact:",
        reply_markup=main_keyboard
    )

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the main menu keyboard."""
    await update.message.reply_html(
        "🎯 <b>Main Menu</b>\n\nChoose an option below:",
        reply_markup=main_keyboard
    )

async def hide_keyboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hides the custom keyboard."""
    await update.message.reply_text("Keyboard hidden. Use /menu to bring it back.", reply_markup=ReplyKeyboardRemove())

async def my_email_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends the user's current email address or prompts them to create one."""
    user_id = update.effective_user.id
    if user_id in user_accounts:
        await update.message.reply_html(
            f"🚀 <b>Your Current Email Address</b>\n\n"
            f"📧 <code>{user_accounts[user_id].address}</code>\n\n"
            f"✅ Status: <b>Active</b>\n"
            f"💡 You can use this email address to receive messages."
        )
    else:
        await update.message.reply_text(
            "❌ <b>No Email Address Found</b>\n\n"
            "You don't have a temporary email address yet. "
            "Please use the 'Generate New Email' button to create one.",
            parse_mode="HTML"
        )

async def new_email_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates a new temporary email address for the user."""
    user_id = update.effective_user.id
    if user_id in user_accounts:
        await update.message.reply_text(
            "⚠️ <b>Email Already Exists</b>\n\n"
            "You already have an active email address. Do you want to delete your current email and create a new one?",
            parse_mode="HTML",
            reply_markup=confirm_new_email_keyboard
        )
        return

    await update.message.reply_text("⏳ <b>Generating New Email...</b>", parse_mode="HTML")

    try:
        mt = MailTm()
        account = mt.get_account()
        user_accounts[user_id] = account
        save_accounts()
        
        await update.message.reply_html(
            "🎉 <b>Email Created Successfully!</b>\n\n"
            f"📧 Your new email: <code>{account.address}</code>\n\n"
            "✅ Status: <b>Active and Ready</b>\n"
            "📮 You can now receive emails at this address."
        )
    except Exception as e:
        logging.error(f"Error creating account for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ <b>Failed to Create Email</b>\n\n"
            "Sorry, we couldn't create a new email address right now. "
            "Please try again later.",
            parse_mode="HTML"
        )

async def check_inbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks the user's temporary email inbox for new messages."""
    user_id = update.effective_user.id
    if user_id not in user_accounts:
        await update.message.reply_text(
            "❌ <b>No Email Account</b>\n\n"
            "You need to create an email address first. "
            "Use 'Generate New Email' to get started!",
            parse_mode="HTML"
        )
        return
    
    account = user_accounts[user_id]
    await update.message.reply_text("📧 <b>Checking Inbox...</b>", parse_mode="HTML")
    
    try:
        messages = account.get_messages()
        
        if not messages:
            inbox_text = (
                "📭 <b>Inbox is Empty</b>\n\n"
                f"📧 Email: <code>{account.address}</code>\n"
                f"📮 Messages: <b>0</b>\n\n"
                "No new messages found."
            )
            await update.message.reply_html(inbox_text)
        else:
            user_inbox_cache[user_id] = {msg.id_: msg for msg in messages}
            inbox_text = f"📬 <b>You have {len(messages)} message(s)!</b>\n\n"
            for i, message in enumerate(messages):
                # Prepare a unique callback data for each message
                callback_data = f"read_email_{message.id_}"
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📖 Read Full Message", callback_data=callback_data)]
                ])
                
                message_preview = (
                    f"<b>📧 Message {i+1}:</b>\n"
                    f"👤 <b>From:</b> {message.from_['address']}\n"
                    f"📝 <b>Subject:</b> {message.subject}\n"
                    f"💬 <b>Preview:</b> {message.intro[:100]}{'...' if len(message.intro) > 100 else ''}\n"
                )
                
                await update.message.reply_html(message_preview, reply_markup=keyboard)
            
    except Exception as e:
        logging.error(f"Error checking inbox for user {user_id}: {e}")
        await update.message.reply_text(
            "❌ <b>Error Checking Inbox</b>\n\n"
            "Couldn't fetch your messages. Your account may have expired. "
            "Your account has been removed. Please create a new email address.",
            parse_mode="HTML"
        )
        if user_id in user_accounts:
            del user_accounts[user_id]
            save_accounts()

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the user's account status."""
    user_id = update.effective_user.id
    if user_id in user_accounts:
        account = user_accounts[user_id]
        try:
            messages = account.get_messages()
            status_text = (
                f"📊 <b>Account Status</b>\n\n"
                f"📧 <b>Email:</b> <code>{account.address}</code>\n"
                f"✅ <b>Status:</b> Active\n"
                f"📮 <b>Messages:</b> {len(messages)}\n"
                f"👤 <b>User ID:</b> <code>{user_id}</code>\n\n"
                f"🔄 <b>Last Checked:</b> Just now\n"
                f"⏰ <b>Account:</b> Temporary (may expire)"
            )
        except Exception:
            status_text = (
                f"📊 <b>Account Status</b>\n\n"
                f"❌ <b>Status:</b> Account may have expired\n"
                f"👤 <b>User ID:</b> <code>{user_id}</code>\n\n"
                f"💡 Please create a new email address."
            )
            if user_id in user_accounts:
                del user_accounts[user_id]
                save_accounts()
    else:
        status_text = (
            f"📊 <b>Account Status</b>\n\n"
            f"❌ <b>Status:</b> No active email\n"
            f"👤 <b>User ID:</b> <code>{user_id}</code>\n\n"
            f"📝 Use 'Generate New Email' to create an account!"
        )
    
    await update.message.reply_html(status_text)

# --- Admin Functions ---

async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the admin panel commands if the user is an admin."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    admin_text = (
        "🔧 <b>Admin Panel</b>\n\n"
        "Welcome, Admin! Here are your available commands:\n\n"
        "• /get_all_users - List all active users and their email addresses.\n"
        "• /stats - See bot usage statistics.\n"
        "• /broadcast [message] - Send a message to all active users.\n"
        "• /delete_account [user_id] - Delete a user's temporary account."
    )
    await update.message.reply_html(admin_text)

async def get_all_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to list all active users and their emails."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not user_accounts:
        await update.message.reply_text("👥 <b>Active Users</b>\n\n❌ No users have created temporary accounts yet.", parse_mode="HTML")
        return

    response_text = f"👥 <b>Active Users ({len(user_accounts)})</b>\n\n"
    for i, (telegram_id, account) in enumerate(user_accounts.items(), 1):
        response_text += (
            f"<b>{i}. User #{telegram_id}</b>\n"
            f"📧 <code>{account.address}</code>\n"
            f"{'─' * 25}\n"
        )
    
    await update.message.reply_html(response_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to show bot statistics."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    total_users = len(user_accounts)
    stats_text = (
        f"📊 <b>Bot Statistics</b>\n\n"
        f"👥 <b>Total Active Users:</b> {total_users}\n"
        f"📧 <b>Total Active Emails:</b> {total_users}\n"
        f"🤖 <b>Bot Status:</b> Online ✅\n"
        f"📈 <b>Performance:</b> Good\n"
        f"⚡ <b>Response Time:</b> Fast"
    )
    
    await update.message.reply_html(stats_text)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to broadcast a message to all users."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📢 <b>Broadcast Command</b>\n\n"
            "Please provide a message to broadcast.\n\n"
            "<b>Usage:</b> <code>/broadcast [Your message here]</code>",
            parse_mode="HTML"
        )
        return
    
    message_to_send = " ".join(context.args)
    if not user_accounts:
        await update.message.reply_text("❌ No users to broadcast to.", parse_mode="HTML")
        return
    
    success_count = 0
    for telegram_id in user_accounts:
        try:
            await context.bot.send_message(
                chat_id=telegram_id,
                text=f"📢 <b>Broadcast Message:</b>\n\n{message_to_send}",
                parse_mode="HTML"
            )
            success_count += 1
        except Exception as e:
            logging.error(f"Failed to send broadcast to user {telegram_id}: {e}")
    
    await update.message.reply_html(
        f"✅ <b>Broadcast Sent!</b>\n\n"
        f"📊 Delivered to {success_count}/{len(user_accounts)} users"
    )

async def delete_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to delete a specific user's temporary account."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    if not context.args:
        await update.message.reply_text(
            "🗑️ <b>Delete Account Command</b>\n\n"
            "Please provide a user ID to delete.\n\n"
            "<b>Usage:</b> <code>/delete_account [user_id]</code>",
            parse_mode="HTML"
        )
        return

    try:
        target_user_id = int(context.args[0])
        if target_user_id in user_accounts:
            account = user_accounts[target_user_id]
            is_deleted = account.delete_account()
            if is_deleted:
                del user_accounts[target_user_id]
                save_accounts()
                await update.message.reply_html(
                    f"✅ Account for user ID <code>{target_user_id}</code> deleted successfully."
                )
            else:
                await update.message.reply_html(
                    f"❌ Failed to delete the account for user ID <code>{target_user_id}</code>."
                )
        else:
            await update.message.reply_html(
                f"❌ User ID <code>{target_user_id}</code> not found or has no active account."
            )
    except (ValueError, KeyError) as e:
        await update.message.reply_text("❌ Invalid user ID provided.", parse_mode="HTML")
        logging.error(f"Error deleting account: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a help message with all available commands."""
    help_text = (
        "🤖 <b>My Email Bot - Help Guide</b>\n\n"
        "<b>User Commands:</b>\n"
        "• /start - Show the welcome message and keyboard.\n"
        "• /menu - Show the main menu keyboard.\n"
        "• /my_email - View your current temporary email address.\n"
        "• /new_email - Get a new disposable email address.\n"
        "• /check_inbox - Check your inbox for new messages.\n"
        "• /status - View your account status.\n"
        "• /hide_keyboard - Hide the main menu keyboard.\n"
        "• /help - Display this help message.\n\n"
        "<b>Admin Commands:</b>\n"
        "• /admin - Access the admin panel.\n"
        "• /get_all_users - List all active users.\n"
        "• /stats - View bot usage statistics.\n"
        "• /broadcast [message] - Send a message to all users.\n"
        "• /delete_account [user_id] - Delete a user's account.\n\n"
        "💡 <b>Tip:</b> You can use the buttons at the bottom of the screen for quick actions."
    )
    await update.message.reply_html(help_text, reply_markup=main_keyboard)

# Callback handler for inline buttons
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "confirm_new_email":
        old_account = user_accounts.get(user_id)
        if old_account:
            await query.edit_message_text("🗑️ Deleting your old email account...")
            try:
                is_deleted = old_account.delete_account()
                if is_deleted:
                    del user_accounts[user_id]
                    save_accounts()
                    await query.edit_message_text("✅ Old account deleted. Generating new email...")
                    # Now call the new email logic to create a fresh one
                    await new_email_logic(query, user_id)
                else:
                    await query.edit_message_text(
                        "❌ Failed to delete old account. Please try again or contact an admin.",
                        parse_mode="HTML"
                    )
            except Exception as e:
                logging.error(f"Error deleting old account for user {user_id}: {e}")
                await query.edit_message_text(
                    "❌ An error occurred while deleting your old account. Please try again.",
                    parse_mode="HTML"
                )
        else:
            await query.edit_message_text("No old account found. Generating new email...", parse_mode="HTML")
            await new_email_logic(query, user_id)
    elif query.data == "cancel_new_email":
        await query.edit_message_text("Keeping your current email. You can find it with /my_email.")
    elif query.data.startswith("read_email_"):
        message_id = query.data.split("_")[2]
        if user_id in user_inbox_cache and message_id in user_inbox_cache[user_id]:
            message = user_inbox_cache[user_id][message_id]
            full_message_text = (
                f"<b>📧 Full Message:</b>\n\n"
                f"👤 <b>From:</b> {message.from_['address']}\n"
                f"📝 <b>Subject:</b> {message.subject}\n\n"
                f"<b>Message Content:</b>\n"
                f"{message.text}"
            )
            # The original message might be too long, so we split it into multiple parts if necessary
            for i in range(0, len(full_message_text), 4096):
                await context.bot.send_message(
                    chat_id=user_id,
                    text=full_message_text[i:i+4096],
                    parse_mode="HTML"
                )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text="❌ Error: Could not find that message. It might have expired from the cache. Please use /check_inbox again.",
                parse_mode="HTML"
            )

async def new_email_logic(query, user_id):
    """Logic to generate a new email, separated for reuse."""
    await query.edit_message_text("⏳ <b>Generating New Email...</b>", parse_mode="HTML")
    try:
        mt = MailTm()
        account = mt.get_account()
        user_accounts[user_id] = account
        save_accounts()
        
        await query.edit_message_text(
            "🎉 <b>Email Created Successfully!</b>\n\n"
            f"📧 Your new email: <code>{account.address}</code>\n\n"
            "✅ Status: <b>Active and Ready</b>\n"
            "📮 You can now receive emails at this address.",
            parse_mode="HTML"
        )
    except Exception as e:
        logging.error(f"Error creating new account for user {user_id}: {e}")
        await query.edit_message_text(
            "❌ <b>Failed to Create Email</b>\n\n"
            "Sorry, we couldn't create a new email address right now. "
            "Please try again later.",
            parse_mode="HTML"
        )
    
# The main function to set up and run the bot
def main():
    """Start the bot."""
    load_accounts()
    application = Application.builder().token(BOT_TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("hide_keyboard", hide_keyboard_command))
    
    # Message handlers for the keyboard buttons
    application.add_handler(MessageHandler(filters.Regex("^🚀 My Email$"), my_email_command))
    application.add_handler(MessageHandler(filters.Regex("^📝 Generate New Email$"), new_email_command))
    application.add_handler(MessageHandler(filters.Regex("^📨 Inbox$"), check_inbox_command))
    application.add_handler(MessageHandler(filters.Regex("^📊 Status$"), status_command))

    # Register admin-specific command handlers
    application.add_handler(CommandHandler("admin", admin_panel_command))
    application.add_handler(CommandHandler("get_all_users", get_all_users_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("delete_account", delete_account_command))
    
    # Register callback query handler for inline buttons
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
