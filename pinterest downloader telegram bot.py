import os
import logging
import requests
from telebot import TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import json
import re
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize bot with your token
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your actual bot token
bot = TeleBot(BOT_TOKEN, threaded=True)

# Store user states
user_data = {}

class UserState:
    def __init__(self):
        self.url = None
        self.media_type = None
        self.media_url = None

def get_pinterest_media_rapidapi(url):
    """Method 1: Using RapidAPI Pinterest Downloader (Free tier available)"""
    try:
        # You need to get free API key from RapidAPI
        # Sign up at: https://rapidapi.com/
        # Search for "Pinterest Downloader" and get API key
        
        api_url = "https://pinterest-downloader-download-pinterest-videos-or-images.p.rapidapi.com/pinterest"
        
        headers = {
            "X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY_HERE",  # Replace with your RapidAPI key
            "X-RapidAPI-Host": "pinterest-downloader-download-pinterest-videos-or-images.p.rapidapi.com"
        }
        
        querystring = {"url": url}
        
        response = requests.get(api_url, headers=headers, params=querystring, timeout=15)
        data = response.json()
        
        if data.get('success'):
            media_type = data.get('type', 'image')  # 'video' or 'image'
            media_url = data.get('url') or data.get('image')
            title = data.get('title', 'Pinterest Media')
            
            return media_type, media_url, title
        
        return None, None, None
        
    except Exception as e:
        logger.error(f"RapidAPI method error: {e}")
        return None, None, None

def get_pinterest_media_scraping(url):
    """Method 2: Web scraping method (backup)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        # Follow redirects for pin.it links
        if 'pin.it' in url:
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=10)
            url = response.url
        
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Try to find video
        video_tag = soup.find('video')
        if video_tag and video_tag.get('src'):
            return 'video', video_tag.get('src'), 'Pinterest Video'
        
        # Try to find image with og:image meta tag
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image.get('content')
            # Get highest quality version
            image_url = image_url.replace('236x', 'originals').replace('474x', 'originals')
            return 'image', image_url, 'Pinterest Image'
        
        # Try to find img tag with high resolution
        img_tags = soup.find_all('img')
        for img in img_tags:
            src = img.get('src', '')
            if 'pinimg.com' in src and 'originals' in src:
                return 'image', src, 'Pinterest Image'
        
        return None, None, None
        
    except Exception as e:
        logger.error(f"Scraping method error: {e}")
        return None, None, None

def get_pinterest_media_api2(url):
    """Method 3: Using another free API"""
    try:
        # Using pinterestdownloader.io API
        api_url = "https://www.pinterestdownloader.com/frontendv2/get_url.php"
        
        payload = {
            'url': url
        }
        
        response = requests.post(api_url, data=payload, timeout=15)
        data = response.json()
        
        if data.get('status') == 'success':
            media_type = 'video' if data.get('type') == 'video' else 'image'
            media_url = data.get('image_url') or data.get('video_url')
            title = data.get('title', 'Pinterest Media')
            
            return media_type, media_url, title
        
        return None, None, None
        
    except Exception as e:
        logger.error(f"API2 method error: {e}")
        return None, None, None

def get_pinterest_media_info(url):
    """Try multiple methods to get Pinterest media"""
    
    # Method 1: Try scraping first (no API key needed)
    logger.info("Trying scraping method...")
    media_type, media_url, title = get_pinterest_media_scraping(url)
    if media_url:
        return media_type, media_url, title
    
    # Method 2: Try alternative API
    logger.info("Trying alternative API...")
    media_type, media_url, title = get_pinterest_media_api2(url)
    if media_url:
        return media_type, media_url, title
    
    # Method 3: Try RapidAPI (if configured)
    logger.info("Trying RapidAPI...")
    media_type, media_url, title = get_pinterest_media_rapidapi(url)
    if media_url:
        return media_type, media_url, title
    
    return None, None, None

def download_pinterest_media(media_url, media_type, chat_id, title):
    """Download Pinterest media (image or video)."""
    folder_name = f"downloads_{chat_id}"
    os.makedirs(folder_name, exist_ok=True)
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.pinterest.com/'
        }
        
        response = requests.get(media_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        # Determine file extension from content-type or URL
        content_type = response.headers.get('content-type', '')
        if 'video' in content_type or media_type == 'video':
            extension = '.mp4'
        elif 'gif' in content_type:
            extension = '.gif'
        else:
            extension = '.jpg'
        
        # Clean filename
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
        filename = os.path.join(folder_name, f"{safe_title}{extension}")
        
        # Download file
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return filename
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
📌 *Pinterest Downloader Bot*

Welcome! I can help you download Pinterest content in HD quality.

*What I can download:*
• 📷 Images (High quality)
• 🎥 Videos (HD quality)
• 🖼️ GIFs

*How to use:*
1. Send me a Pinterest URL
2. I'll fetch the media
3. Receive your file in HD!

*Supported URLs:*
• Pin: pinterest.com/pin/...
• Short URL: pin.it/...

*Features:*
✅ High quality downloads
✅ Fast & reliable
✅ No watermarks
✅ Videos & Images support

*Example URLs:*
`https://www.pinterest.com/pin/123456789/`
`https://pin.it/abc123`

Send me a Pinterest URL to get started! 🚀

*Note:* Make sure the pin is public!
    """
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['download'])
def ask_for_url(message):
    bot.reply_to(message, "📎 Please send me the Pinterest URL:")
    bot.register_next_step_handler(message, process_url)

@bot.message_handler(func=lambda message: 'pinterest.com' in message.text.lower() or 'pin.it' in message.text.lower())
def handle_url_direct(message):
    process_url(message)

def process_url(message):
    chat_id = message.chat.id
    url = message.text.strip()
    
    # Validate URL
    if 'pinterest.com' not in url and 'pin.it' not in url:
        bot.reply_to(message, "❌ Invalid URL. Please send a valid Pinterest URL.")
        return
    
    # Initialize user state
    user_data[chat_id] = UserState()
    user_data[chat_id].url = url
    
    status_msg = bot.reply_to(message, "🔍 Analyzing Pinterest URL... Please wait.")
    threading.Thread(target=process_single_pin, args=(chat_id, status_msg.message_id)).start()

def process_single_pin(chat_id, message_id):
    try:
        url = user_data[chat_id].url
        
        # Get media info using multiple methods
        media_type, media_url, title = get_pinterest_media_info(url)
        
        if not media_url:
            bot.edit_message_text(
                "❌ Could not fetch media. Possible reasons:\n\n"
                "• Pin might be private\n"
                "• URL is incorrect\n"
                "• Pinterest blocked the request\n\n"
                "Try:\n"
                "1. Make sure the pin is public\n"
                "2. Use direct pinterest.com/pin/... URL\n"
                "3. Try a different pin",
                chat_id=chat_id,
                message_id=message_id
            )
            cleanup_user_data(chat_id)
            return
        
        # Update status
        media_icon = "🎥" if media_type == "video" else "📷"
        bot.edit_message_text(
            f"{media_icon} Found {media_type}! Downloading... Please wait.",
            chat_id=chat_id,
            message_id=message_id
        )
        
        # Download media
        filename = download_pinterest_media(media_url, media_type, chat_id, title)
        
        # Check file size
        file_size = os.path.getsize(filename)
        file_size_mb = file_size / (1024 * 1024)
        
        if file_size > 2000 * 1024 * 1024:
            bot.edit_message_text(
                f"⚠️ File is too large ({file_size_mb:.1f}MB) to send via Telegram (max 2GB).",
                chat_id=chat_id,
                message_id=message_id
            )
            os.remove(filename)
            cleanup_user_data(chat_id)
            return
        
        # Update status
        bot.edit_message_text(
            f"📤 Uploading {media_type} ({file_size_mb:.1f}MB)... Please wait.",
            chat_id=chat_id,
            message_id=message_id
        )
        
        # Send media
        with open(filename, 'rb') as media:
            if media_type == 'video':
                bot.send_video(
                    chat_id,
                    media,
                    caption=f"✅ {title}",
                    supports_streaming=True,
                    timeout=300
                )
            else:
                bot.send_photo(
                    chat_id,
                    media,
                    caption=f"✅ {title}",
                    timeout=300
                )
        
        bot.delete_message(chat_id, message_id)
        
        # Clean up
        os.remove(filename)
        cleanup_user_data(chat_id)
        
    except Exception as e:
        logger.error(f"Error in process_single_pin: {e}")
        bot.edit_message_text(
            f"❌ Error: {str(e)}\n\n"
            "Please try:\n"
            "1. Different pin URL\n"
            "2. Make sure pin is public\n"
            "3. Check if URL is correct",
            chat_id=chat_id,
            message_id=message_id
        )
        cleanup_user_data(chat_id)

def cleanup_user_data(chat_id):
    """Clean up user data and folders."""
    if chat_id in user_data:
        del user_data[chat_id]
    
    folder_name = f"downloads_{chat_id}"
    if os.path.exists(folder_name):
        # Remove any remaining files
        for file in os.listdir(folder_name):
            try:
                os.remove(os.path.join(folder_name, file))
            except:
                pass
        # Remove folder
        try:
            os.rmdir(folder_name)
        except:
            pass

@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    bot.reply_to(
        message,
        "❓ Send me a Pinterest URL or use /start to see instructions.\n\n"
        "Example: https://www.pinterest.com/pin/123456789/"
    )

if __name__ == "__main__":
    print("🤖 Pinterest Downloader Bot is running...")
    print("📌 Using multiple download methods for better success rate")
    bot.infinity_polling()