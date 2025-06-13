import asyncio
import aiohttp
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import logging
from sites.manhwaclan import ManhwaClanScraper
# from sites.asurascans import AsuraScansScraper # Commented out for now
# from sites.flamescans import FlameScansScraper # Commented out for now

logger = logging.getLogger(__name__)

class ManhwaScraperManager:
    def __init__(self):
        self.scrapers = {
            'manhwaclan.com': ManhwaClanScraper(),
            # 'asurascans.com': AsuraScansScraper(), # Add back when ready
            # 'flamescans.org': FlameScansScraper(), # Add back when ready
        }
        self.session = None

    async def get_session(self):
        """Get or create aiohttp session"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
        return self.session

    async def close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    def get_scraper(self, url: str):
        """Get appropriate scraper for URL"""
        domain = urlparse(url).netloc.lower()
        # Remove www. prefix if present
        domain = domain.replace('www.', '')
        return self.scrapers.get(domain)

    async def add_manhwa(self, url: str) -> Dict:
        """Add manhwa and get basic info"""
        try:
            scraper = self.get_scraper(url)
            if not scraper:
                return {'success': False, 'error': 'Unsupported site'}
            session = await self.get_session()
            info = await scraper.get_manhwa_info(session, url)
            if info:
                return {
                    'success': True,
                    'name': info['name'],
                    'site': info['site'],
                    'latest_chapter': info.get('latest_chapter'),
                    'latest_chapter_url': info.get('latest_chapter_url')
                }
            else:
                return {'success': False, 'error': 'Failed to parse manhwa info'}
        except Exception as e:
            logger.error(f"Error adding manhwa {url}: {e}")
            return {'success': False, 'error': str(e)}

    async def check_new_chapters(self, manhwa) -> List[Dict]:
        """Check for new chapters of a manhwa"""
        try:
            scraper = self.get_scraper(manhwa.url)
            if not scraper:
                return []
            session = await self.get_session()
            chapters = await scraper.get_latest_chapters(session, manhwa.url)
            # Filter new chapters
            new_chapters = []
            for chapter in chapters:
                if chapter['url'] != manhwa.last_chapter_url:
                    new_chapters.append(chapter)
                else:
                    break # Found the last read chapter
            return new_chapters
        except Exception as e:
            logger.error(f"Error checking chapters for {manhwa.name}: {e}")
            return []

    async def download_chapter_images(self, chapter_url: str, site_name: str) -> List[str]:
        """Download all images from a chapter"""
        try:
            scraper = self.get_scraper(chapter_url)
            if not scraper:
                return []
            session = await self.get_session()
            images = await scraper.get_chapter_images(session, chapter_url)
            # Download images to temp directory
            downloaded_images = []
            for i, img_url in enumerate(images):
                try:
                    async with session.get(img_url) as response:
                        if response.status == 200:
                            content = await response.read()
                            filename = f"temp/chapter_{i+1:03d}.jpg"
                            with open(filename, 'wb') as f:
                                f.write(content)
                            downloaded_images.append(filename)
                except Exception as e:
                    logger.error(f"Error downloading image {img_url}: {e}")
            return downloaded_images
        except Exception as e:
            logger.error(f"Error downloading chapter images: {e}")
            return []
