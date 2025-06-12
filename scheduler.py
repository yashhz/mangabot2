import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
from config import Config

logger = logging.getLogger(__name__)

class UpdateScheduler:
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.config = Config()
        self.scheduler = AsyncIOScheduler()

        # Schedule update checks
        self.scheduler.add_job(
            self.scheduled_update_check,
            IntervalTrigger(hours=self.config.UPDATE_INTERVAL_HOURS),
            id='manhwa_update_check',
            name='Manhwa Update Check'
        )

    async def scheduled_update_check(self):
        """Scheduled update check for all manhwa"""
        try:
            logger.info("Starting scheduled update check...")
            # Fetch all manhwa from the database
            all_manhwa = self.bot.db.get_all_manhwa()
            if not all_manhwa:
                logger.info("No manhwa tracked for updates.")
                return

            for manhwa in all_manhwa:
                logger.info(f"Checking for updates for {manhwa.name} (User: {manhwa.telegram_user_id})")
                new_chapters = await self.bot.scraper_manager.check_new_chapters(manhwa)

                if new_chapters:
                    logger.info(f"Found {len(new_chapters)} new chapters for {manhwa.name}")
                    for chapter in new_chapters:
                        success = await self.bot.process_and_send_chapter(manhwa, chapter)
                        if success:
                            # Update last_chapter_url and last_chapter_name in DB
                            self.bot.db.update_manhwa_progress(
                                manhwa.name, chapter["url"], chapter["name"]
                            )
                            logger.info(f"Successfully processed and sent {chapter["name"]} for {manhwa.name}")
                        else:
                            logger.error(f"Failed to process and send {chapter["name"]} for {manhwa.name}")
                else:
                    logger.info(f"No new chapters for {manhwa.name}")

        except Exception as e:
            logger.error(f"Error in scheduled update check: {e}")

    def start(self):
        """Start the scheduler"""
        try:
            self.scheduler.start()
            logger.info(f"Scheduler started - checking every {self.config.UPDATE_INTERVAL_HOURS} hours")
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")

    def stop(self):
        """Stop the scheduler"""
        try:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
