import asyncio
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import UpdateType
from typing import Optional
from config import Config
from database import ManhwaDB
from scraper import ManhwaScraperManager
from pdf_processor import PDFProcessor
from scheduler import UpdateScheduler
from user_manager import UserManager

# Set environment variables
os.environ["BOT_TOKEN"] = "7481737869:AAE7rEWHuQZhkCbBVJbYAFwnOFM7-Jxq7i4"
os.environ["CHANNEL_ID"] = "-1002700341132"
os.environ["DATABASE_PATH"] = "data/manhwa.db"
os.environ["UPDATE_INTERVAL_HOURS"] = "6"
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
        self.config = Config()
        self.config.validate()
        self.bot = Bot(token=self.config.BOT_TOKEN)
        self.dp = Dispatcher()
        self.db = ManhwaDB(self.config.DATABASE_PATH)
        self.scraper_manager = ManhwaScraperManager()
        self.pdf_processor = PDFProcessor()
        self.scheduler = UpdateScheduler(self)
        self.user_manager = user_manager

        # Register handlers
        self.register_handlers()

    def register_handlers(self):
        """Register bot command handlers"""
        print("Registering command handlers...")
        self.dp.message.register(self.cmd_start, Command("start"))
        self.dp.message.register(self.cmd_add_manhwa, Command("add"))
        self.dp.message.register(self.cmd_list_manhwa, Command("list"))
        self.dp.message.register(self.cmd_remove_manhwa, Command("remove"))
        self.dp.message.register(self.cmd_manual_check, Command("check"))
        self.dp.message.register(self.cmd_status, Command("status"))
        self.dp.message.register(self.cmd_setchannel, Command("setchannel"))
        self.dp.message.register(self.cmd_get_latest, Command("latest"))
        self.dp.message.register(self.cmd_add_user, Command("adduser"))
        self.dp.message.register(self.cmd_remove_user, Command("removeuser"))
        self.dp.message.register(self.cmd_list_users, Command("listusers"))
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
        if not await self.check_authorization(message):
            return

        try:
            welcome_text = (
                "🤖 Manhwa Delivery Bot\n\n"
                "Commands:\n"
                "/add <manhwa_url> - Add manhwa to tracking\n"
                "/list - Show tracked manhwa\n"
                "/remove <manhwa_name> - Remove manhwa\n"
                "/check - Manual update check\n"
                "/status - Bot status\n"
                "/setchannel <channel_id> - Set your output Telegram channel\n"
                "/latest <manhwa_name> - Get latest chapter of a manhwa\n"
                "/adduser <user_id> - Add a new user (admin only)\n"
                "/removeuser <user_id> - Remove a user (admin only)\n"
                "/listusers - List all authorized users (admin only)\n\n"
                f"Bot will automatically check for updates every {self.config.UPDATE_INTERVAL_HOURS} hours."
            )
            await message.answer(welcome_text)
        except Exception as e:
            logger.error(f"Error in cmd_start: {e}")
            await message.answer("Sorry, there was an error processing your command. Please try again.")

    async def cmd_add_manhwa(self, message: Message):
        """Add manhwa to tracking"""
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /add <manhwa_url>")
                return
            url = args[1]
            user_id = message.from_user.id # Get user ID

            # Check if user has set an output channel
            output_channel = self.db.get_user_output_channel(user_id)
            if not output_channel:
                await message.answer("Please set your output Telegram channel first using /setchannel <channel_id>.")
                return

            result = await self.scraper_manager.add_manhwa(url)
            if result["success"]:
                self.db.add_manhwa(
                    name=result["name"],
                    url=url,
                    site_name=result["site"],
                    telegram_user_id=user_id, # Pass user ID here
                    last_chapter_url=result.get("latest_chapter_url", ""),
                    last_chapter_name=result.get("latest_chapter", "")
                )
                await message.answer(f"✅ Added: {result["name"]}")
            else:
                await message.answer(f"❌ Failed to add manhwa: {result["error"]}")
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

    async def cmd_setchannel(self, message: types.Message):
        """Set the output channel for updates"""
        try:
            # Get channel ID from message
            channel_id = message.text.split()[1]
            logger.info(f"Setting channel ID: {channel_id}")
            
            # Verify channel ID format
            if not channel_id.startswith('-100'):
                channel_id = f'-100{channel_id}'
            logger.info(f"Formatted channel ID: {channel_id}")
            
            # Try to get channel info
            try:
                chat = await self.bot.get_chat(channel_id)
                logger.info(f"Channel info retrieved: {chat.title} (ID: {chat.id})")
            except Exception as e:
                logger.error(f"Error getting channel info: {str(e)}")
                await message.reply("❌ Error: Could not verify channel. Make sure:\n"
                                  "1. The bot is an admin in the channel\n"
                                  "2. The channel ID is correct\n"
                                  "3. The channel is public")
                return
            
            # Update channel ID in database
            self.db.update_channel_id(channel_id)
            logger.info(f"Channel ID updated in database: {channel_id}")
            
            await message.reply(f"✅ Channel set to: {chat.title}")
        except Exception as e:
            logger.error(f"Error in setchannel command: {str(e)}")
            await message.reply("❌ Error setting channel. Please try again.")

    async def cmd_get_latest(self, message: Message):
        """Get the latest chapter of a specific manhwa"""
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /latest <manhwa_name>")
                return

            manhwa_name = args[1]
            user_id = message.from_user.id

            # Get manhwa from database
            manhwa = self.db.get_manhwa_by_name(manhwa_name)
            if not manhwa or manhwa.telegram_user_id != user_id:
                await message.answer(f"❌ Manhwa '{manhwa_name}' not found in your tracking list.")
                return

            # Get user's output channel
            output_channel = self.db.get_user_output_channel(user_id)
            if not output_channel:
                await message.answer("Please set your output Telegram channel first using /setchannel <channel_id>.")
                return

            # Send processing message
            processing_msg = await message.answer(f"🔄 Getting latest chapter for {manhwa_name}...")

            # Get latest chapter info
            session = await self.scraper_manager.get_session()
            scraper = self.scraper_manager.get_scraper(manhwa.url)
            if not scraper:
                await processing_msg.edit_text(f"❌ Unsupported site for {manhwa_name}")
                return

            info = await scraper.get_manhwa_info(session, manhwa.url)
            if not info or not info.get('latest_chapter_url'):
                await processing_msg.edit_text(f"❌ Could not get latest chapter info for {manhwa_name}")
                return

            # Process and send the chapter
            chapter = {
                'name': info['latest_chapter'],
                'url': info['latest_chapter_url']
            }

            success = await self.process_and_deliver_chapter(manhwa, chapter, output_channel)
            if success:
                await processing_msg.edit_text(f"✅ Latest chapter of {manhwa_name} has been sent to your channel!")
                # Update database with new chapter info
                self.db.update_manhwa_progress(
                    manhwa.name,
                    chapter['url'],
                    chapter['name']
                )
            else:
                await processing_msg.edit_text(f"❌ Failed to process latest chapter of {manhwa_name}")

        except Exception as e:
            logger.error(f"Error getting latest chapter: {e}")
            await message.answer("❌ Error getting latest chapter. Please try again.")

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

                    success = await self.process_and_deliver_chapter(manhwa, chapter, user_output_channel)
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

    async def process_and_deliver_chapter(self, manhwa, chapter, output_channel_id: str) -> bool:
        """Download, process and deliver a chapter"""
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

            # Send to Telegram channel
            logger.info(f"Sending to channel {output_channel_id}")
            try:
                await self.send_chapter_to_channel(pdf_path, manhwa.name, chapter['name'], output_channel_id)
                logger.info("Successfully sent to channel")
            except Exception as e:
                logger.error(f"Error sending to channel: {e}")
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

    async def send_chapter_to_channel(self, pdf_path, manhwa_name, chapter_name, chat_id: str):
        """Send chapter PDF to Telegram channel"""
        try:
            logger.info(f"Attempting to send PDF to channel {chat_id}")
            logger.info(f"PDF path: {pdf_path}")
            logger.info(f"File exists: {os.path.exists(pdf_path)}")
            
            # Create caption
            caption = f"📚 {manhwa_name}\n📖 {chapter_name}"
            logger.info(f"Created caption: {caption}")
            
            # Send PDF using FSInputFile
            try:
                message = await self.bot.send_document(
                    chat_id=chat_id,
                    document=types.FSInputFile(pdf_path, filename=f"{manhwa_name} - {chapter_name}.pdf"),
                    caption=caption
                )
                logger.info(f"Successfully sent message to channel. Message ID: {message.message_id}")
                return True
            except Exception as send_error:
                logger.error(f"Error during send_document: {str(send_error)}")
                logger.error(f"Error type: {type(send_error)}")
                raise send_error
        except Exception as e:
            logger.error(f"Error sending to channel: {str(e)}")
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
            self.db.init_tables() # Ensure tables are created

            # Start scheduler
            self.scheduler.start()

            # Start polling
            logger.info("Starting Manhwa Bot...")
            await self.dp.start_polling(self.bot, allowed_updates=[UpdateType.MESSAGE])
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            sys.exit(1)

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
