
# Manhwa Telegram Bot

A Python-based Telegram bot that automatically tracks manhwa series, downloads new chapters, adds watermarks, converts to PDF, and delivers them to your Telegram channel.

## Quick Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your values
   ```

3. **Required environment variables:**
   - `BOT_TOKEN`: Your Telegram bot token from @BotFather
   - `CHANNEL_ID`: Your Telegram channel ID (numeric)

4. **Run the bot:**
   ```bash
   python main.py
   ```

## Bot Commands

- `/start` - Welcome message and help
- `/add <url>` - Add manhwa to tracking
- `/list` - Show tracked manhwa
- `/remove <name>` - Remove manhwa from tracking
- `/check` - Manual update check
- `/status` - Bot status

## Features

- ✅ Automatic chapter detection
- ✅ Custom watermarking 
- ✅ PDF generation with proper naming
- ✅ SQLite database for tracking
- ✅ Scheduled updates every 6 hours
- ✅ Support for multiple manhwa sites

## Supported Sites

- ManhwaClan
- AsuraScans  
- FlameScans

Bot will automatically check for updates and deliver new chapters to your configured Telegram channel.
