
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration management"""
    
    def __init__(self):
        # Telegram credentials
        self.BOT_TOKEN = os.getenv('BOT_TOKEN')
        self.CHANNEL_ID = os.getenv('CHANNEL_ID')
        
        # Bot settings
        self.WATERMARK_TEXT = os.getenv('WATERMARK_TEXT', 'Personal use only - Yash')
        self.UPDATE_INTERVAL_HOURS = int(os.getenv('UPDATE_INTERVAL_HOURS', 6))
        
        # File paths
        self.DATABASE_PATH = os.getenv('DATABASE_PATH', 'data/manhwa.db')
        self.TEMP_DIR = os.getenv('TEMP_DIR', 'temp')
        
        # Scraping settings
        self.REQUEST_DELAY = float(os.getenv('REQUEST_DELAY', 1.0))
        self.MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', 5))
        
        # Ensure directories exist
        os.makedirs(os.path.dirname(self.DATABASE_PATH), exist_ok=True)
        os.makedirs(self.TEMP_DIR, exist_ok=True)
    
    def validate(self):
        """Validate required configuration"""
        required = ['BOT_TOKEN', 'CHANNEL_ID']
        missing = [key for key in required if not getattr(self, key)]
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return True
