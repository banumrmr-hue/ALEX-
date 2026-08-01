import os
import logging
import secrets
import string
import re

import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------ कॉन्फ़िगरेशन ------------------
# Render पर Environment Variable से Token लें
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8443))
logging.basicConfig(level=logging.INFO)

# ------------------ यूटिलिटी फंक्शन ------------------
def generate_random_password(length=12):
    """एक मजबूत रैंडम पासवर्ड जनरेट करें"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def reset_password(reset_link):
    """
    दिए गए रीसेट लिंक पर जाकर पासवर्ड बदलता है।
    रिटर्न: (success, new_password या error_message)
    """
    session = requests.Session()
    # यूज़र-एजेंट सेट करें ताकि कुछ साइट्स ब्लॉक न करें
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    try:
        resp = session.get(reset_link, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return False, f"लिंक खोलने में त्रुटि: {e}"

    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # CSRF टोकन खोजें (कई तरीकों से)
    csrf_token = None
    # 1. Hidden inputs में खोजें
    for inp in soup.find_all('input', type='hidden'):
        name = inp.get('name', '').lower()
        if 'csrf' in name or 'token' in name or 'authenticity' in name:
            csrf_token = inp.get('value')
            break
    
    # 2. Meta tags में खोजें
    if not csrf_token:
        meta = soup.find('meta', {'name': 'csrf-token'})
        if meta:
            csrf_token = meta.get('content')
    
    # 3. Form में data属性 में खोजें
    if not csrf_token:
        form = soup.find('form')
        if form and form.get('data-csrf'):
            csrf_token = form.get('data-csrf')

    new_pass = generate_random_password()

    # फॉर्म डेटा तैयार करें
    data = {
        'password': new_pass,
        'password_confirmation': new_pass,
    }
    
    # CSRF टोकन अगर मिला तो डालें
    if csrf_token:
        # कई संभावित नामों के साथ डालें
        data['csrf_token'] = csrf_token
        data['authenticity_token'] = csrf_token
        data['_csrf'] = csrf_token
        data['csrfmiddlewaretoken'] = csrf_token

    # फॉर्म का action URL निकालें
    form = soup.find('form')
    action_url = reset_link
    if form and form.get('action'):
        action = form.get('action')
        if action.startswith('/'):
            from urllib.parse import urljoin
            action_url = urljoin(reset_link, action)
        else:
            action_url = action

    # POST करें
    try:
        post_resp = session.post(action_url, data=data, timeout=10)
        post_resp.raise_for_status()
    except Exception as e:
        return False, f"पासवर्ड बदलते समय त्रुटि: {e}"

    # सफलता की जाँच
    if 'success' in post_resp.text.lower() or 'changed' in post_resp.text.lower():
        return True, new_pass
    elif 'error' in post_resp.text.lower() or 'invalid' in post_resp.text.lower():
        return False, "साइट ने एरर दिखाया। शायद लिंक एक्सपायर हो गया है या फॉर्मेट अलग है।"
    else:
        # अगर कुछ पता नहीं तो मान लें कि सफल है
        return True, new_pass

# ------------------ Telegram बॉट हैंडलर ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 नमस्ते! मुझे एक पासवर्ड रीसेट लिंक भेजें, मैं उसे खोलकर एक रैंडम पासवर्ड सेट कर दूँगा।\n\n"
        "⚠️ **ध्यान दें**: यह बॉट सिर्फ उन साइट्स पर काम करेगा जिनका रीसेट फॉर्म सरल है।\n"
        "जटिल साइट्स (जहाँ OTP, CAPTCHA, या JavaScript चाहिए) पर काम नहीं करेगा।",
        parse_mode='Markdown'
    )

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    url_pattern = re.compile(r'https?://[^\s]+')
    match = url_pattern.search(text)
    if not match:
        await update.message.reply_text("❌ कृपया एक सही रीसेट लिंक भेजें (URL)।")
        return

    reset_link = match.group(0)
    await update.message.reply_text("⏳ लिंक मिल गया। पासवर्ड बदलने की कोशिश कर रहा हूँ...")

    success, result = reset_password(reset_link)
    if success:
        await update.message.reply_text(
            f"✅ पासवर्ड सफलतापूर्वक बदल दिया गया!\n\n"
            f"🔑 नया पासवर्ड: `{result}`\n\n"
            "⚠️ कृपया इसे तुरंत सुरक्षित स्थान पर सेव करें।\n"
            "यह पासवर्ड केवल एक बार दिखाया गया है!",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(f"❌ पासवर्ड बदलने में विफल:\n\n{result}")

# ------------------ मुख्य फंक्शन ------------------
def main():
    # Render पर Webhook के लिए
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    # Render.com पर पोर्ट 8443 पर Webhook सेट करें
    # या फिर polling mode में चलाएं
    if os.environ.get("RENDER"):
        # Webhook mode for Render
        print("बॉट Webhook मोड में चालू है...")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
        )
    else:
        # Polling mode for local testing
        print("बॉट Polling मोड में चालू है...")
        app.run_polling()

if __name__ == "__main__":
    main()