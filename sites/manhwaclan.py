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
            chapter_ul = chapter_list.find('ul', class_='main version-chap no-volumn')
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
                    
                chapter_name = link.text.strip()
                chapter_url = urljoin(self.base_url, link['href'])
                
                chapters.append({
                    'name': chapter_name,
                    'url': chapter_url
                })
            
            # Sort chapters by number
            def get_chapter_num(chapter):
                try:
                    # Extract number from chapter name (e.g., "Chapter 1" -> 1)
                    return float(re.search(r'\d+(?:\.\d+)?', chapter['name']).group())
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

    async def search_manhwa(self, query: str) -> List[Dict[str, str]]:
        """Search for manhwa on ManhwaClan"""
        try:
            # Format the search URL - ManhwaClan uses a different search endpoint
            search_url = f"{self.base_url}/wp-admin/admin-ajax.php"
            logger.info(f"Searching ManhwaClan for: {query}")
            
            async with aiohttp.ClientSession() as session:
                # First get the search page to get any necessary tokens
                async with session.get(f"{self.base_url}/") as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch search page: {response.status}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find the search form
                    search_form = soup.find('form', class_='search-form')
                    if not search_form:
                        logger.error("Could not find search form")
                        return []
                    
                    # Get the search action URL
                    search_action = search_form.get('action', '')
                    if not search_action:
                        search_action = f"{self.base_url}/"
                    
                    # Now perform the search
                    search_data = {
                        'action': 'wp-manga-search-manga',
                        'title': query
                    }
                    
                    async with session.post(search_action, data=search_data) as search_response:
                        if search_response.status != 200:
                            logger.error(f"Failed to perform search: {search_response.status}")
                            return []
                        
                        search_html = await search_response.text()
                        search_soup = BeautifulSoup(search_html, 'html.parser')
                        
                        # Find search results
                        results = []
                        manga_items = search_soup.find_all('div', class_='tab-thumb c-image-hover')
                        
                        for item in manga_items:
                            try:
                                # Get the title and link
                                title_elem = item.find('a', class_='post-title')
                                if not title_elem:
                                    continue
                                
                                title = title_elem.text.strip()
                                link = title_elem['href']
                                
                                # Get the thumbnail
                                img_elem = item.find('img')
                                thumbnail = img_elem['src'] if img_elem else None
                                
                                results.append({
                                    'title': title,
                                    'url': link,
                                    'thumbnail': thumbnail
                                })
                            except Exception as e:
                                logger.error(f"Error parsing search result: {e}")
                                continue
                        
                        logger.info(f"Found {len(results)} search results for query: {query}")
                        return results[:5]  # Return top 5 results
                    
        except Exception as e:
            logger.error(f"Error searching ManhwaClan: {e}")
            return []
