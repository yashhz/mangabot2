import os

class Config:
    def __init__(self):
        self.BOT_TOKEN = os.environ.get("BOT_TOKEN")
        self.DATABASE_PATH = os.environ.get("DATABASE_PATH", "data/manhwa.db")
        self.TEMP_DIR = os.environ.get("TEMP_DIR", "temp")
        self.WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "Personal use only - ManhwaBot")

    def validate(self):
        if not self.BOT_TOKEN:
            raise ValueError("BOT_TOKEN environment variable not set.")
        # Ensure temp directory exists
        os.makedirs(self.TEMP_DIR, exist_ok=True)
