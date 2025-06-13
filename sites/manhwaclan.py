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
        """Search for manhwa on ManhwaClan using the correct search format"""
        try:
            # Use the correct search URL format with post_type parameter
            search_url = f"{self.base_url}/?s={query.replace(' ', '+')}&post_type=wp-manga"
            logger.info(f"Searching ManhwaClan with URL: {search_url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to fetch search results: {response.status}")
                        return []
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    results = []
                    
                    # Find the main search results container
                    search_container = soup.find('div', class_='c-tabs-item__content')
                    if not search_container:
                        logger.warning("Could not find search results container")
                        return []
                    
                    # Find all individual search result entries
                    # Each result is in a div with class "row c-tabs-item__content"
                    result_items = search_container.find_all('div', class_='row c-tabs-item__content')
                    logger.info(f"Found {len(result_items)} search result items")
                    
                    for item in result_items:
                        try:
                            # Find the manga title and URL within the h3 > a structure
                            title_container = item.find('div', class_='post-title')
                            if not title_container:
                                continue
                                
                            title_elem = title_container.find('h3', class_='h4')
                            if not title_elem:
                                continue
                                
                            title_link = title_elem.find('a')
                            if not title_link:
                                continue
                            
                            title = title_link.text.strip()
                            url = title_link['href']
                            
                            # Ensure URL is absolute
                            if not url.startswith('http'):
                                url = urljoin(self.base_url, url)
                            
                            # Find the thumbnail image
                            thumbnail = None
                            thumb_container = item.find('div', class_='tab-thumb c-image-hover')
                            if thumb_container:
                                img_elem = thumb_container.find('img')
                                if img_elem:
                                    thumbnail = img_elem.get('src')
                                    if thumbnail and not thumbnail.startswith('http'):
                                        thumbnail = urljoin(self.base_url, thumbnail)
                            
                            # Extract additional info like genres and status if available
                            summary_container = item.find('div', class_='tab-summary')
                            genres = []
                            status = None
                            
                            if summary_container:
                                # Try to find genres
                                genre_container = summary_container.find('div', class_='mg_genres')
                                if genre_container:
                                    genre_links = genre_container.find_all('a')
                                    genres = [link.text.strip() for link in genre_links]
                                
                                # Try to find status
                                status_container = summary_container.find('div', class_='mg_status')
                                if status_container:
                                    status_elem = status_container.find('div', class_='summary-content')
                                    if status_elem:
                                        status = status_elem.text.strip()
                            
                            result = {
                                'title': title,
                                'url': url,
                                'thumbnail': thumbnail,
                                'genres': genres,
                                'status': status
                            }
                            
                            results.append(result)
                            
                        except Exception as e:
                            logger.error(f"Error parsing individual search result: {e}")
                            continue
                    
                    logger.info(f"Successfully parsed {len(results)} search results for query: '{query}'")
                    return results[:10]  # Return top 10 results
                    
        except Exception as e:
            logger.error(f"Error searching ManhwaClan for '{query}': {e}")
            return []