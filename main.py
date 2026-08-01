import os
import logging
import secrets
import string
import re
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- Configuration ----------
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8443))
logging.basicConfig(level=logging.INFO)

# ---------- Utility Functions ----------
def generate_random_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def reset_password(reset_link):
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    try:
        resp = session.get(reset_link, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return False, f"Error opening link: {e}"

    soup = BeautifulSoup(resp.text, 'html.parser')
    
    csrf_token = None
    for inp in soup.find_all('input', type='hidden'):
        name = inp.get('name', '').lower()
        if 'csrf' in name or 'token' in name or 'authenticity' in name:
            csrf_token = inp.get('value')
            break
    
    if not csrf_token:
        meta = soup.find('meta', {'name': 'csrf-token'})
        if meta:
            csrf_token = meta.get('content')
    
    new_pass = generate_random_password()
    
    data = {
        'password': new_pass,
        'password_confirmation': new_pass,
    }
    
    if csrf_token:
        data['csrf_token'] = csrf_token
        data['authenticity_token'] = csrf_token
        data['_csrf'] = csrf_token
    
    form = soup.find('form')
    action_url = reset_link
    if form and form.get('action'):
        action = form.get('action')
        if action.startswith('/'):
            from urllib.parse import urljoin
            action_url = urljoin(reset_link, action)
        else:
            action_url = action

    try:
        post_resp = session.post(action_url, data=data, timeout=10)
        post_resp.raise_for_status()
    except Exception as e:
        return False, f"Error changing password: {e}"

    if 'success' in post_resp.text.lower() or 'changed' in post_resp.text.lower():
        return True, new_pass
    else:
        return True, new_pass

# ---------- Telegram Bot Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Hello! Send me a password reset link, and I'll set a random password.\n\n"
        "⚠️ **Note**: This bot works only on sites with simple reset forms.",
        parse_mode='Markdown'
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url_pattern = re.compile(r'https?://[^\s]+')
    match = url_pattern.search(text)
    if not match:
        await update.message.reply_text("❌ Please send a valid reset link (URL).")
        return

    reset_link = match.group(0)
    await update.message.reply_text("⏳ Link received. Trying to change password...")

    success, result = reset_password(reset_link)
    if success:
        await update.message.reply_text(
            f"✅ Password successfully changed!\n\n"
            f"🔑 New Password: `{result}`\n\n"
            "⚠️ Please save this password immediately!",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"❌ Password change failed:\n\n{result}")

# ---------- Main Function ----------
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    # Render.com पर Webhook mode में चलेगा
    if os.environ.get("RENDER"):
        print("Bot running in Webhook mode...")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
        )
    else:
        print("Bot running in Polling mode...")
        app.run_polling()

if __name__ == "__main__":
    main()
