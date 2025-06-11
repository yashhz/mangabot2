
# Manhwa Telegram Bot

A custom Telegram bot that automatically tracks ~100 manhwa series, detects new chapter releases, downloads images, adds watermarks, converts to PDF, and delivers to your Telegram channel.

## Features

- 🤖 Automatic manhwa tracking and delivery
- 📖 PDF generation with custom watermarks
- 🔄 Scheduled updates every 6 hours
- 🌐 Support for multiple manhwa sites
- 📊 SQLite database for tracking progress
- 🎯 Custom file naming: [Manhwa Name] - Chapter [Number].pdf

## Supported Sites

- ManhwaClan
- AsuraScans  
- FlameScans
- (Easily extensible for more sites)

## Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd manhwa-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your Telegram credentials
```

4. **Run the bot**
```bash
python main.py
```

## Configuration

### Required Environment Variables

- `API_ID` - Your Telegram API ID
- `API_HASH` - Your Telegram API Hash  
- `BOT_TOKEN` - Your bot token from @BotFather
- `CHANNEL_ID` - Numeric ID of your delivery channel

### Optional Settings

- `WATERMARK_TEXT` - Custom watermark text (default: "Personal use only - Yash")
- `UPDATE_INTERVAL_HOURS` - Check interval (default: 6)
- `DATABASE_PATH` - Database file location
- `TEMP_DIR` - Temporary files directory

## Bot Commands

- `/start` - Welcome message and help
- `/add <manhwa_url>` - Add manhwa to tracking
- `/list` - Show tracked manhwa
- `/remove <manhwa_name>` - Remove manhwa
- `/check` - Manual update check  
- `/status` - Bot status

## Usage

1. **Add a manhwa**
```
/add https://manhwaclan.com/manga/solo-leveling/
```

2. **List tracked manhwa**
```
/list
```

3. **Manual check for updates**
```
/check
```

The bot will automatically check for updates every 6 hours and deliver new chapters to your configured channel.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Telegram Bot  │    │  Manhwa Scraper  │    │  PDF Processor  │
│   Interface     │◄──►│     Module       │◄──►│     Module     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Database      │    │   Scheduler/     │    │   File Storage  │
│   Layer         │    │   Worker System  │    │   (Temporary)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Adding New Sites

1. Create a new scraper in `sites/` directory
2. Inherit from `BaseScraper`
3. Implement required methods:
   - `get_manhwa_info()`
   - `get_latest_chapters()`  
   - `get_chapter_images()`
4. Add to `ManhwaScraperManager.scrapers` dict

## Deployment

### Fly.io (Recommended)

1. **Install flyctl**
```bash
curl -L https://fly.io/install.sh | sh
```

2. **Initialize fly app**
```bash
fly apps create manhwa-bot
```

3. **Set environment variables**
```bash
fly secrets set BOT_TOKEN=your_token
fly secrets set CHANNEL_ID=your_channel_id
# ... other variables
```

4. **Deploy**
```bash
fly deploy
```

## Expected Volume
- ~100 tracked manhwa series
- 400-500 chapters per month  
- 4-5 updates per week across all series

## License

This project is for personal use only. Respect manhwa creators and publishers.
