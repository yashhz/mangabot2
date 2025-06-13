import aiohttp
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class BaseScraper:
    """Base class for site scrapers"""
    def __init__(self, site_name: str, base_url: str):
        self.site_name = site_name
        self.base_url = base_url

    async def get_manhwa_info(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """Get manhwa information"""
        raise NotImplementedError

    async def get_latest_chapters(self, session: aiohttp.ClientSession, url: str) -> List[Dict]:
        """Get latest chapters"""
        raise NotImplementedError

    async def get_chapter_images(self, session: aiohttp.ClientSession, chapter_url: str) -> List[str]:
        """Get chapter images"""
        raise NotImplementedError

    async def fetch_html(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch HTML content"""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None 