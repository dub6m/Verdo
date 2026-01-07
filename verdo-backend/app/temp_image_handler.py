import base64
import io
import json
import hashlib
import os
import requests
import fitz
from PIL import Image
from pathlib import Path
from typing import Optional, Dict, Any
from concurrent.futures import Future

class ImageCache:
    # Simple file-based cache for image descriptions.
    
    def __init__(self, cacheDir: str = "./cache/images"):
        # Initialize image cache.
        self.cacheDir = Path(cacheDir)
        self.cacheDir.mkdir(parents=True, exist_ok=True)
        self.cacheFile = self.cacheDir / "descriptions.json"
        self.cache = self._loadCache()
    
    def _loadCache(self) -> Dict[str, str]:
        # Load cache from disk.
        if self.cacheFile.exists():
            try:
                with open(self.cacheFile, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _saveCache(self) -> None:
        # Save cache to disk.
        try:
            with open(self.cacheFile, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"âš ï¸  Could not save cache: {e}")
    
    def getImageHash(self, imageBytes: bytes) -> str:
        # Generate hash for image bytes.
        return hashlib.sha256(imageBytes).hexdigest()
    
    def get(self, imageHash: str) -> Optional[str]:
        # Get cached description for image hash.
        return self.cache.get(imageHash)
    
    def set(self, imageHash: str, description: str) -> None:
        # Cache description for image hash.
        self.cache[imageHash] = description
        self._saveCache()
    
    def has(self, imageHash: str) -> bool:
        # Check if image hash exists in cache.
        return imageHash in self.cache
    
    def stats(self) -> Dict[str, int]:
        # Get cache statistics.
        return {
            'total_cached': len(self.cache),
            'cache_size_kb': self.cacheFile.stat().st_size // 1024 if self.cacheFile.exists() else 0
        }


class ImageHandler:
    # Handles image extraction and description generation using OpenAI Vision API.
    
    def __init__(self, apiKey: str, llmClient,
                 model: str = "gpt-4o",
                 enableCache: bool = True,
                 cacheDir: str = "./cache/images",
                 verbose: bool = True):
        # Initialize the image handler.
        self.apiKey = apiKey
        self.llm = llmClient  # Use LLM's thread pool for parallel execution
        self.model = model
        self.verbose = verbose
        
        # Initialize cache
        self.enableCache = enableCache
        if enableCache:
            self.cache = ImageCache(cacheDir)
            if verbose:
                stats = self.cache.stats()
                print(f"ðŸ“¦ Image cache: {stats['total_cached']} descriptions cached ({stats['cache_size_kb']} KB)")
        else:
            self.cache = None
        
        # Track API usage
        self.apiCallCount = 0
        self.cacheHitCount = 0
    
    def handlePptxAsync(self, shape, context: Optional[str] = None):
        # Process PPTX image asynchronously - returns future.
        try:
            # Extract image bytes
            image = shape.image
            imageBytes = image.blob
            
            # Check cache first
            if self.enableCache:
                imageHash = self.cache.getImageHash(imageBytes)
                cachedDesc = self.cache.get(imageHash)
                if cachedDesc:
                    self.cacheHitCount += 1
                    if self.verbose:
                        print(f"  âœ“ Cached description (hit #{self.cacheHitCount})")
                    # Return a completed future with cached result
                    future = Future()
                    future.set_result(cachedDesc)
                    return future
            
            # Convert to PIL Image
            pilImage = Image.open(io.BytesIO(imageBytes))
            
            # Generate description asynchronously
            self.apiCallCount += 1
            if self.verbose:
                print(f"  â†’ API call #{self.apiCallCount} (generating description)...")
            
            future = self._generateDescriptionAsync(pilImage, context)
            
            # Wrap future to handle caching when result arrives
            if self.enableCache:
                imageHash = self.cache.getImageHash(imageBytes)
                originalFuture = future
                wrappedFuture = Future()
                
                def cacheResult():
                    try:
                        result = originalFuture.result()
                        self.cache.set(imageHash, result)
                        wrappedFuture.set_result(result)
                    except Exception as e:
                        wrappedFuture.set_exception(e)
                
                # Submit caching task to run after description completes
                self.llm.submit(cacheResult)
                return wrappedFuture
            
            return future
            
        except Exception as e:
            if self.verbose:
                print(f"  âŒ Error processing PPTX image: {e}")
            # Return future with error
            future = Future()
            future.set_result(f"<ERROR: {str(e)}>")
            return future
    
    def handlePptx(self, shape, context: Optional[str] = None) -> str:
        # Extract image from PPTX shape and generate description (blocking).
        # Use async version and block on result
        future = self.handlePptxAsync(shape, context)
        return future.result()
    
    def handlePdfAsync(self, page, bbox, scale: float = 1.0, 
                       context: Optional[str] = None):
        # Extract image region from PDF and generate description asynchronously.
        try:
            # Scale bbox back to PDF coordinate space
            xMin, yMin, xMax, yMax = bbox
            scaledRect = fitz.Rect(
                xMin * scale,
                yMin * scale,
                xMax * scale,
                yMax * scale
            )
            
            # Render the region as an image at high resolution
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat, clip=scaledRect)
            
            # Convert to bytes
            imageBytes = pix.tobytes("png")
            
            # Check cache first
            if self.enableCache:
                imageHash = self.cache.getImageHash(imageBytes)
                cachedDesc = self.cache.get(imageHash)
                if cachedDesc:
                    self.cacheHitCount += 1
                    if self.verbose:
                        print(f"  âœ“ Cached description (hit #{self.cacheHitCount})")
                    # Return completed future with cached result
                    future = Future()
                    future.set_result(cachedDesc)
                    return future
            
            # Convert to PIL Image for API
            pilImage = Image.open(io.BytesIO(imageBytes))
            
            # Generate description asynchronously
            self.apiCallCount += 1
            if self.verbose:
                print(f"  â†’ API call #{self.apiCallCount} (generating description)...")
            
            future = self._generateDescriptionAsync(pilImage, context)
            
            # Wrap future to handle caching when result arrives
            if self.enableCache:
                imageHash = self.cache.getImageHash(imageBytes)
                originalFuture = future
                wrappedFuture = Future()
                
                def cacheResult():
                    try:
                        result = originalFuture.result()
                        self.cache.set(imageHash, result)
                        wrappedFuture.set_result(result)
                    except Exception as e:
                        wrappedFuture.set_exception(e)
                
                # Submit caching task to run after description completes
                self.llm.submit(cacheResult)
                return wrappedFuture
            
            return future
            
        except Exception as e:
            if self.verbose:
                print(f"  âŒ Error processing PDF image: {e}")
            # Return future with error
            future = Future()
            future.set_result(f"<ERROR: {str(e)}>")
            return future
    
    def handlePdf(self, page, bbox, scale: float = 1.0, 
                  context: Optional[str] = None) -> str:
        # Extract image region from PDF and generate description (blocking).
        # Use async version and block on result
        future = self.handlePdfAsync(page, bbox, scale, context)
        return future.result()
    
    def _generateDescriptionAsync(self, image: Image.Image, 
                                   context: Optional[str] = None):
        # Generate description asynchronously - returns a future.
        # Submit to LLM's thread pool and return future immediately
        return self.llm.submit(self._callOpenAI, image, context)
    
    def _generateDescription(self, image: Image.Image, 
                            context: Optional[str] = None) -> str:
        # Generate description of image using OpenAI Vision API.
        # Submit to LLM's thread pool for parallel execution
        future = self._generateDescriptionAsync(image, context)
        return future.result()
    
    def _callOpenAI(self, image: Image.Image, context: Optional[str] = None) -> str:
        # Call OpenAI GPT-4 Vision API.
        try:
            # Convert image to base64
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")
            imageBase64 = base64.b64encode(buffered.getvalue()).decode()
            
            # Build prompt
            if context:
                prompt = f"Context: {context}\n\nDescribe this educational diagram/figure in detail. Focus on what it illustrates and any key information shown. Be concise but comprehensive."
            else:
                prompt = "Describe this educational diagram/figure in detail. Focus on what it illustrates and any key information shown. Be concise but comprehensive."
            
            # Call OpenAI API
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.apiKey}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{imageBase64}"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 300
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                return f"<ERROR: API returned {response.status_code}: {response.text[:100]}>"
                
        except Exception as e:
            if self.verbose:
                print(f"  âŒ API error: {e}")
            return f"<ERROR: {str(e)}>"
    
    def getStats(self) -> Dict[str, int]:
        # Get usage statistics.
        stats = {
            'api_calls': self.apiCallCount,
            'cache_hits': self.cacheHitCount,
            'total_requests': self.apiCallCount + self.cacheHitCount
        }
        
        if self.enableCache:
            cacheStats = self.cache.stats()
            stats.update(cacheStats)
        
        return stats
