import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from config import Config
from database import ManhwaDB # Import the class directly
from scraper import ManhwaScraperManager
from pdf_processor import PDFProcessor
from scheduler import UpdateScheduler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ManhwaBot:
    def __init__(self):
        self.config = Config()
        self.config.validate() # Validate config on startup
        self.bot = Bot(token=self.config.BOT_TOKEN)
        self.dp = Dispatcher()
        self.db = ManhwaDB(self.config.DATABASE_PATH) # Pass db_path to ManhwaDB
        self.scraper_manager = ManhwaScraperManager()
        self.pdf_processor = PDFProcessor()
        self.scheduler = UpdateScheduler(self)

        # Register handlers
        self.register_handlers()

    def register_handlers(self):
        """Register bot command handlers"""
        self.dp.message(Command("start"))(self.cmd_start)
        self.dp.message(Command("add"))(self.cmd_add_manhwa)
        self.dp.message(Command("list"))(self.cmd_list_manhwa)
        self.dp.message(Command("remove"))(self.cmd_remove_manhwa)
        self.dp.message(Command("check"))(self.cmd_manual_check)
        self.dp.message(Command("status"))(self.cmd_status)
        self.dp.message(Command("setchannel"))(self.cmd_set_channel) # New command

    async def cmd_start(self, message: Message):
        """Handle /start command"""
        welcome_text = """
        🤖 **Manhwa Delivery Bot**
        Commands:
        /add <manhwa_url> - Add manhwa to tracking
        /list - Show tracked manhwa
        /remove <manhwa_name> - Remove manhwa
        /check - Manual update check
        /status - Bot status
        /setchannel <channel_id> - Set your output Telegram channel (e.g., -1001234567890)

        Bot will automatically check for updates every {} hours.
        """.format(self.config.UPDATE_INTERVAL_HOURS)
        await message.answer(welcome_text, parse_mode="Markdown")

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
            text += f"  Last: {manhwa.last_chapter_name or \'Unknown\'}\n\n"
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

    async def cmd_set_channel(self, message: Message):
        """Set the output Telegram channel for the user"""
        try:
            args = message.text.split(maxsplit=1)
            if len(args) < 2:
                await message.answer("Usage: /setchannel <numeric_channel_id>\n(e.g., /setchannel -1001234567890)")
                return
            
            channel_id = args[1] # Keep as string, Telegram IDs can be large
            user_id = message.from_user.id

            if self.db.set_user_output_channel(user_id, channel_id):
                await message.answer(f"✅ Your output channel has been set to: `{channel_id}`")
            else:
                await message.answer("❌ Failed to set your output channel. Please try again.")
        except Exception as e:
            logger.error(f"Error setting channel: {e}")
            await message.answer("❌ Error setting channel.")

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
                        logger.warning(f"No output channel set for user {manhwa.telegram_user_id} tracking {manhwa.name}. Skipping delivery of {chapter[\'name\']}.")
                        continue

                    success = await self.process_and_deliver_chapter(manhwa, chapter, user_output_channel)
                    if success:
                        updates.append((manhwa.name, chapter[\'name\']))
                        # Update database
                        self.db.update_manhwa_progress(
                            manhwa.name,
                            chapter[\'url\'],
                            chapter[\'name\']
                        )
            except Exception as e:
                logger.error(f"Error checking {manhwa.name}: {e}")
        return updates

    async def process_and_deliver_chapter(self, manhwa, chapter, output_channel_id: str) -> bool:
        """Download, process and deliver a chapter"""
        try:
            # Download chapter images
            images = await self.scraper_manager.download_chapter_images(
                chapter[\'url\'],
                manhwa.site_name
            )
            if not images:
                logger.error(f"No images found for {chapter[\'name\']}")
                return False

            # Process images and create PDF
            pdf_path = await self.pdf_processor.create_chapter_pdf(
                images,
                manhwa.name,
                chapter[\'name\']
            )
            if not pdf_path:
                logger.error(f"Failed to create PDF for {chapter[\'name\']}")
                return False

            # Generate thumbnail
            thumbnail_path = await self.pdf_processor.generate_thumbnail(pdf_path)

            # Send to Telegram channel
            await self.send_chapter_to_channel(pdf_path, manhwa.name, chapter[\'name\'], output_channel_id, thumbnail_path)

            # Cleanup
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if thumbnail_path and os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
            return True
        except Exception as e:
            logger.error(f"Error processing chapter {chapter[\'name\']}: {e}")
            return False

    async def send_chapter_to_channel(self, pdf_path, manhwa_name, chapter_name, chat_id: str, thumbnail_path: Optional[str] = None):
        """Send PDF to Telegram channel"""
        try:
            with open(pdf_path, "rb") as pdf_file:
                caption = f"📖 **{manhwa_name}**\\n{chapter_name}"
                await self.bot.send_document(
                    chat_id=chat_id, # Use the specific chat_id for the user
                    document=types.FSInputFile(pdf_path, filename=f"{manhwa_name} - {chapter_name}.pdf"),
                    caption=caption,
                    parse_mode="Markdown",
                    thumbnail=types.FSInputFile(thumbnail_path) if thumbnail_path else None
                )
            logger.info(f"Sent {chapter_name} to channel {chat_id}")
        except Exception as e:
            logger.error(f"Error sending to channel {chat_id}: {e}")

    async def start_bot(self):
        """Start the bot"""
        # Initialize database
        self.db.init_tables() # Ensure tables are created

        # Start scheduler
        self.scheduler.start()

        # Start polling
        logger.info("Starting Manhwa Bot...")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    bot = ManhwaBot()
    asyncio.run(bot.start_bot())
