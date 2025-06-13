import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
import img2pdf
from typing import List, Optional
import logging
from config import Config
import asyncio
import re
import aiohttp
import aiofiles
import io

logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self):
        self.config = Config()
        self.watermark_text = self.config.WATERMARK_TEXT
    
    async def add_watermark(self, image_url: str) -> Optional[str]:
        """Add watermark to an image"""
        try:
            # Create a temporary file for the downloaded image
            temp_input = f"temp_input_{os.urandom(4).hex()}.webp"
            temp_output = f"temp_output_{os.urandom(4).hex()}.webp"
            
            # Download the image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download image: {response.status}")
                        return None
                    
                    # Save the image to a temporary file
                    async with aiofiles.open(temp_input, 'wb') as f:
                        await f.write(await response.read())
            
            # Open and process the image
            with Image.open(temp_input) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Create a copy for drawing
                img_with_watermark = img.copy()
                draw = ImageDraw.Draw(img_with_watermark)
                
                # Get image dimensions
                width, height = img.size
                
                # Calculate font size (5% of image height)
                font_size = int(height * 0.05)
                try:
                    font = ImageFont.truetype("arial.ttf", font_size)
                except:
                    # Fallback to default font if arial.ttf is not available
                    font = ImageFont.load_default()
                
                # Calculate text size
                text_bbox = draw.textbbox((0, 0), self.watermark_text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # Calculate position (bottom right corner with padding)
                x = width - text_width - int(width * 0.02)  # 2% padding from right
                y = height - text_height - int(height * 0.02)  # 2% padding from bottom
                
                # Add semi-transparent watermark
                draw.text((x, y), self.watermark_text, font=font, fill=(128, 128, 128, 128))
                
                # Save the watermarked image
                img_with_watermark.save(temp_output, 'WEBP', quality=95)
            
            # Clean up the input file
            os.remove(temp_input)
            
            return temp_output
            
        except Exception as e:
            logger.error(f"Error adding watermark to {image_url}: {e}")
            # Clean up any temporary files
            for temp_file in [temp_input, temp_output]:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except:
                    pass
            return None
    
    async def create_chapter_pdf(self, image_urls: List[str], chapter_name: str, manhwa_url: str) -> Optional[str]:
        """Create a PDF from a list of image URLs"""
        try:
            # Extract chapter number from chapter name
            chapter_num = re.search(r'\d+(?:\.\d+)?', chapter_name)
            if not chapter_num:
                chapter_num = "0"
            else:
                chapter_num = chapter_num.group()

            # Extract manhwa name from URL
            manhwa_name = manhwa_url.split('/')[-1].replace('-', ' ').title()
            safe_manhwa_name = re.sub(r'[^a-zA-Z0-9\s-]', '', manhwa_name)

            # Create PDF filename
            pdf_filename = f"Chapter {chapter_num} - {safe_manhwa_name}.pdf"
            pdf_path = os.path.join(self.config.TEMP_DIR, pdf_filename)

            # Create temp directory if it doesn't exist
            os.makedirs(self.config.TEMP_DIR, exist_ok=True)

            # Download and process images concurrently
            async def process_image(url: str) -> Optional[bytes]:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as response:
                            if response.status != 200:
                                return None
                            
                            # Read image data
                            image_data = await response.read()
                            
                            # Process image in memory
                            with Image.open(io.BytesIO(image_data)) as img:
                                # Convert to RGB if necessary
                                if img.mode != 'RGB':
                                    img = img.convert('RGB')
                                
                                # Create a copy for watermarking
                                img_with_watermark = img.copy()
                                draw = ImageDraw.Draw(img_with_watermark)
                                
                                # Get image dimensions
                                width, height = img.size
                                
                                # Calculate font size (5% of image height)
                                font_size = int(height * 0.05)
                                try:
                                    font = ImageFont.truetype("arial.ttf", font_size)
                                except:
                                    font = ImageFont.load_default()
                                
                                # Calculate text size
                                text_bbox = draw.textbbox((0, 0), self.watermark_text, font=font)
                                text_width = text_bbox[2] - text_bbox[0]
                                text_height = text_bbox[3] - text_bbox[1]
                                
                                # Calculate position (bottom right corner with padding)
                                x = width - text_width - int(width * 0.02)
                                y = height - text_height - int(height * 0.02)
                                
                                # Add semi-transparent watermark
                                draw.text((x, y), self.watermark_text, font=font, fill=(128, 128, 128, 128))
                                
                                # Save to bytes buffer
                                output_buffer = io.BytesIO()
                                img_with_watermark.save(output_buffer, format='JPEG', quality=95)
                                return output_buffer.getvalue()
                                
                except Exception as e:
                    logger.error(f"Error processing image {url}: {e}")
                    return None

            # Process all images concurrently
            tasks = [process_image(url) for url in image_urls]
            processed_images = await asyncio.gather(*tasks)
            processed_images = [img for img in processed_images if img]  # Remove None values

            if not processed_images:
                logger.error("No images were successfully processed")
                return None

            # Create PDF from processed images
            with open(pdf_path, "wb") as f:
                f.write(img2pdf.convert(processed_images))

            return pdf_path

        except Exception as e:
            logger.error(f"Error creating PDF: {e}")
            return None
    
    def optimize_image(self, image_path: str, max_width: int = 1200) -> str:
        """Optimize image size and quality"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize if too large
                width, height = img.size
                if width > max_width:
                    ratio = max_width / width
                    new_height = int(height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                
                # Save optimized image
                optimized_path = image_path.replace('.jpg', '_opt.jpg')
                img.save(optimized_path, 'JPEG', quality=85, optimize=True)
                
                # Replace original
                os.remove(image_path)
                os.rename(optimized_path, image_path)
                
                return image_path
        
        except Exception as e:
            logger.error(f"Error optimizing image {image_path}: {e}")
            return image_path
