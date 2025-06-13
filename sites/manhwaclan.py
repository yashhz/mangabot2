import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict, Optional
import aiohttp
import logging
from base_scraper import BaseScraper

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
            # Find the chapter list container
            chapter_list = soup.find('div', class_='listing-chapters_wrap')
            if not chapter_list:
                logger.error("Could not find chapter list container")
                return []

            # Find the unordered list containing chapters
            chapter_ul = chapter_list.find('ul', class_='main')
            if not chapter_ul:
                logger.error("Could not find chapter list")
                return []

            # Find all chapter list items
            chapter_items = chapter_ul.find_all('li', class_='wp-manga-chapter')
            logger.info(f"Found {len(chapter_items)} chapter items")
            
            for item in chapter_items:
                # Get the chapter link
                link = item.find('a')
                if not link:
                    continue
                    
                chapter_name = link.get_text(strip=True)
                chapter_url = urljoin(self.base_url, link['href'])
                
                chapters.append({
                    'name': chapter_name,
                    'url': chapter_url
                })
            
            # Sort chapters by number
            def get_chapter_num(chapter):
                try:
                    # Extract number from chapter name (e.g., "Chapter 1" -> 1)
                    return int(re.search(r'\d+', chapter['name']).group())
                except:
                    return 0
            
            chapters.sort(key=get_chapter_num)
            logger.info(f"Found {len(chapters)} chapters")
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
            # Find the reading content container
            reading_content = soup.find('div', class_='reading-content')
            if not reading_content:
                logger.error("Could not find reading content")
                return []

            # Find all image containers
            image_containers = reading_content.find_all('div', class_='page-break')
            logger.info(f"Found {len(image_containers)} image containers")
            
            for container in image_containers:
                # Find the image
                img = container.find('img', class_='wp-manga-chapter-img')
                if not img:
                    continue
                    
                src = img.get('src') or img.get('data-src')
                if src:
                    if not src.startswith('http'):
                        src = urljoin(self.base_url, src)
                    images.append(src)
            
            logger.info(f"Found {len(images)} images in chapter")
            return images
        
        except Exception as e:
            logger.error(f"Error getting chapter images: {e}")
            return []
