import asyncio
import logging
import os
import sys
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import UpdateType
from typing import Optional, Set, List
from config import Config
from database import ManhwaDB
from scraper import ManhwaScraperManager
from pdf_processor import PDFProcessor
from user_manager import UserManager
from sites.manhwaclan import ManhwaClanScraper
import aiofiles
from PIL import Image, ImageDraw, ImageFont
import io
import img2pdf
from PyPDF2 import PdfReader, PdfWriter

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

class ManhwaBot:
    def __init__(self):
        """Initialize the bot"""
        self.config = Config()
        self.config.validate()
        self.bot = Bot(token=self.config.BOT_TOKEN)
        self.dp = Dispatcher()
        self.db = ManhwaDB(self.config.DATABASE_PATH)
        self.scraper = ManhwaClanScraper()
        self.user_manager = UserManager({5042428876, 7961509388})
        self.user_states = {}  # Initialize user states dictionary
        
        # Register command handlers
        print("Registering command handlers...")
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_fetch, Command("fetch"))
        self.dp.message.register(self.cmd_add_user, Command("adduser"))
        self.dp.message.register(self.cmd_remove_user, Command("removeuser"))
        self.dp.message.register(self.cmd_list_users, Command("listusers"))
        
        # Register message handler for chapter ranges
        self.dp.message.register(self.handle_chapter_range)
        print("Command handlers registered.")

    def register_handlers(self):
        """Register bot command handlers"""
        print("Registering command handlers...")
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_add_manhwa, Command("add"))
        self.dp.message.register(self.cmd_list_manhwa, Command("list"))
        self.dp.message.register(self.cmd_remove_manhwa, Command("remove"))
        self.dp.message.register(self.cmd_manual_check, Command("check"))
        self.dp.message.register(self.cmd_status, Command("status"))
        self.dp.message.register(self.cmd_get_latest, Command("latest"))
        self.dp.message.register(self.cmd_add_user, Command("adduser"))
        self.dp.message.register(self.cmd_remove_user, Command("removeuser"))
        self.dp.message.register(self.cmd_list_users, Command("listusers"))
        self.dp.message.register(self.cmd_fetch, Command("fetch"))
        print("Command handlers registered.")

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
                    "1. Use /fetch <manhwa_url> to start\n"
                    "2. I'll fetch the available chapters\n"
                    "3. Tell me which chapters you want (e.g., '1-5' or 'latest')\n"
                    "4. I'll send you the chapters as PDFs\n\n"
                    "Example:\n"
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
        try:
            if not await self.check_authorization(message):
                return

            # Extract URL from command
            parts = message.text.split()
            if len(parts) != 2:
                await message.answer("Please use the command like this: /fetch <manhwa_url>")
                return

            # Clean up URL
            url = parts[1].strip()
            url = url.strip('@')  # Remove @ if present
            url = url.strip()     # Remove any extra spaces
            
            logger.info(f"Processing URL: {url}")
            
            if not url.startswith('https://manhwaclan.com/manga/'):
                await message.answer("Please send a valid manhwa URL from manhwaclan.com")
                return

            # Store the URL in user state
            self.user_states[message.from_user.id] = {'url': url}
            
            # Fetch available chapters
            await message.answer("Fetching available chapters...")
            try:
                async with aiohttp.ClientSession() as session:
                    logger.info("Created aiohttp session")
                    chapters = await self.scraper.get_latest_chapters(session, url)
                    logger.info(f"Found {len(chapters)} chapters")
                    
                    if not chapters:
                        logger.error("No chapters found in the response")
                        await message.answer("No chapters found for this manhwa.")
                        return

                    # Format chapter list
                    chapter_list = "\n".join([f"{i+1}. {ch['name']}" for i, ch in enumerate(chapters)])
                    response = (
                        "Available chapters:\n\n"
                        f"{chapter_list}\n\n"
                        "Please specify which chapters you want:\n"
                        "- Send a range (e.g., '1-5')\n"
                        "- Send 'latest' for the most recent chapter\n"
                        "- Send a single number (e.g., '3')"
                    )
                    await message.answer(response)
            except Exception as e:
                logger.error(f"Error fetching chapters: {str(e)}")
                logger.error(f"Error type: {type(e)}")
                await message.answer(f"Error fetching chapters: {str(e)}")
                return
                
        except Exception as e:
            logger.error(f"Error in cmd_fetch: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            await message.answer("Sorry, there was an error processing the URL. Please try again.")

    async def handle_chapter_range(self, message: Message) -> None:
        """Handle chapter range input from user"""
        try:
            user_id = message.from_user.id
            if not self.user_manager.is_authorized(user_id):
                logger.info(f"Unauthorized access attempt from user {user_id}")
                await message.reply("You are not authorized to use this bot.")
                return

            # Check if user has a pending URL
            if user_id not in self.user_states or 'url' not in self.user_states[user_id]:
                await message.reply("Please use /fetch command first with a manhwa URL.")
                return

            url = self.user_states[user_id]['url']
            input_text = message.text.strip().lower()
            
            # Extract manhwa name from URL
            manhwa_name = url.split('/')[-1].replace('-', ' ').title()
            
            # Parse chapter range
            if input_text == "latest":
                start_chapter = 1
                end_chapter = 1
            else:
                try:
                    if "-" in input_text:
                        start, end = map(int, input_text.split("-"))
                        start_chapter = min(start, end)
                        end_chapter = max(start, end)
                    else:
                        start_chapter = end_chapter = int(input_text)
                except ValueError:
                    await message.reply("Invalid input. Please send a number (e.g., '1'), a range (e.g., '1-5'), or 'latest'.")
                    return

            # Get chapters
            async with aiohttp.ClientSession() as session:
                chapters = await self.scraper.get_latest_chapters(session, url)
                if not chapters:
                    await message.reply("No chapters found for this manhwa.")
                    return

                logger.info(f"Processing {len(chapters)} chapters")
                # Sort chapters by chapter number
                chapters.sort(key=lambda x: float(x['name'].split()[-1].replace('-', '.')))
                
                # Get requested chapters
                requested_chapters = []
                for chapter in chapters:
                    try:
                        chapter_num = float(chapter['name'].split()[-1].replace('-', '.'))
                        if start_chapter <= chapter_num <= end_chapter:
                            requested_chapters.append(chapter)
                    except (ValueError, IndexError):
                        continue

                if not requested_chapters:
                    await message.reply(f"No chapters found in range {start_chapter}-{end_chapter}")
                    return

                logger.info(f"Processing chapters {start_chapter} to {end_chapter}")
                for chapter in requested_chapters:
                    try:
                        # Send progress message
                        progress_msg = await message.reply(f"🔄 Processing chapter {chapter['name']}...")
                        
                        # Get chapter images
                        images = await self.scraper.get_chapter_images(session, chapter['url'])
                        if not images:
                            await progress_msg.edit_text(f"❌ No images found in chapter {chapter['name']}")
                            continue

                        logger.info(f"Found {len(images)} images for chapter {chapter['name']}")
                        await progress_msg.edit_text(f"📥 Downloading {len(images)} images for chapter {chapter['name']}...")
                        
                        # Format chapter number with leading zeros
                        chapter_num = chapter['name'].split()[-1]
                        if '.' in chapter_num:
                            num, dec = chapter_num.split('.')
                            formatted_num = f"{int(num):03d}.{dec}"
                        else:
                            formatted_num = f"{int(chapter_num):03d}"
                        
                        # Create PDF with formatted name
                        pdf_name = f"{formatted_num} - {manhwa_name}.pdf"
                        pdf_path = f"temp_{pdf_name}"
                        
                        await progress_msg.edit_text(f"📝 Creating PDF for chapter {chapter['name']}...")
                        await self.create_pdf(images, pdf_path, manhwa_name, chapter_num)
                        
                        # Send PDF
                        await progress_msg.edit_text(f"📤 Sending chapter {chapter['name']}...")
                        with open(pdf_path, 'rb') as pdf_file:
                            await message.reply_document(
                                document=types.FSInputFile(pdf_path, filename=pdf_name),
                                caption=f"✅ Chapter {chapter['name']}"
                            )
                        
                        # Clean up
                        os.remove(pdf_path)
                        await progress_msg.delete()
                        
                    except Exception as e:
                        logger.error(f"Error processing chapter {chapter['name']}: {e}")
                        await message.reply(f"❌ Error processing chapter {chapter['name']}: {str(e)}")
                        continue

                await message.reply("✅ All requested chapters have been sent!")
                
        except Exception as e:
            logger.error(f"Error in handle_chapter_range: {e}")
            await message.reply(f"❌ An error occurred: {str(e)}")
        finally:
            # Clear user state after processing
            if user_id in self.user_states:
                del self.user_states[user_id]

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

            result = await self.scraper_manager.add_manhwa(url)
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
            session = await self.scraper_manager.get_session()
            scraper = self.scraper_manager.get_scraper(manhwa.url)
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
                new_chapters = await self.scraper_manager.check_new_chapters(manhwa)
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
        """Download, process and deliver a chapter to user's DM"""
        try:
            logger.info(f"Starting to process chapter {chapter['name']} for {manhwa.name}")
            
            # Download chapter images
            logger.info(f"Downloading images from {chapter['url']}")
            images = await self.scraper_manager.download_chapter_images(
                chapter['url'],
                manhwa.site_name
            )
            if not images:
                logger.error(f"No images found for {chapter['name']}")
                return False
            logger.info(f"Successfully downloaded {len(images)} images")

            # Process images and create PDF
            logger.info("Creating PDF from images")
            pdf_path = await self.pdf_processor.create_chapter_pdf(
                images,
                manhwa.name,
                chapter['name']
            )
            if not pdf_path:
                logger.error(f"Failed to create PDF for {chapter['name']}")
                return False
            logger.info(f"PDF created successfully at {pdf_path}")

            # Send to user's DM
            logger.info(f"Sending to user {user_id}")
            try:
                await self.send_chapter_to_user(pdf_path, manhwa.name, chapter['name'], user_id)
                logger.info("Successfully sent to user")
            except Exception as e:
                logger.error(f"Error sending to user: {e}")
                return False

            # Cleanup
            logger.info("Cleaning up temporary files")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            
            logger.info("Chapter processing completed successfully")
            return True
            
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
                message = await self.bot.send_document(
                    chat_id=user_id,
                    document=types.FSInputFile(pdf_path, filename=f"{manhwa_name} - {chapter_name}.pdf"),
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

    async def start_bot(self):
        """Start the bot"""
        try:
            # Initialize database
            self.db.init_tables()

            # Start polling
            logger.info("Starting Manhwa Bot...")
            await self.dp.start_polling(self.bot, allowed_updates=[UpdateType.MESSAGE])
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
    # Check if another instance is running
    try:
        bot = ManhwaBot()
        asyncio.run(bot.start_bot())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
