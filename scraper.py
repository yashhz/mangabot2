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
import os

logger = logging.getLogger(__name__)

class ManhwaScraperManager:
    def __init__(self):
        self.scrapers = {
            'manhwaclan.com': ManhwaClanScraper(),
            # 'asurascans.com': AsuraScansScraper(), # Add back when ready
            # 'flamescans.org': FlameScansScraper(), # Add back when ready
        }
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

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

    async def search_manhwa(self, query: str) -> List[Dict[str, str]]:
        """Search for manhwa using ManhwaClan scraper"""
        try:
            # Use ManhwaClan scraper for search
            scraper = self.scrapers.get('manhwaclan.com')
            if not scraper:
                logger.error("ManhwaClan scraper not available")
                return []
            
            logger.info(f"Searching for manhwa with query: '{query}'")
            results = await scraper.search_manhwa(query)
            logger.info(f"Search completed, found {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in search_manhwa: {e}")
            return []

    async def get_chapter_list(self, url: str, site_name: str) -> List[Dict[str, str]]:
        """Get list of chapters for a manhwa"""
        if site_name.lower() == "manhwaclan":
            return await self._get_manhwaclan_chapters(url)
        else:
            logger.error(f"Chapter list not implemented for site: {site_name}")
            return []

    async def _get_manhwaclan_chapters(self, url: str) -> List[Dict[str, str]]:
        """Get list of chapters from ManhwaClan"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch chapters: {response.status}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    chapters = []
                    # Find the chapter list
                    chapter_list = soup.find('div', class_='chapter-list')
                    if chapter_list:
                        for chapter in chapter_list.find_all('a'):
                            try:
                                chapter_url = chapter['href']
                                chapter_name = chapter.text.strip()
                                chapters.append({
                                    'name': chapter_name,
                                    'url': chapter_url
                                })
                            except Exception as e:
                                logger.error(f"Error parsing chapter: {e}")
                                continue
                    
                    return sorted(chapters, key=lambda x: float(re.search(r'\d+', x['name']).group()) if re.search(r'\d+', x['name']) else 0)
                    
        except Exception as e:
            logger.error(f"Error getting chapters from ManhwaClan: {e}")
            return []

    async def _download_manhwaclan_images(self, url: str) -> List[str]:
        """Download images from ManhwaClan chapter"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch chapter: {response.status}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find all images in the chapter
                    image_urls = []
                    for img in soup.find_all('img', class_='wp-manga-chapter-img'):
                        try:
                            img_url = img['src']
                            if img_url:
                                image_urls.append(img_url)
                        except Exception as e:
                            logger.error(f"Error parsing image URL: {e}")
                            continue

                    if not image_urls:
                        return []

                    # Download images concurrently
                    async def download_image(img_url: str, index: int) -> Optional[str]:
                        try:
                            async with session.get(img_url, headers=self.headers) as img_response:
                                if img_response.status == 200:
                                    img_data = await img_response.read()
                                    filename = f"temp/chapter_{index+1:03d}.jpg"
                                    with open(filename, 'wb') as f:
                                        f.write(img_data)
                                    return filename
                        except Exception as e:
                            logger.error(f"Error downloading image {img_url}: {e}")
                        return None

                    # Create tasks for concurrent downloads
                    tasks = [download_image(url, i) for i, url in enumerate(image_urls)]
                    downloaded_files = await asyncio.gather(*tasks)
                    
                    # Filter out None values and sort by filename
                    return sorted([f for f in downloaded_files if f is not None], 
                                key=lambda x: int(x.split('_')[1].split('.')[0]))
                    
        except Exception as e:
            logger.error(f"Error downloading ManhwaClan images: {e}")
            return []