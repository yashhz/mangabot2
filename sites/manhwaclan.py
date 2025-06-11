
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict, Optional
import aiohttp
import logging
from scraper import BaseScraper

logger = logging.getLogger(__name__)

class ManhwaClanScraper(BaseScraper):
    def __init__(self):
        super().__init__('manhwaclan', 'https://manhwaclan.com')
    
    async def get_manhwa_info(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """Get manhwa information from ManhwaClan"""
        html = await self.fetch_html(session, url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        try:
            # Extract manhwa name
            title_elem = soup.find('h1', class_='entry-title') or soup.find('h1')
            name = title_elem.get_text(strip=True) if title_elem else 'Unknown'
            
            # Extract latest chapter
            latest_chapter_elem = soup.find('a', href=re.compile(r'/chapter-\d+'))
            latest_chapter = None
            latest_chapter_url = None
            
            if latest_chapter_elem:
                latest_chapter = latest_chapter_elem.get_text(strip=True)
                latest_chapter_url = urljoin(self.base_url, latest_chapter_elem['href'])
            
            return {
                'name': name,
                'site': self.site_name,
                'latest_chapter': latest_chapter,
                'latest_chapter_url': latest_chapter_url
            }
        
        except Exception as e:
            logger.error(f"Error parsing manhwa info: {e}")
            return None
    
    async def get_latest_chapters(self, session: aiohttp.ClientSession, url: str) -> List[Dict]:
        """Get latest chapters from ManhwaClan"""
        html = await self.fetch_html(session, url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        chapters = []
        
        try:
            # Find chapter links
            chapter_links = soup.find_all('a', href=re.compile(r'/chapter-\d+'))
            
            for link in chapter_links[:10]:  # Get last 10 chapters
                chapter_name = link.get_text(strip=True)
                chapter_url = urljoin(self.base_url, link['href'])
                
                chapters.append({
                    'name': chapter_name,
                    'url': chapter_url
                })
            
            return chapters
        
        except Exception as e:
            logger.error(f"Error getting chapters: {e}")
            return []
    
    async def get_chapter_images(self, session: aiohttp.ClientSession, chapter_url: str) -> List[str]:
        """Get chapter images from ManhwaClan"""
        html = await self.fetch_html(session, chapter_url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        images = []
        
        try:
            # Find images in reading area
            img_tags = soup.find_all('img', src=re.compile(r'\.(jpg|jpeg|png|webp)'))
            
            for img in img_tags:
                src = img.get('src') or img.get('data-src')
                if src and any(x in src for x in ['chapter', 'page', 'scan']):
                    if not src.startswith('http'):
                        src = urljoin(self.base_url, src)
                    images.append(src)
            
            return images
        
        except Exception as e:
            logger.error(f"Error getting chapter images: {e}")
            return []
