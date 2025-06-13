import asyncio
import logging
import os
import sys
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import UpdateType
from typing import Optional, Set, List
from config import Config
from database import ManhwaDB
from pdf_processor import PDFProcessor
from user_manager import UserManager
from sites.manhwaclan import ManhwaClanScraper
import aiofiles
from PIL import Image, ImageDraw, ImageFont
import io
import img2pdf
from PyPDF2 import PdfReader, PdfWriter
import atexit
import signal

# Set environment variables
os.environ["BOT_TOKEN"] = "7584435128:AAGHy_LQ_nmAXm7lDRoBDUbQzDWWZ3j5IQE"
os.environ["DATABASE_PATH"] = "data/manhwa.db"
os.environ["TEMP_DIR"] = "temp"
os.environ["WATERMARK_TEXT"] = "Personal use only - ManhwaBot"

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize UserManager with admin IDs
ADMIN_IDS = [7961509388, 5042428876]
user_manager = UserManager(ADMIN_IDS)

# Process lock mechanism
def create_lock():
    """Create a lock file to prevent multiple instances"""
    lock_file = "bot.lock"
    if os.path.exists(lock_file):
        with open(lock_file, 'r') as f:
            pid = f.read().strip()
            try:
                # Check if process is still running
                os.kill(int(pid), 0)
                print(f"Bot is already running with PID {pid}")
                sys.exit(1)
            except (OSError, ProcessLookupError):
                # Process not running, remove stale lock
                os.remove(lock_file)
    
    # Create lock file
    with open(lock_file, 'w') as f:
        f.write(str(os.getpid()))

def remove_lock():
    """Remove the lock file"""
    try:
        os.remove("bot.lock")
    except:
        pass

# Register cleanup handlers
atexit.register(remove_lock)
signal.signal(signal.SIGINT, lambda s, f: (remove_lock(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s, f: (remove_lock(), sys.exit(0)))

class ManhwaBot:
    def __init__(self, config):
        """Initialize the bot"""
        self.config = config
        self.config.validate()
        self.bot = Bot(token=self.config.BOT_TOKEN)
        self.dp = Dispatcher()
        self.db = ManhwaDB(self.config.DATABASE_PATH)
        self.scraper = ManhwaClanScraper()  # Use ManhwaClanScraper directly
        self.user_manager = UserManager({5042428876, 7961509388})
        self.user_states = {}  # Initialize user states dictionary
        self.pdf_processor = PDFProcessor()
        
        # Register command handlers
        self.register_handlers()

    def register_handlers(self):
        """Register command handlers"""
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_fetch, Command("fetch"))
        self.dp.message.register(self.cmd_add_manhwa, Command("add"))
        self.dp.message.register(self.cmd_list_manhwa, Command("list"))
        self.dp.message.register(self.cmd_remove_manhwa, Command("remove"))
        self.dp.message.register(self.cmd_manual_check, Command("check"))
        self.dp.message.register(self.cmd_status, Command("status"))
        self.dp.message.register(self.cmd_get_latest, Command("latest"))
        self.dp.message.register(self.cmd_add_user, Command("adduser"))
        self.dp.message.register(self.cmd_remove_user, Command("removeuser"))
        self.dp.message.register(self.cmd_list_users, Command("listusers"))
        self.dp.message.register(self.cmd_search, Command("search"))
        
        # Register callback query handler
        self.dp.callback_query.register(self.handle_callback_query)
        
        # Register message handler for chapter ranges only when user is in fetch state
        self.dp.message.register(self.handle_chapter_range, lambda message: message.from_user.id in self.user_states)

    async def check_authorization(self, message: Message) -> bool:
        """Check if user is authorized to use the bot"""
        user_id = message.from_user.id
        is_authorized = self.user_manager.is_authorized(user_id)
        logger.info(f"Authorization check for user {user_id}: {is_authorized}")
        if not is_authorized:
            await message.answer("You are not authorized to use this bot.")
            return False
        return True

    async def cmd_start(self, message: Message):
        """Handle /start command"""
        try:
            user_id = message.from_user.id
            logger.info(f"Received /start command from user {user_id}")

            # Check if this is the first user
            if not self.user_manager.authorized_users and not self.user_manager.admin_ids:
                logger.info(f"First user {user_id} detected, making them admin")
                self.user_manager.admin_ids.add(user_id)
                self.user_manager.authorized_users.add(user_id)
                self.user_manager._save_users()
                await message.answer("Welcome! You have been set as the first admin user.")
            elif not await self.check_authorization(message):
                logger.info(f"User {user_id} is not authorized")
                await message.answer("You are not authorized to use this bot. Please contact an admin.")
                return

            try:
                welcome_text = (
                    "🤖 Manhwa Chapter Downloader Bot\n\n"
                    "How to use:\n"
                    "1. Use /search <manhwa_name> to search for manhwa\n"
                    "2. Or use /fetch <manhwa_url> to start with a URL\n"
                    "3. Select the chapters you want\n"
                    "4. I'll send you the chapters as PDFs\n\n"
                    "Example:\n"
                    "/search solo leveling\n"
                    "or\n"
                    "/fetch https://manhwaclan.com/manga/example"
                )
                logger.info(f"Sending welcome message to user {user_id}")
                await message.answer(welcome_text)
                logger.info(f"Welcome message sent successfully to user {user_id}")
            except Exception as e:
                logger.error(f"Error in cmd_start inner try block: {str(e)}")
                logger.error(f"Error type: {type(e)}")
                raise e
        except Exception as e:
            logger.error(f"Error in cmd_start: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            await message.answer("Sorry, there was an error processing your command. Please try again.")

    async def cmd_fetch(self, message: Message):
        """Handle /fetch command"""
        if not await self.check_authorization(message):
            return

        # Get URL from message
        url = message.text.split(' ', 1)[1].strip()
        if not url:
            await message.reply("Please provide a URL. Usage: /fetch <url>")
            return

        # Send initial message
        status_msg = await message.reply("Fetching chapters...")

        try:
            # Create session and get chapters
            async with aiohttp.ClientSession() as session:
                chapters = await self.scraper.get_latest_chapters(session, url)
                
                if not chapters:
                    await status_msg.edit_text("No chapters found or error occurred.")
                    return

                # Store chapters and URL in user state
                self.user_states[message.from_user.id] = {
                    'state': 'fetching',
                    'chapters': chapters,
                    'url': url
                }

                # Format chapter list
                chapter_list = "\n".join([f"{i+1}. {ch['name']}" for i, ch in enumerate(chapters)])
                await status_msg.edit_text(
                    f"Found {len(chapters)} chapters.\n\n"
                    f"Available chapters:\n{chapter_list}\n\n"
                    "Please select chapters using one of these formats:\n"
                    "- Single chapter: 1\n"
                    "- Range: 1-5\n"
                    "- Multiple chapters: 1,3,5"
                )

        except Exception as e:
            logger.error(f"Error in fetch command: {e}")
            await status_msg.edit_text(f"Error occurred: {str(e)}")
            # Clean up user state
            self.user_states.pop(message.from_user.id, None)

    async def handle_chapter_range(self, message: Message) -> None:
        """Handle chapter range selection"""
        if not await self.check_authorization(message):
            return

        user_id = message.from_user.id
        user_state = self.user_states.get(user_id)
        if not user_state or user_state.get('state') != 'fetching':
            await message.reply("Please use /fetch command first.")
            return

        chapters = user_state['chapters']
        url = user_state['url']
        selected_chapters = []

        try:
            # Parse user input
            text = message.text.strip()
            
            # Handle range format (e.g., "1-5")
            if '-' in text:
                start, end = map(int, text.split('-'))
                selected_chapters = chapters[start-1:end]
            
            # Handle comma-separated format (e.g., "1,3,5")
            elif ',' in text:
                indices = [int(x.strip()) - 1 for x in text.split(',')]
                selected_chapters = [chapters[i] for i in indices if 0 <= i < len(chapters)]
            
            # Handle single chapter (e.g., "1")
            else:
                try:
                    index = int(text) - 1
                    if 0 <= index < len(chapters):
                        selected_chapters = [chapters[index]]
                except ValueError:
                    await message.reply("Invalid input. Please use format: 1, 1-5, or 1,3,5")
                    return

            if not selected_chapters:
                await message.reply("No valid chapters selected.")
                return

            # Process selected chapters
            status_msg = await message.reply(f"Processing {len(selected_chapters)} chapters...")
            
            async with aiohttp.ClientSession() as session:
                for chapter in selected_chapters:
                    try:
                        # Get chapter images
                        images = await self.scraper.get_chapter_images(session, chapter['url'])
                        if not images:
                            continue

                        # Create PDF
                        pdf_path = await self.pdf_processor.create_chapter_pdf(
                            images,
                            chapter['name'],
                            url
                        )

                        if pdf_path:
                            # Send PDF
                            with open(pdf_path, 'rb') as pdf_file:
                                await message.answer_document(
                                    document=types.FSInputFile(pdf_path),
                                    caption=f"Chapter: {chapter['name']}"
                                )
                            # Clean up PDF file
                            os.remove(pdf_path)

                    except Exception as e:
                        logger.error(f"Error processing chapter {chapter['name']}: {e}")
                        await message.reply(f"Error processing chapter {chapter['name']}: {str(e)}")

            await status_msg.edit_text("All chapters processed!")

        except Exception as e:
            logger.error(f"Error in chapter range handler: {e}")
            await message.reply(f"Error occurred: {str(e)}")
        
        finally:
            # Clean up user state
            self.user_states.pop(user_id, None)

    async def handle_message(self, message: Message):
        """Handle all messages"""
        if not await self.check_authorization(message):
            return

        # If we get here, it means the message wasn't handled by any other handler
        await message.answer("Please use /fetch <manhwa_url> to start downloading chapters.")

    async def cmd_add_manhwa(self, message: Message):
        """Add manhwa to tracking"""
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /add <manhwa_url>")
                return
            url = args[1]
            user_id = message.from_user.id

            result = await self.scraper.add_manhwa(url)
            if result["success"]:
                self.db.add_manhwa(
                    name=result["name"],
                    url=url,
                    site_name=result["site"],
                    telegram_user_id=user_id,
                    last_chapter_url=result.get("latest_chapter_url", ""),
                    last_chapter_name=result.get("latest_chapter", "")
                )
                await message.answer(f"✅ Added: {result['name']}")
            else:
                await message.answer(f"❌ Failed to add manhwa: {result['error']}")
        except Exception as e:
            logger.error(f"Error adding manhwa: {e}")
            await message.answer("❌ Error adding manhwa")

    async def cmd_list_manhwa(self, message: Message):
        """List tracked manhwa for the current user"""
        user_id = message.from_user.id
        # Filter manhwa by user_id
        manhwa_list = [m for m in self.db.get_all_manhwa() if m.telegram_user_id == user_id]

        if not manhwa_list:
            await message.answer("No manhwa being tracked by you.")
            return

        text = "📚 **Your Tracked Manhwa:**\n\n"
        for manhwa in manhwa_list:
            text += f"• {manhwa.name}\n"
            text += f"  Last: {manhwa.last_chapter_name or 'Unknown'}\n\n"
        await message.answer(text, parse_mode="Markdown")

    async def cmd_remove_manhwa(self, message: Message):
        """Remove manhwa from tracking"""
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /remove <manhwa_name>")
                return
            name = args[1]
            user_id = message.from_user.id

            # Ensure only the user who added it can remove it (or an admin)
            manhwa_to_remove = self.db.get_manhwa_by_name(name)
            if manhwa_to_remove and manhwa_to_remove.telegram_user_id == user_id:
                if self.db.remove_manhwa(name):
                    await message.answer(f"✅ Removed: {name}")
                else:
                    await message.answer(f"❌ Manhwa not found: {name}")
            else:
                await message.answer(f"❌ You can only remove manhwa you have added.")

        except Exception as e:
            logger.error(f"Error removing manhwa: {e}")
            await message.answer("❌ Error removing manhwa")

    async def cmd_manual_check(self, message: Message):
        """Manual update check"""
        await message.answer("🔍 Checking for updates...")
        try:
            updates = await self.check_for_updates()
            if updates:
                await message.answer(f"✅ Found {len(updates)} new chapters!")
            else:
                await message.answer("📚 No new chapters found.")
        except Exception as e:
            logger.error(f"Error in manual check: {e}")
            await message.answer("❌ Error checking for updates")

    async def cmd_status(self, message: Message):
        """Show bot status"""
        manhwa_count = len(self.db.get_all_manhwa())
        status_text = f"""
        📊 **Bot Status**
        Tracked Manhwa: {manhwa_count}
        Auto-check: Every {self.config.UPDATE_INTERVAL_HOURS} hours
        Status: Running ✅
        """
        await message.answer(status_text, parse_mode="Markdown")

    async def cmd_get_latest(self, message: Message):
        """Get chapters of a specific manhwa"""
        try:
            args = message.text.split(maxsplit=2)
            if len(args) < 2:
                await message.answer("Usage: /latest <manhwa_name> [chapter_range]\nExamples:\n/latest manhwa_name\n/latest manhwa_name latest\n/latest manhwa_name 1-5")
                return

            manhwa_name = args[1]
            user_id = message.from_user.id

            # Get manhwa from database
            manhwa = self.db.get_manhwa_by_name(manhwa_name)
            if not manhwa or manhwa.telegram_user_id != user_id:
                await message.answer(f"❌ Manhwa '{manhwa_name}' not found in your tracking list.")
                return

            # Send processing message
            processing_msg = await message.answer(f"🔄 Getting chapters for {manhwa_name}...")

            # Get chapter info
            session = await self.scraper.get_session()
            scraper = self.scraper
            if not scraper:
                await processing_msg.edit_text(f"❌ Unsupported site for {manhwa_name}")
                return

            info = await scraper.get_manhwa_info(session, manhwa.url)
            if not info or not info.get('chapters'):
                await processing_msg.edit_text(f"❌ Could not get chapter info for {manhwa_name}")
                return

            # Determine which chapters to process
            chapters_to_process = []
            if len(args) == 2 or args[2].lower() == 'latest':
                # Get only the latest chapter
                latest_chapter = info['chapters'][-1]
                chapters_to_process = [latest_chapter]
                await processing_msg.edit_text(f"🔄 Processing latest chapter ({latest_chapter['name']})...")
            else:
                # Parse chapter range
                try:
                    range_str = args[2]
                    if '-' in range_str:
                        start, end = map(int, range_str.split('-'))
                        # Filter chapters within range
                        chapters_to_process = [
                            ch for ch in info['chapters']
                            if start <= int(ch['name'].split()[-1]) <= end
                        ]
                        if not chapters_to_process:
                            await processing_msg.edit_text(f"❌ No chapters found in range {start}-{end}")
                            return
                        await processing_msg.edit_text(f"🔄 Processing chapters {start}-{end}...")
                    else:
                        # Single chapter
                        chapter_num = int(range_str)
                        chapter = next(
                            (ch for ch in info['chapters'] if int(ch['name'].split()[-1]) == chapter_num),
                            None
                        )
                        if not chapter:
                            await processing_msg.edit_text(f"❌ Chapter {chapter_num} not found")
                            return
                        chapters_to_process = [chapter]
                        await processing_msg.edit_text(f"🔄 Processing chapter {chapter_num}...")
                except ValueError:
                    await processing_msg.edit_text("❌ Invalid chapter range format. Use numbers like '1-5' or 'latest'")
                    return

            # Process and send chapters
            success_count = 0
            for chapter in chapters_to_process:
                try:
                    success = await self.process_and_deliver_chapter(manhwa, chapter, user_id)
                    if success:
                        success_count += 1
                        # Add a small delay between chapters to avoid rate limits
                        await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Error processing chapter {chapter['name']}: {e}")
                    continue

            if success_count > 0:
                await processing_msg.edit_text(f"✅ Successfully sent {success_count} chapter(s) to your DM!")
                # Update database with latest chapter info
                if len(args) == 2 or args[2].lower() == 'latest':
                    self.db.update_manhwa_progress(
                        manhwa.name,
                        chapters_to_process[-1]['url'],
                        chapters_to_process[-1]['name']
                    )
            else:
                await processing_msg.edit_text(f"❌ Failed to process any chapters")

        except Exception as e:
            logger.error(f"Error getting chapters: {e}")
            await message.answer("❌ Error getting chapters. Please try again.")

    async def check_for_updates(self):
        """Check all manhwa for new chapters"""
        updates = []
        manhwa_list = self.db.get_all_manhwa()
        for manhwa in manhwa_list:
            try:
                logger.info(f"Checking {manhwa.name}")
                new_chapters = await self.scraper.check_new_chapters(manhwa)
                for chapter in new_chapters:
                    # Get the user\'s specific output channel for this manhwa
                    user_output_channel = self.db.get_user_output_channel(manhwa.telegram_user_id)
                    if not user_output_channel:
                        logger.warning(f"No output channel set for user {manhwa.telegram_user_id} tracking {manhwa.name}. Skipping delivery of {chapter['name']}.")
                        continue

                    success = await self.process_and_deliver_chapter(manhwa, chapter, manhwa.telegram_user_id)
                    if success:
                        updates.append((manhwa.name, chapter['name']))
                        # Update database
                        self.db.update_manhwa_progress(
                            manhwa.name,
                            chapter['url'],
                            chapter['name']
                        )
            except Exception as e:
                logger.error(f"Error checking {manhwa.name}: {e}")
        return updates

    async def process_and_deliver_chapter(self, manhwa, chapter, user_id: int) -> bool:
        """Process and deliver a chapter to a user"""
        try:
            # Create PDF
            pdf_path = await self.pdf_processor.create_chapter_pdf(
                chapter['images'],
                manhwa.name,
                chapter['name']
            )
            
            if not pdf_path:
                logger.error("Failed to create PDF")
                return False
            
            logger.info(f"PDF created successfully at {pdf_path}")
            
            # Send to user
            success = await self.send_chapter_to_user(pdf_path, manhwa.name, chapter['name'], user_id)
            
            # Cleanup
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            
            return success
            
        except Exception as e:
            logger.error(f"Error in process_and_deliver_chapter: {e}")
            return False

    async def send_chapter_to_user(self, pdf_path, manhwa_name, chapter_name, user_id: int):
        """Send chapter PDF to user's DM"""
        try:
            logger.info(f"Attempting to send PDF to user {user_id}")
            logger.info(f"PDF path: {pdf_path}")
            logger.info(f"File exists: {os.path.exists(pdf_path)}")
            
            # Create caption
            caption = f"📚 {manhwa_name}\n📖 {chapter_name}"
            logger.info(f"Created caption: {caption}")
            
            # Send PDF using FSInputFile
            try:
                # Use the same filename that was created in pdf_processor
                pdf_filename = os.path.basename(pdf_path)
                message = await self.bot.send_document(
                    chat_id=user_id,
                    document=types.FSInputFile(pdf_path, filename=pdf_filename),
                    caption=caption
                )
                logger.info(f"Successfully sent message to user. Message ID: {message.message_id}")
                return True
            except Exception as send_error:
                logger.error(f"Error during send_document: {str(send_error)}")
                logger.error(f"Error type: {type(send_error)}")
                raise send_error
        except Exception as e:
            logger.error(f"Error sending to user: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            return False

    async def cmd_add_user(self, message: Message):
        """Add a new user (admin only)"""
        logger.info(f"Received adduser command from user {message.from_user.id}")
        if not await self.check_authorization(message):
            logger.info(f"User {message.from_user.id} is not authorized")
            return

        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /adduser <user_id>")
                return

            new_user_id = int(args[1])
            logger.info(f"Attempting to add user {new_user_id} by admin {message.from_user.id}")
            success, response = self.user_manager.add_user(message.from_user.id, new_user_id)
            logger.info(f"Add user result - Success: {success}, Response: {response}")
            await message.answer(response)
        except ValueError:
            logger.error(f"Invalid user ID provided: {args[1]}")
            await message.answer("Invalid user ID. Please provide a valid number.")
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            await message.answer("❌ Error adding user")

    async def cmd_remove_user(self, message: Message):
        """Remove a user (admin only)"""
        logger.info(f"Received removeuser command from user {message.from_user.id}")
        if not await self.check_authorization(message):
            logger.info(f"User {message.from_user.id} is not authorized")
            return

        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /removeuser <user_id>")
                return

            target_user_id = int(args[1])
            logger.info(f"Attempting to remove user {target_user_id} by admin {message.from_user.id}")
            success, response = self.user_manager.remove_user(message.from_user.id, target_user_id)
            logger.info(f"Remove user result - Success: {success}, Response: {response}")
            await message.answer(response)
        except ValueError:
            logger.error(f"Invalid user ID provided: {args[1]}")
            await message.answer("Invalid user ID. Please provide a valid number.")
        except Exception as e:
            logger.error(f"Error removing user: {e}")
            await message.answer("❌ Error removing user")

    async def cmd_list_users(self, message: Message):
        """List all authorized users (admin only)"""
        logger.info(f"Received listusers command from user {message.from_user.id}")
        if not await self.check_authorization(message):
            logger.info(f"User {message.from_user.id} is not authorized")
            return

        try:
            logger.info(f"Attempting to list users for admin {message.from_user.id}")
            success, response = self.user_manager.list_users(message.from_user.id)
            logger.info(f"List users result - Success: {success}, Response: {response}")
            await message.answer(response)
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            await message.answer("❌ Error listing users")

    async def cmd_search(self, message: Message):
        """Handle /search command"""
        if not await self.check_authorization(message):
            return

        # Get search query
        query = message.text.split(' ', 1)[1].strip()
        if not query:
            await message.reply("Please provide a search query. Usage: /search <manhwa_name>")
            return

        # Send initial message
        status_msg = await message.reply("Searching...")

        try:
            # Search for manhwa
            results = await self.scraper.search_manhwa(query)
            
            if not results:
                await status_msg.edit_text("No results found.")
                return

            # Create inline keyboard with results
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=result['title'], callback_data=f"select_{result['url']}")]
                for result in results[:5]  # Show top 5 results
            ])

            await status_msg.edit_text(
                "Found these manhwa. Click on one to view chapters:",
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Error in search command: {e}")
            await status_msg.edit_text(f"Error occurred: {str(e)}")

    async def handle_callback_query(self, callback_query: types.CallbackQuery):
        """Handle callback queries from inline keyboards"""
        if not await self.check_authorization(callback_query.message):
            return

        try:
            data = callback_query.data
            if data.startswith("select_"):
                # Get manhwa URL from callback data
                url = data[7:]  # Remove "select_" prefix
                
                # Send status message
                status_msg = await callback_query.message.answer("Fetching chapters...")
                
                # Get chapters
                async with aiohttp.ClientSession() as session:
                    chapters = await self.scraper.get_latest_chapters(session, url)
                    
                    if not chapters:
                        await status_msg.edit_text("No chapters found.")
                        return

                    # Store chapters and URL in user state
                    self.user_states[callback_query.from_user.id] = {
                        'state': 'fetching',
                        'chapters': chapters,
                        'url': url
                    }

                    # Format chapter list
                    chapter_list = "\n".join([f"{i+1}. {ch['name']}" for i, ch in enumerate(chapters)])
                    await status_msg.edit_text(
                        f"Found {len(chapters)} chapters.\n\n"
                        f"Available chapters:\n{chapter_list}\n\n"
                        "Please select chapters using one of these formats:\n"
                        "- Single chapter: 1\n"
                        "- Range: 1-5\n"
                        "- Multiple chapters: 1,3,5"
                    )

        except Exception as e:
            logger.error(f"Error in callback query handler: {e}")
            await callback_query.message.answer(f"Error occurred: {str(e)}")

    async def start_bot(self):
        """Start the bot"""
        try:
            # Initialize database
            self.db.init_tables()

            # Start polling with retry mechanism
            logger.info("Starting Manhwa Bot...")
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    await self.dp.start_polling(self.bot, allowed_updates=[UpdateType.MESSAGE])
                    break
                except Exception as e:
                    if "Conflict" in str(e):
                        retry_count += 1
                        if retry_count < max_retries:
                            logger.warning(f"Bot conflict detected. Attempt {retry_count} of {max_retries}. Waiting 5 seconds...")
                            await asyncio.sleep(5)
                        else:
                            logger.error("Maximum retry attempts reached. Please ensure no other bot instances are running.")
                            raise
                    else:
                        raise
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            sys.exit(1)

    async def create_pdf(self, image_urls: List[str], output_path: str, manhwa_name: str, chapter_num: str) -> None:
        """Create a PDF from a list of image URLs with watermark"""
        try:
            # Download all images
            images = []
            async with aiohttp.ClientSession() as session:
                for url in image_urls:
                    try:
                        async with session.get(url) as response:
                            if response.status == 200:
                                image_data = await response.read()
                                # Open image with PIL
                                img = Image.open(io.BytesIO(image_data))
                                # Convert to RGB if necessary
                                if img.mode in ('RGBA', 'LA'):
                                    background = Image.new('RGB', img.size, (255, 255, 255))
                                    background.paste(img, mask=img.split()[-1])
                                    img = background
                                elif img.mode != 'RGB':
                                    img = img.convert('RGB')
                                
                                # Add watermark
                                draw = ImageDraw.Draw(img)
                                # Use a much smaller font size (0.8% of image height)
                                font_size = int(img.size[1] * 0.008)
                                try:
                                    font = ImageFont.truetype("arial.ttf", font_size)
                                except:
                                    font = ImageFont.load_default()
                                
                                watermark_text = "join @manga_stash"
                                # Calculate text size
                                text_bbox = draw.textbbox((0, 0), watermark_text, font=font)
                                text_width = text_bbox[2] - text_bbox[0]
                                text_height = text_bbox[3] - text_bbox[1]
                                
                                # Position in bottom right with padding
                                padding = int(img.size[0] * 0.005)  # 0.5% padding
                                position = (
                                    img.size[0] - text_width - padding,
                                    img.size[1] - text_height - padding
                                )
                                
                                # Add very subtle watermark (more transparent)
                                draw.text(position, watermark_text, font=font, fill=(128, 128, 128, 64))
                                
                                # Save to bytes
                                img_byte_arr = io.BytesIO()
                                img.save(img_byte_arr, format='JPEG', quality=90, optimize=True)
                                images.append(img_byte_arr.getvalue())
                    except Exception as e:
                        logger.error(f"Error downloading image {url}: {e}")
                        continue

            if not images:
                raise Exception("No images were successfully downloaded")

            # Create temporary PDF
            temp_pdf_path = f"temp_{output_path}"
            with open(temp_pdf_path, "wb") as f:
                f.write(img2pdf.convert(images))

            # Compress PDF
            reader = PdfReader(temp_pdf_path)
            writer = PdfWriter()

            # Copy pages with compression
            for page in reader.pages:
                writer.add_page(page)

            # Set compression parameters
            writer.add_metadata(reader.metadata)
            
            # Write compressed PDF
            with open(output_path, "wb") as output_file:
                writer.write(output_file)

            # Clean up temporary file
            os.remove(temp_pdf_path)

            logger.info(f"Successfully created compressed PDF with {len(images)} images")
        except Exception as e:
            logger.error(f"Error creating PDF: {e}")
            raise e

if __name__ == "__main__":
    # Create process lock
    create_lock()
    
    try:
        # Initialize logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        
        # Create bot instance
        config = Config()
        config.validate()
        
        bot = ManhwaBot(config)
        asyncio.run(bot.start_bot())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        logger.error(f"Error: {e}")
    finally:
        remove_lock()
