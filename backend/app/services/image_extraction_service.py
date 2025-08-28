"""
Image extraction service for comprehensive image extraction from PDFs.

This service provides enhanced image extraction capabilities including format conversion,
size optimization, and comprehensive metadata extraction.
"""

import logging
import io
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image, ImageFile
import fitz  # PyMuPDF

from app.utils.temp_file_manager import TempFileManager
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)

# Allow loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageExtractionService:
    """Service for extracting images from PDF documents."""
    
    # Maximum image size limit (10MB as per project requirements)
    MAX_IMAGE_SIZE_MB = 10
    MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
    
    # Supported output formats
    SUPPORTED_FORMATS = ['PNG', 'JPEG', 'TIFF', 'WEBP']
    
    def __init__(self, session_id: str):
        """Initialize the image extraction service.
        
        Args:
            session_id: Unique session identifier for file management
        """
        self.session_id = session_id
        self.temp_file_manager = TempFileManager(session_id)
    
    @handle_errors
    def extract_images(
        self,
        file_path: Path,
        page_range: Optional[Tuple[int, int]] = None,
        output_format: str = 'PNG',
        quality: int = 95,
        include_page_renders: bool = False,
        dpi: int = 300
    ) -> Dict[str, Any]:
        """Extract images from PDF file.
        
        Args:
            file_path: Path to the PDF file
            page_range: Optional tuple of (start_page, end_page) (1-indexed)
            output_format: Target output format ('PNG', 'JPEG', 'TIFF', 'WEBP')
            quality: Output quality for JPEG (1-100)
            include_page_renders: Whether to also render pages as images
            dpi: DPI for page rendering
            
        Returns:
            Dictionary containing extraction results and statistics
        """
        logger.info(f"Starting image extraction from {file_path}")
        
        if output_format.upper() not in self.SUPPORTED_FORMATS:
            return {
                'success': False,
                'error': f'Unsupported output format: {output_format}',
                'images': [],
                'files': []
            }
        
        try:
            doc = fitz.open(str(file_path))
            total_pages = len(doc)
            
            # Determine pages to process
            if page_range:
                start, end = page_range
                start = max(1, start) - 1  # Convert to 0-indexed
                end = min(total_pages, end)
                pages_to_process = list(range(start, end))
            else:
                pages_to_process = list(range(total_pages))
            
            extraction_stats = {
                'pages_processed': 0,
                'embedded_images_found': 0,
                'embedded_images_extracted': 0,
                'page_renders_created': 0,
                'format_conversions': 0,
                'size_optimizations': 0
            }
            
            extracted_images = []
            output_files = []
            
            # Extract embedded images
            embedded_results = self._extract_embedded_images(
                doc, pages_to_process, output_format, quality
            )
            extracted_images.extend(embedded_results['images'])
            output_files.extend(embedded_results['files'])
            extraction_stats['embedded_images_found'] = embedded_results['stats']['found']
            extraction_stats['embedded_images_extracted'] = embedded_results['stats']['extracted']
            extraction_stats['format_conversions'] += embedded_results['stats']['conversions']
            extraction_stats['size_optimizations'] += embedded_results['stats']['optimizations']
            
            # Extract page renders if requested
            if include_page_renders:
                render_results = self._extract_page_images(
                    doc, pages_to_process, output_format, quality, dpi
                )
                extracted_images.extend(render_results['images'])
                output_files.extend(render_results['files'])
                extraction_stats['page_renders_created'] = render_results['stats']['rendered']
            
            extraction_stats['pages_processed'] = len(pages_to_process)
            
            doc.close()
            
            logger.info(f"Image extraction completed: {len(extracted_images)} images extracted")
            
            return {
                'success': True,
                'images': extracted_images,
                'files': output_files,
                'statistics': extraction_stats,
                'page_range': page_range,
                'output_format': output_format.upper(),
                'total_pages_processed': len(pages_to_process)
            }
            
        except Exception as e:
            logger.error(f"Error in image extraction: {e}")
            return {
                'success': False,
                'error': str(e),
                'images': [],
                'files': []
            }
    
    def _extract_embedded_images(
        self,
        doc,
        pages_to_process: List[int],
        output_format: str,
        quality: int
    ) -> Dict[str, Any]:
        """Extract embedded images from PDF pages.
        
        Args:
            doc: PyMuPDF document object
            pages_to_process: List of page indices (0-indexed)
            output_format: Target format for output
            quality: Output quality
            
        Returns:
            Dictionary with extracted images, files, and statistics
        """
        images = []
        files = []
        stats = {'found': 0, 'extracted': 0, 'conversions': 0, 'optimizations': 0}
        downloads_dir = self.temp_file_manager.downloads_dir
        
        for page_num in pages_to_process:
            try:
                page = doc.load_page(page_num)
                image_list = page.get_images()
                stats['found'] += len(image_list)
                
                for img_index, img in enumerate(image_list):
                    try:
                        # Extract image data
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image["ext"]
                        
                        # Validate image size
                        if not self._validate_image_size(image_bytes):
                            logger.warning(f"Skipping oversized image on page {page_num + 1}")
                            continue
                        
                        # Convert format if needed
                        if image_ext.upper() != output_format.upper():
                            converted_bytes = self._convert_image_format(
                                image_bytes, image_ext, output_format, quality
                            )
                            if converted_bytes:
                                image_bytes = converted_bytes
                                image_ext = output_format.lower()
                                stats['conversions'] += 1
                        
                        # Optimize image if needed
                        optimized_bytes = self._optimize_image_quality(
                            image_bytes, output_format, quality
                        )
                        if optimized_bytes and len(optimized_bytes) < len(image_bytes):
                            image_bytes = optimized_bytes
                            stats['optimizations'] += 1
                        
                        # Save image file
                        filename = f"image_page_{page_num + 1}_{img_index + 1}.{image_ext}"
                        file_path = downloads_dir / filename
                        
                        with open(file_path, 'wb') as f:
                            f.write(image_bytes)
                        
                        # Extract image metadata
                        metadata = self._extract_image_metadata(
                            image_bytes, page_num + 1, img_index
                        )
                        
                        # Create image info
                        image_info = {
                            'filename': filename,
                            'page': page_num + 1,
                            'image_index': img_index,
                            'file_size': len(image_bytes),
                            'format': output_format.upper(),
                            'source_format': base_image["ext"].upper(),
                            'metadata': metadata
                        }
                        
                        file_info = {
                            'filename': filename,
                            'file_path': str(file_path),
                            'file_size': file_path.stat().st_size,
                            'type': 'embedded_image',
                            'page': page_num + 1,
                            'image_index': img_index
                        }
                        
                        images.append(image_info)
                        files.append(file_info)
                        stats['extracted'] += 1
                        
                        logger.debug(f"Extracted image: {filename}")
                        
                    except Exception as e:
                        logger.warning(f"Failed to extract image {img_index} from page {page_num + 1}: {e}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Failed to process page {page_num + 1}: {e}")
                continue
        
        return {'images': images, 'files': files, 'stats': stats}
    
    def _extract_page_images(
        self,
        doc,
        pages_to_process: List[int],
        output_format: str,
        quality: int,
        dpi: int
    ) -> Dict[str, Any]:
        """Render PDF pages as images.
        
        Args:
            doc: PyMuPDF document object
            pages_to_process: List of page indices (0-indexed)
            output_format: Target format for output
            quality: Output quality
            dpi: DPI for rendering
            
        Returns:
            Dictionary with rendered images, files, and statistics
        """
        images = []
        files = []
        stats = {'rendered': 0}
        downloads_dir = self.temp_file_manager.downloads_dir
        
        for page_num in pages_to_process:
            try:
                page = doc.load_page(page_num)
                
                # Calculate matrix for desired DPI
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PIL Image for processing
                img_data = pix.tobytes("png")
                
                # Validate size
                if not self._validate_image_size(img_data):
                    logger.warning(f"Skipping oversized page render for page {page_num + 1}")
                    continue
                
                # Convert format if needed
                if output_format.upper() != 'PNG':
                    converted_data = self._convert_image_format(
                        img_data, 'PNG', output_format, quality
                    )
                    if converted_data:
                        img_data = converted_data
                
                # Save page render
                ext = output_format.lower()
                filename = f"page_render_{page_num + 1}.{ext}"
                file_path = downloads_dir / filename
                
                with open(file_path, 'wb') as f:
                    f.write(img_data)
                
                # Extract metadata
                metadata = self._extract_image_metadata(img_data, page_num + 1, 0)
                metadata['dpi'] = dpi
                metadata['source'] = 'page_render'
                
                # Create image info
                image_info = {
                    'filename': filename,
                    'page': page_num + 1,
                    'image_index': 0,
                    'file_size': len(img_data),
                    'format': output_format.upper(),
                    'source_format': 'PDF_PAGE',
                    'metadata': metadata,
                    'type': 'page_render'
                }
                
                file_info = {
                    'filename': filename,
                    'file_path': str(file_path),
                    'file_size': file_path.stat().st_size,
                    'type': 'page_render',
                    'page': page_num + 1,
                    'dpi': dpi
                }
                
                images.append(image_info)
                files.append(file_info)
                stats['rendered'] += 1
                
                logger.debug(f"Rendered page {page_num + 1} as image: {filename}")
                
            except Exception as e:
                logger.warning(f"Failed to render page {page_num + 1}: {e}")
                continue
        
        return {'images': images, 'files': files, 'stats': stats}
    
    def _convert_image_format(
        self,
        image_data: bytes,
        source_format: str,
        target_format: str,
        quality: int
    ) -> Optional[bytes]:
        """Convert image format using PIL.
        
        Args:
            image_data: Original image bytes
            source_format: Source image format
            target_format: Target image format
            quality: Output quality for JPEG
            
        Returns:
            Converted image bytes or None if conversion failed
        """
        try:
            # Load image with PIL
            image = Image.open(io.BytesIO(image_data))
            
            # Handle color space conversion
            image = self._handle_color_space_conversion(image)
            
            # Prepare save options
            save_options = {}
            if target_format.upper() == 'JPEG':
                save_options['quality'] = quality
                save_options['optimize'] = True
                # Convert to RGB if necessary for JPEG
                if image.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'P':
                        image = image.convert('RGBA')
                    background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
            elif target_format.upper() == 'PNG':
                save_options['optimize'] = True
            elif target_format.upper() == 'WEBP':
                save_options['quality'] = quality
                save_options['method'] = 6  # Better compression
            
            # Convert and save to bytes
            output_buffer = io.BytesIO()
            image.save(output_buffer, format=target_format.upper(), **save_options)
            return output_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Failed to convert image from {source_format} to {target_format}: {e}")
            return None
    
    def _handle_color_space_conversion(self, image: Image.Image) -> Image.Image:
        """Handle color space conversion for unsupported formats.
        
        Args:
            image: PIL Image object
            
        Returns:
            Image with compatible color space
        """
        if image.mode == 'CMYK':
            # Convert CMYK to RGB
            return image.convert('RGB')
        elif image.mode == 'LAB':
            # Convert LAB to RGB
            return image.convert('RGB')
        elif image.mode == '1':
            # Convert 1-bit to grayscale
            return image.convert('L')
        
        return image
    
    def _validate_image_size(self, image_data: bytes) -> bool:
        """Validate image size against maximum limit.
        
        Args:
            image_data: Image bytes to validate
            
        Returns:
            True if image is within size limits
        """
        return len(image_data) <= self.MAX_IMAGE_SIZE_BYTES
    
    def _optimize_image_quality(
        self,
        image_data: bytes,
        target_format: str,
        quality: int
    ) -> Optional[bytes]:
        """Optimize image quality and size.
        
        Args:
            image_data: Original image bytes
            target_format: Target format
            quality: Desired quality
            
        Returns:
            Optimized image bytes or None if optimization failed
        """
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # Only optimize if format supports quality settings
            if target_format.upper() not in ['JPEG', 'WEBP']:
                return None
            
            # Try different quality settings for size optimization
            best_quality = quality
            best_size = len(image_data)
            best_data = image_data
            
            for test_quality in [quality - 10, quality - 20]:
                if test_quality < 10:
                    break
                
                output_buffer = io.BytesIO()
                save_options = {'quality': test_quality, 'optimize': True}
                
                if target_format.upper() == 'WEBP':
                    save_options['method'] = 6
                
                image.save(output_buffer, format=target_format.upper(), **save_options)
                test_data = output_buffer.getvalue()
                
                # If size reduction is significant (>20%) and still within limits
                if len(test_data) < best_size * 0.8 and self._validate_image_size(test_data):
                    best_data = test_data
                    best_size = len(test_data)
                    best_quality = test_quality
                else:
                    break
            
            return best_data if best_quality < quality else None
            
        except Exception as e:
            logger.error(f"Failed to optimize image: {e}")
            return None
    
    def _extract_image_metadata(
        self,
        image_data: bytes,
        page_num: int,
        image_index: int
    ) -> Dict[str, Any]:
        """Extract comprehensive image metadata.
        
        Args:
            image_data: Image bytes
            page_num: Page number (1-indexed)
            image_index: Image index on page
            
        Returns:
            Dictionary containing image metadata
        """
        metadata = {
            'page': page_num,
            'index': image_index,
            'file_size_bytes': len(image_data),
            'file_size_mb': round(len(image_data) / (1024 * 1024), 2)
        }
        
        try:
            image = Image.open(io.BytesIO(image_data))
            
            # Basic image properties
            metadata.update({
                'width': image.width,
                'height': image.height,
                'mode': image.mode,
                'format': image.format or 'Unknown',
                'has_transparency': image.mode in ('RGBA', 'LA', 'P') or 'transparency' in image.info
            })
            
            # DPI information
            dpi = image.info.get('dpi', (72, 72))
            if isinstance(dpi, (list, tuple)) and len(dpi) >= 2:
                metadata['dpi_x'] = dpi[0]
                metadata['dpi_y'] = dpi[1]
            else:
                metadata['dpi_x'] = dpi if isinstance(dpi, (int, float)) else 72
                metadata['dpi_y'] = metadata['dpi_x']
            
            # Color information
            if hasattr(image, 'getcolors'):
                try:
                    colors = image.getcolors(maxcolors=256*256*256)
                    if colors:
                        metadata['unique_colors'] = len(colors)
                        metadata['is_grayscale'] = image.mode in ('L', '1') or all(r == g == b for r, g, b in [color[1][:3] if len(color[1]) >= 3 else (color[1], color[1], color[1]) for color in colors[:100]])
                except:
                    pass
            
            # Additional format-specific metadata
            if hasattr(image, 'info') and image.info:
                for key, value in image.info.items():
                    if key not in ['dpi'] and isinstance(value, (str, int, float, bool)):
                        metadata[f'exif_{key}'] = value
            
        except Exception as e:
            logger.warning(f"Failed to extract detailed metadata for image: {e}")
        
        return metadata
    
    def _generate_image_thumbnails(
        self,
        image_data: bytes,
        thumbnail_size: Tuple[int, int] = (200, 200)
    ) -> Optional[bytes]:
        """Generate thumbnail for image preview.
        
        Args:
            image_data: Original image bytes
            thumbnail_size: Desired thumbnail dimensions
            
        Returns:
            Thumbnail image bytes or None if generation failed
        """
        try:
            image = Image.open(io.BytesIO(image_data))
            image.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                image = background
            
            output_buffer = io.BytesIO()
            image.save(output_buffer, format='JPEG', quality=85, optimize=True)
            return output_buffer.getvalue()
            
        except Exception as e:
            logger.error(f"Failed to generate thumbnail: {e}")
            return None