
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont
import img2pdf
from typing import List, Optional
import logging
from config import Config

logger = logging.getLogger(__name__)

class PDFProcessor:
    def __init__(self):
        self.config = Config()
        self.watermark_text = self.config.WATERMARK_TEXT
    
    def add_watermark(self, image_path: str) -> str:
        """Add watermark to image"""
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Create a copy for watermarking
                watermarked = img.copy()
                
                # Create drawing context
                draw = ImageDraw.Draw(watermarked)
                
                # Calculate watermark position and size
                width, height = watermarked.size
                font_size = max(20, min(width, height) // 40)
                
                try:
                    # Try to use a nice font
                    font = ImageFont.truetype("arial.ttf", font_size)
                except OSError:
                    # Fallback to default font
                    font = ImageFont.load_default()
                
                # Get text dimensions
                bbox = draw.textbbox((0, 0), self.watermark_text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                # Position watermark in bottom right
                x = width - text_width - 20
                y = height - text_height - 20
                
                # Add semi-transparent background
                margin = 10
                draw.rectangle([
                    x - margin, y - margin,
                    x + text_width + margin, y + text_height + margin
                ], fill=(0, 0, 0, 128))
                
                # Add watermark text
                draw.text((x, y), self.watermark_text, fill=(255, 255, 255, 255), font=font)
                
                # Save watermarked image
                watermarked_path = image_path.replace('.jpg', '_watermarked.jpg')
                watermarked.save(watermarked_path, 'JPEG', quality=95)
                
                return watermarked_path
        
        except Exception as e:
            logger.error(f"Error adding watermark to {image_path}: {e}")
            return image_path  # Return original if watermarking fails
    
    async def create_chapter_pdf(self, image_paths: List[str], manhwa_name: str, chapter_name: str) -> Optional[str]:
        """Create PDF from chapter images"""
        try:
            if not image_paths:
                return None
            
            # Add watermarks to all images
            watermarked_images = []
            for img_path in image_paths:
                watermarked_path = self.add_watermark(img_path)
                watermarked_images.append(watermarked_path)
            
            # Create PDF filename
            safe_manhwa_name = "".join(c for c in manhwa_name if c.isalnum() or c in (' ', '-', '_')).strip()
            safe_chapter_name = "".join(c for c in chapter_name if c.isalnum() or c in (' ', '-', '_')).strip()
            pdf_filename = f"{safe_manhwa_name} - {safe_chapter_name}.pdf"
            pdf_path = os.path.join(self.config.TEMP_DIR, pdf_filename)
            
            # Convert images to PDF
            with open(pdf_path, "wb") as f:
                f.write(img2pdf.convert(watermarked_images))
            
            # Cleanup watermarked images
            for img_path in watermarked_images:
                if img_path != image_paths[watermarked_images.index(img_path)]:  # Only delete if watermarked
                    try:
                        os.remove(img_path)
                    except OSError:
                        pass
            
            # Cleanup original images
            for img_path in image_paths:
                try:
                    os.remove(img_path)
                except OSError:
                    pass
            
            logger.info(f"Created PDF: {pdf_filename}")
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
