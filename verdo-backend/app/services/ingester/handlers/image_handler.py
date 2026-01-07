import base64
import hashlib
import io
import json
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Dict, Optional

import fitz
from PIL import Image

from app.services.ingester.prompts import (
	CATEGORIZE_IMAGE_PROMPT,
	DESCRIBE_CHART_PROMPT,
	DESCRIBE_DIAGRAM_PROMPT,
	DESCRIBE_FLOWCHART_PROMPT,
	DESCRIBE_PHOTO_PROMPT,
	DESCRIBE_TEXT_IMAGE_PROMPT,
)

# --- Classes ------------------------------------------------------------

class ImageCache:
	# Simple file cache for image descriptions

	def __init__(self, cacheDir: str = "./cache/images"):
		self.cacheDir = Path(cacheDir)
		self.cacheDir.mkdir(parents=True, exist_ok=True)
		self.cacheFile = self.cacheDir / "descriptions.json"
		self.cache = self._loadCache()

	def _loadCache(self) -> Dict[str, str]:
		if self.cacheFile.exists():
			try:
				with open(self.cacheFile, 'r', encoding='utf-8') as f:
					return json.load(f)
			except Exception:
				return {}
		return {}

	def _saveCache(self) -> None:
		try:
			with open(self.cacheFile, 'w', encoding='utf-8') as f:
				json.dump(self.cache, f, indent=2, ensure_ascii=False)
		except Exception:
			pass

	def getImageHash(self, imageBytes: bytes) -> str:
		return hashlib.sha256(imageBytes).hexdigest()

	def get(self, imageHash: str) -> Optional[str]:
		return self.cache.get(imageHash)

	def set(self, imageHash: str, description: str) -> None:
		self.cache[imageHash] = description
		self._saveCache()

	def stats(self) -> Dict[str, int]:
		return {
			'total_cached': len(self.cache),
			'cache_size_kb': self.cacheFile.stat().st_size // 1024 if self.cacheFile.exists() else 0
		}


class ImageHandler:
	# Handles image extraction, categorization, and description using central LLM

	def __init__(self, apiKey: str, llmClient,
				 enableCache: bool = True,
				 cacheDir: str = "./cache/images",
				 verbose: bool = True,
				 tableHandler: Any = None,
				 formulaHandler: Any = None):
		self.apiKey = apiKey
		self.llm = llmClient
		# Use a capable vision model for categorization and description
		self.model = "gpt-4o" 
		self.verbose = verbose
		self.tableHandler = tableHandler
		self.formulaHandler = formulaHandler

		self.enableCache = enableCache
		self.cache = ImageCache(cacheDir) if enableCache else None

		self.apiCallCount = 0
		self.cacheHitCount = 0

		if self.cache and self.verbose:
			stats = self.cache.stats()
			print(f"📦 Image cache: {stats['total_cached']} descriptions cached ({stats['cache_size_kb']} KB)")

	def handlePptxAsync(self, shape, context: Optional[str] = None):
		# Describe PPTX image asynchronously
		try:
			image = shape.image
			imageBytes = image.blob
			return self._processImageAsync(imageBytes, context)
		except Exception as e:
			if self.verbose:
				print(f"  ERR Error processing PPTX image: {e}")
			fut = Future()
			fut.set_result(f"<ERROR: {str(e)}>")
			return fut

	def handlePptx(self, shape, context: Optional[str] = None) -> str:
		fut = self.handlePptxAsync(shape, context)
		return fut.result()

	def handlePdfAsync(self, page, bbox, scale: float = 1.0,
					   context: Optional[str] = None):
		# Describe PDF region asynchronously
		try:
			xMin, yMin, xMax, yMax = bbox
			rect = fitz.Rect(xMin * scale, yMin * scale, xMax * scale, yMax * scale)
			pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=rect)
			imageBytes = pix.tobytes("png")
			return self._processImageAsync(imageBytes, context)
		except Exception as e:
			if self.verbose:
				print(f"  ERR Error processing PDF image: {e}")
			fut = Future()
			fut.set_result(f"<ERROR: {str(e)}>")
			return fut

	def handlePdf(self, page, bbox, scale: float = 1.0,
				  context: Optional[str] = None) -> str:
		fut = self.handlePdfAsync(page, bbox, scale, context)
		return fut.result()

	def _processImageAsync(self, imageBytes: bytes, context: Optional[str] = None) -> Future:
		# Central processing logic: Cache -> Categorize -> Dispatch
		if self.enableCache and self.cache:
			imageHash = self.cache.getImageHash(imageBytes)
			cached = self.cache.get(imageHash)
			if cached:
				self.cacheHitCount += 1
				if self.verbose:
					print(f"  ✓ Cached description (hit #{self.cacheHitCount})")
				fut = Future()
				fut.set_result(cached)
				return fut

		# We need to categorize first, then dispatch. This requires chaining futures or
		# coordinating async calls. Since `Future` doesn't easily chain, we wrap in a submit.
		# However, categorization and extraction are separate LLM calls.
		# To keep it non-blocking, we submit the coordination task to the LLM worker pool.

		future = Future()
		
		def coordinator():
			try:
				# 1. Categorize
				category = self._categorize(imageBytes)
				if self.verbose:
					print(f"  🔍 Encoded Image Category: {category}")
				
				# 2. Dispatch
				result = self._dispatch(imageBytes, category, context)
				
				# 3. Cache
				if self.enableCache and self.cache:
					self.cache.set(imageHash, result)
				
				future.set_result(result)
			except Exception as e:
				future.set_exception(e)

		self.llm.submit(coordinator)
		return future

	def _categorize(self, imageBytes: bytes) -> str:
		# Synchronous call (inside coordinator thread)
		self.apiCallCount += 1
		imageBase64 = base64.b64encode(imageBytes).decode()
		messages = [
			{
				"role": "user",
				"content": [
					{"type": "text", "text": CATEGORIZE_IMAGE_PROMPT},
					{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imageBase64}"}}
				]
			}
		]
		
		# Using json_mode if possible, or just strict instructions
		resp = self.llm.chat(
			messages=messages,
			model=self.model,
			response_format={"type": "json_object"}
		)
		
		try:
			data = json.loads(resp)
			return data.get("type", "Photo")
		except Exception:
			return "Photo"

	def _dispatch(self, imageBytes: bytes, category: str, context: Optional[str]) -> str:
		# Dispatch based on category
		cat = category.lower()
		
		if "table" in cat:
			if self.tableHandler:
				return json.dumps(self.tableHandler.handleImage(imageBytes))
			else:
				# Fallback if no handler
				return self._generateDescription(imageBytes, DESCRIBE_TEXT_IMAGE_PROMPT)

		if "math" in cat or "formula" in cat:
			if self.formulaHandler:
				return json.dumps(self.formulaHandler.handleImage(imageBytes))
			else:
				return self._generateDescription(imageBytes, DESCRIBE_TEXT_IMAGE_PROMPT)

		# Specific handlers
		if "chart" in cat or "graph" in cat:
			return self._generateDescription(imageBytes, DESCRIBE_CHART_PROMPT)
		
		if "diagram" in cat or "technical" in cat:
			return self._generateDescription(imageBytes, DESCRIBE_DIAGRAM_PROMPT)
			
		if "flowchart" in cat:
			return self._generateDescription(imageBytes, DESCRIBE_FLOWCHART_PROMPT)
			
		if "text" in cat:
			return self._generateDescription(imageBytes, DESCRIBE_TEXT_IMAGE_PROMPT)
			
		# Default / Photo
		return self._generateDescription(imageBytes, DESCRIBE_PHOTO_PROMPT)

	def _generateDescription(self, imageBytes: bytes, prompt: str) -> str:
		self.apiCallCount += 1
		imageBase64 = base64.b64encode(imageBytes).decode()
		messages = [
			{
				"role": "user",
				"content": [
					{"type": "text", "text": prompt},
					{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imageBase64}"}}
				]
			}
		]
		# Using json_object response format for all consistent extraction
		return self.llm.chat(
			messages=messages,
			model=self.model,
			response_format={"type": "json_object"},
			max_completion_tokens=1000
		)

	def getStats(self) -> Dict[str, int]:
		stats = {
			'api_calls': self.apiCallCount,
			'cache_hits': self.cacheHitCount,
			'total_requests': self.apiCallCount + self.cacheHitCount
		}
		if self.enableCache and self.cache:
			stats.update(self.cache.stats())
		return stats
