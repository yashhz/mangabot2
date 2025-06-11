
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
            
            updates = await self.bot.check_for_updates()
            
            if updates:
                logger.info(f"Found {len(updates)} new chapters")
                
                # Send summary to admin (if configured)
                summary_text = f"🔄 **Update Summary**\n\n"
                summary_text += f"Found {len(updates)} new chapters:\n\n"
                
                for manhwa_name, chapter_name in updates:
                    summary_text += f"• {manhwa_name}: {chapter_name}\n"
                
                # You could send this to a specific admin chat
                # await self.bot.bot.send_message(chat_id=ADMIN_CHAT_ID, text=summary_text)
            else:
                logger.info("No new chapters found")
        
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
