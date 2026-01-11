import os
import logging
from yt_dlp import YoutubeDL
from telebot import TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading

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
        self.download_type = None
        self.resolution = None
        self.resolutions = {}
        self.is_playlist = False

def get_available_resolutions(video_url):
    """Fetch available video resolutions."""
    ydl_opts = {
        'no_proxy': True,
        'quiet': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=False)
            
            if 'entries' in info_dict and info_dict['entries']:
                first_video = info_dict['entries'][0]
                formats = first_video.get('formats', [])
            else:
                formats = info_dict.get('formats', [])
            
            # Get unique resolutions
            resolutions = {}
            for fmt in formats:
                if 'height' in fmt and fmt['height']:
                    res = f"{fmt['height']}p"
                    if res not in resolutions.values():
                        resolutions[fmt['format_id']] = res
            
            return resolutions, 'entries' in info_dict
    except Exception as e:
        logger.error(f"Error fetching resolutions: {e}")
        return {}, False

def download_video_with_ytdlp(video_url, selected_resolution, chat_id):
    """Download video at or below selected resolution."""
    folder_name = f"downloads_{chat_id}"
    os.makedirs(folder_name, exist_ok=True)
    
    ydl_opts = {
        'no_proxy': True,
        'format': f'bestvideo[height<={selected_resolution[:-1]}]+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': os.path.join(folder_name, '%(title)s.%(ext)s'),
        'quiet': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

def download_audio_as_mp3(video_url, chat_id):
    """Download only audio as MP3."""
    folder_name = f"downloads_{chat_id}"
    os.makedirs(folder_name, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(folder_name, '%(title)s.%(ext)s'),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        },
    }
    
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filename = os.path.splitext(ydl.prepare_filename(info))[0] + '.mp3'
            return filename
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = """
🎥 *YouTube Downloader Bot*

Welcome! I can help you download YouTube videos and audio.

*Commands:*
/start - Start the bot
/download - Download a video or audio

*How to use:*
1. Send me a YouTube URL
2. Choose video or audio
3. Select quality (for videos)
4. Receive your file!

Send me a YouTube URL to get started! 🚀
    """
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(commands=['download'])
def ask_for_url(message):
    bot.reply_to(message, "📎 Please send me the YouTube video or playlist URL:")
    bot.register_next_step_handler(message, process_url)

@bot.message_handler(func=lambda message: 'youtube.com' in message.text or 'youtu.be' in message.text)
def handle_url_direct(message):
    process_url(message)

def process_url(message):
    chat_id = message.chat.id
    video_url = message.text.strip()
    
    # Convert shorts URL
    if "youtube.com/shorts/" in video_url:
        video_url = video_url.replace("youtube.com/shorts/", "youtube.com/watch?v=")
    
    # Validate URL
    if 'youtube.com' not in video_url and 'youtu.be' not in video_url:
        bot.reply_to(message, "❌ Invalid URL. Please send a valid YouTube URL.")
        return
    
    # Initialize user state
    user_data[chat_id] = UserState()
    user_data[chat_id].url = video_url
    
    # Show download type options
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎬 Video", callback_data="type_video"),
        InlineKeyboardButton("🎵 MP3 Audio", callback_data="type_mp3")
    )
    
    bot.reply_to(message, "✅ URL received! What would you like to download?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('type_'))
def handle_download_type(call):
    chat_id = call.message.chat.id
    download_type = call.data.split('_')[1]
    
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Session expired. Please send the URL again.")
        return
    
    user_data[chat_id].download_type = download_type
    bot.answer_callback_query(call.id)
    
    if download_type == 'mp3':
        # Start MP3 download
        bot.edit_message_text(
            "🎵 Downloading audio... Please wait.",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        threading.Thread(target=process_mp3_download, args=(chat_id,)).start()
    
    elif download_type == 'video':
        # Fetch resolutions
        bot.edit_message_text(
            "🔍 Fetching available resolutions...",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        threading.Thread(target=fetch_and_show_resolutions, args=(chat_id, call.message.message_id)).start()

def fetch_and_show_resolutions(chat_id, message_id):
    try:
        url = user_data[chat_id].url
        resolutions, is_playlist = get_available_resolutions(url)
        
        if not resolutions:
            bot.edit_message_text(
                "❌ Could not fetch video information. Please try again.",
                chat_id=chat_id,
                message_id=message_id
            )
            return
        
        user_data[chat_id].resolutions = resolutions
        user_data[chat_id].is_playlist = is_playlist
        
        # Create resolution buttons
        markup = InlineKeyboardMarkup(row_width=2)
        unique_resolutions = sorted(set(resolutions.values()), key=lambda x: int(x[:-1]), reverse=True)
        
        buttons = []
        for res in unique_resolutions[:10]:  # Limit to 10 resolutions
            buttons.append(InlineKeyboardButton(res, callback_data=f"res_{res}"))
        
        # Add buttons in pairs
        for i in range(0, len(buttons), 2):
            if i + 1 < len(buttons):
                markup.row(buttons[i], buttons[i+1])
            else:
                markup.row(buttons[i])
        
        playlist_text = " (Playlist detected)" if is_playlist else ""
        bot.edit_message_text(
            f"📹 Select video quality{playlist_text}:",
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error in fetch_and_show_resolutions: {e}")
        bot.edit_message_text(
            f"❌ Error: {str(e)}",
            chat_id=chat_id,
            message_id=message_id
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('res_'))
def handle_resolution_selection(call):
    chat_id = call.message.chat.id
    resolution = call.data.split('_')[1]
    
    if chat_id not in user_data:
        bot.answer_callback_query(call.id, "Session expired. Please send the URL again.")
        return
    
    user_data[chat_id].resolution = resolution
    bot.answer_callback_query(call.id)
    
    # Start video download
    playlist_text = "playlist" if user_data[chat_id].is_playlist else "video"
    bot.edit_message_text(
        f"🎬 Downloading {playlist_text} in {resolution}... Please wait.",
        chat_id=chat_id,
        message_id=call.message.message_id
    )
    
    threading.Thread(target=process_video_download, args=(chat_id,)).start()

def process_video_download(chat_id):
    try:
        url = user_data[chat_id].url
        resolution = user_data[chat_id].resolution
        
        bot.send_message(chat_id, "⏳ Downloading... This may take a few minutes.")
        
        filename = download_video_with_ytdlp(url, resolution, chat_id)
        
        # Send the file
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            
            # Telegram file size limit is 50MB for bots
            if file_size > 50 * 1024 * 1024:
                bot.send_message(
                    chat_id,
                    f"⚠️ File is too large ({file_size / (1024*1024):.1f}MB) to send via Telegram.\n"
                    f"Location: {filename}"
                )
            else:
                bot.send_message(chat_id, "📤 Uploading your video...")
                with open(filename, 'rb') as video:
                    bot.send_video(chat_id, video, caption="✅ Here's your video!")
                
                # Clean up
                os.remove(filename)
        else:
            bot.send_message(chat_id, "❌ Download failed. Please try again.")
        
        # Clean up user data
        if chat_id in user_data:
            del user_data[chat_id]
        
        # Clean up folder
        folder_name = f"downloads_{chat_id}"
        if os.path.exists(folder_name) and not os.listdir(folder_name):
            os.rmdir(folder_name)
            
    except Exception as e:
        logger.error(f"Error in process_video_download: {e}")
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

def process_mp3_download(chat_id):
    try:
        url = user_data[chat_id].url
        
        bot.send_message(chat_id, "⏳ Downloading audio... This may take a few minutes.")
        
        filename = download_audio_as_mp3(url, chat_id)
        
        # Send the file
        if os.path.exists(filename):
            file_size = os.path.getsize(filename)
            
            if file_size > 50 * 1024 * 1024:
                bot.send_message(
                    chat_id,
                    f"⚠️ File is too large ({file_size / (1024*1024):.1f}MB) to send via Telegram.\n"
                    f"Location: {filename}"
                )
            else:
                bot.send_message(chat_id, "📤 Uploading your audio...")
                with open(filename, 'rb') as audio:
                    bot.send_audio(chat_id, audio, caption="✅ Here's your MP3!")
                
                # Clean up
                os.remove(filename)
        else:
            bot.send_message(chat_id, "❌ Download failed. Please try again.")
        
        # Clean up user data
        if chat_id in user_data:
            del user_data[chat_id]
        
        # Clean up folder
        folder_name = f"downloads_{chat_id}"
        if os.path.exists(folder_name) and not os.listdir(folder_name):
            os.rmdir(folder_name)
            
    except Exception as e:
        logger.error(f"Error in process_mp3_download: {e}")
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    bot.reply_to(
        message,
        "❓ Send me a YouTube URL or use /start to see instructions."
    )

if __name__ == "__main__":
    print("🤖 Bot is running...")
    bot.infinity_polling()