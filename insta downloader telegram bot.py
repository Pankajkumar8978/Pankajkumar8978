import os
import logging
import instaloader
from telebot import TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading
import requests
from datetime import datetime

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize bot with your token
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your actual bot token
bot = TeleBot(BOT_TOKEN, threaded=True)

# Initialize Instaloader
L = instaloader.Instaloader(
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    post_metadata_txt_pattern='',
    max_connection_attempts=3
)

# Store user states
user_data = {}

class UserState:
    def __init__(self):
        self.url = None
        self.download_type = None
        self.post_shortcode = None

def get_post_shortcode(url):
    """Extract shortcode from Instagram URL."""
    try:
        # Handle different Instagram URL formats
        if '/p/' in url:
            shortcode = url.split('/p/')[1].split('/')[0].split('?')[0]
        elif '/reel/' in url:
            shortcode = url.split('/reel/')[1].split('/')[0].split('?')[0]
        elif '/tv/' in url:
            shortcode = url.split('/tv/')[1].split('/')[0].split('?')[0]
        else:
            return None
        return shortcode
    except:
        return None

def download_instagram_post(url, chat_id):
    """Download Instagram post (photo/video/carousel)."""
    folder_name = f"downloads_{chat_id}"
    os.makedirs(folder_name, exist_ok=True)
    
    try:
        shortcode = get_post_shortcode(url)
        if not shortcode:
            raise Exception("Invalid Instagram URL")
        
        # Get post
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        # Change directory for download
        original_dir = os.getcwd()
        os.chdir(folder_name)
        
        # Download post
        L.download_post(post, target=shortcode)
        
        os.chdir(original_dir)
        
        # Find downloaded files
        downloaded_files = []
        for file in os.listdir(folder_name):
            if file.startswith(shortcode):
                file_path = os.path.join(folder_name, file)
                # Skip txt files
                if file.endswith(('.jpg', '.mp4', '.png')):
                    downloaded_files.append(file_path)
        
        return downloaded_files, post.caption if post.caption else "Instagram Post"
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

def download_instagram_story(username, chat_id):
    """Download Instagram stories from a user."""
    folder_name = f"downloads_{chat_id}"
    os.makedirs(folder_name, exist_ok=True)
    
    try:
        # Get profile
        profile = instaloader.Profile.from_username(L.context, username)
        
        # Change directory for download
        original_dir = os.getcwd()
        os.chdir(folder_name)
        
        # Download stories
        downloaded_count = 0
        for story in L.get_stories(userids=[profile.userid]):
            for item in story.get_items():
                L.download_storyitem(item, target=username)
                downloaded_count += 1
        
        os.chdir(original_dir)
        
        if downloaded_count == 0:
            raise Exception("No stories available or account is private")
        
        # Find downloaded files
        downloaded_files = []
        for file in os.listdir(folder_name):
            file_path = os.path.join(folder_name, file)
            if file.endswith(('.jpg', '.mp4', '.png')):
                downloaded_files.append(file_path)
        
        return downloaded_files, f"Stories from @{username}"
    
    except Exception as e:
        logger.error(f"Story download error: {e}")
        raise

def download_instagram_profile_pic(username, chat_id):
    """Download Instagram profile picture in HD."""
    folder_name = f"downloads_{chat_id}"
    os.makedirs(folder_name, exist_ok=True)
    
    try:
        # Get profile
        profile = instaloader.Profile.from_username(L.context, username)
        
        # Download profile pic
        profile_pic_url = profile.profile_pic_url
        
        # Download the image
        response = requests.get(profile_pic_url, stream=True)
        response.raise_for_status()
        
        filename = os.path.join(folder_name, f"{username}_profile_pic.jpg")
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return [filename], f"Profile picture of @{username}"
    
    except Exception as e:
        logger.error(f"Profile pic download error: {e}")
        raise

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
📸 *Instagram Downloader Bot*

Welcome! I can help you download Instagram content.

*What I can download:*
• 📷 Photos
• 🎥 Videos
• 🎬 Reels
• 🎭 Stories (if public)
• 🖼️ Carousel posts
• 👤 Profile pictures (HD)

*How to use:*
1. Send me an Instagram URL
2. Choose what to download
3. Receive your files!

*Supported URLs:*
• Post: instagram.com/p/...
• Reel: instagram.com/reel/...
• Profile: instagram.com/username

Send me an Instagram URL to get started! 🚀
    """
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['download'])
def ask_for_url(message):
    bot.reply_to(message, "📎 Please send me the Instagram URL or username:")
    bot.register_next_step_handler(message, process_url)

@bot.message_handler(func=lambda message: 'instagram.com' in message.text.lower() or message.text.startswith('@'))
def handle_url_direct(message):
    process_url(message)

def process_url(message):
    chat_id = message.chat.id
    url = message.text.strip()
    
    # Initialize user state
    user_data[chat_id] = UserState()
    user_data[chat_id].url = url
    
    # Check if it's a username or URL
    if url.startswith('@') or ('instagram.com/' in url and '/p/' not in url and '/reel/' not in url and '/tv/' not in url):
        # It's a username or profile URL
        username = url.replace('@', '').replace('https://', '').replace('http://', '')
        username = username.replace('www.instagram.com/', '').replace('instagram.com/', '').strip('/')
        
        user_data[chat_id].url = username
        
        # Show options for username
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📸 Profile Picture", callback_data="type_profile_pic"),
            InlineKeyboardButton("📖 Stories", callback_data="type_stories")
        )
        
        bot.reply_to(message, f"✅ Username received: @{username}\n\nWhat would you like to download?", reply_markup=markup)
    
    elif 'instagram.com' in url:
        # It's a post/reel URL
        shortcode = get_post_shortcode(url)
        if not shortcode:
            bot.reply_to(message, "❌ Invalid Instagram URL. Please send a valid post/reel URL.")
            return
        
        user_data[chat_id].post_shortcode = shortcode
        
        # Show download option
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("⬇️ Download Post", callback_data="type_post"))
        
        bot.reply_to(message, "✅ URL received! Click below to download:", reply_markup=markup)
    
    else:
        bot.reply_to(message, "❌ Please send a valid Instagram URL or username (starting with @)")

@bot.callback_query_handler(func=lambda call: call.data.startswith('type_'))
def handle_download_type(call):
    chat_id = call.message.chat.id
    download_type = call.data.split('_', 1)[1]
    
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Session expired. Please send the URL again.")
        return
    
    user_data[chat_id].download_type = download_type
    bot.answer_callback_query(call.id)
    
    if download_type == 'post':
        bot.edit_message_text(
            "⬇️ Downloading post... Please wait.",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        threading.Thread(target=process_post_download, args=(chat_id, call.message.message_id)).start()
    
    elif download_type == 'profile_pic':
        bot.edit_message_text(
            "📸 Downloading profile picture... Please wait.",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        threading.Thread(target=process_profile_pic_download, args=(chat_id, call.message.message_id)).start()
    
    elif download_type == 'stories':
        bot.edit_message_text(
            "📖 Downloading stories... Please wait.",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        threading.Thread(target=process_stories_download, args=(chat_id, call.message.message_id)).start()

def process_post_download(chat_id, message_id):
    try:
        url = user_data[chat_id].url
        
        files, caption = download_instagram_post(url, chat_id)
        
        if not files:
            bot.edit_message_text(
                "❌ No media found. The post might be private or deleted.",
                chat_id=chat_id,
                message_id=message_id
            )
            return
        
        # Send files
        bot.edit_message_text(
            f"📤 Uploading {len(files)} file(s)... Please wait.",
            chat_id=chat_id,
            message_id=message_id
        )
        
        for i, file_path in enumerate(files):
            try:
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)
                
                if file_size > 2000 * 1024 * 1024:
                    bot.send_message(
                        chat_id,
                        f"⚠️ File {i+1} is too large ({file_size_mb:.1f}MB) to send."
                    )
                    continue
                
                with open(file_path, 'rb') as media:
                    if file_path.endswith('.mp4'):
                        bot.send_video(
                            chat_id,
                            media,
                            caption=f"✅ {caption}" if i == 0 else None,
                            supports_streaming=True,
                            timeout=300
                        )
                    else:
                        bot.send_photo(
                            chat_id,
                            media,
                            caption=f"✅ {caption}" if i == 0 else None,
                            timeout=300
                        )
                
                # Clean up individual file
                os.remove(file_path)
                
            except Exception as e:
                logger.error(f"Error sending file {file_path}: {e}")
                bot.send_message(chat_id, f"❌ Error uploading file {i+1}: {str(e)}")
        
        bot.delete_message(chat_id, message_id)
        
        # Clean up
        cleanup_user_data(chat_id)
        
    except Exception as e:
        logger.error(f"Error in process_post_download: {e}")
        bot.edit_message_text(
            f"❌ Error: {str(e)}\n\nThe account might be private or the post might be deleted.",
            chat_id=chat_id,
            message_id=message_id
        )
        cleanup_user_data(chat_id)

def process_profile_pic_download(chat_id, message_id):
    try:
        username = user_data[chat_id].url
        
        files, caption = download_instagram_profile_pic(username, chat_id)
        
        bot.edit_message_text(
            "📤 Uploading profile picture...",
            chat_id=chat_id,
            message_id=message_id
        )
        
        with open(files[0], 'rb') as photo:
            bot.send_photo(
                chat_id,
                photo,
                caption=f"✅ {caption}",
                timeout=300
            )
        
        bot.delete_message(chat_id, message_id)
        
        # Clean up
        os.remove(files[0])
        cleanup_user_data(chat_id)
        
    except Exception as e:
        logger.error(f"Error in process_profile_pic_download: {e}")
        bot.edit_message_text(
            f"❌ Error: {str(e)}\n\nMake sure the username is correct.",
            chat_id=chat_id,
            message_id=message_id
        )
        cleanup_user_data(chat_id)

def process_stories_download(chat_id, message_id):
    try:
        username = user_data[chat_id].url
        
        files, caption = download_instagram_story(username, chat_id)
        
        bot.edit_message_text(
            f"📤 Uploading {len(files)} story/stories...",
            chat_id=chat_id,
            message_id=message_id
        )
        
        for i, file_path in enumerate(files):
            try:
                with open(file_path, 'rb') as media:
                    if file_path.endswith('.mp4'):
                        bot.send_video(
                            chat_id,
                            media,
                            caption=f"✅ Story {i+1}" if i == 0 else None,
                            supports_streaming=True,
                            timeout=300
                        )
                    else:
                        bot.send_photo(
                            chat_id,
                            media,
                            caption=f"✅ Story {i+1}" if i == 0 else None,
                            timeout=300
                        )
                
                # Clean up individual file
                os.remove(file_path)
                
            except Exception as e:
                logger.error(f"Error sending story {file_path}: {e}")
        
        bot.delete_message(chat_id, message_id)
        
        # Clean up
        cleanup_user_data(chat_id)
        
    except Exception as e:
        logger.error(f"Error in process_stories_download: {e}")
        bot.edit_message_text(
            f"❌ Error: {str(e)}\n\nMake sure the account is public and has active stories.",
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
        "❓ Send me an Instagram URL or username, or use /start to see instructions."
    )

if __name__ == "__main__":
    print("🤖 Instagram Downloader Bot is running...")
    bot.infinity_polling()