import base64
import io
import json
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image

from app.services.ingester.prompts import DESCRIBE_TABLE_PROMPT

# --- Classes ------------------------------------------------------------

class TableHandler:
	# Handles table extraction for PPTX and PDF.
	# Now supports handling raw image bytes directly via handleImage.

	def __init__(self, apiKey: Optional[str] = None, llmClient=None,
				 enableGptFallback: bool = True, verbose: bool = True):
		# Initialize table handler.
		self.apiKey = apiKey
		self.llm = llmClient
		self.enableGptFallback = enableGptFallback and apiKey and llmClient
		self.verbose = verbose

		# Track usage
		self.pdfplumberSuccess = 0
		self.gptFallbackUsed = 0

	def handleImage(self, imageBytes: bytes) -> Dict[str, Any]:
		# Extract table from raw image bytes (delegated from ImageHandler)
		try:
			result = self._extractWithGptBytes(imageBytes)
			return result
		except Exception as e:
			if self.verbose:
				print(f"  ❌ Error extracting table from image: {e}")
			return {'error': str(e), 'source': 'image_handler_delegation'}

	def handlePptx(self, shape, **kwargs) -> Dict[str, Any]:
		# Extract table from PPTX shape.
		try:
			table = shape.table

			# Extract table dimensions
			rows = len(table.rows)
			cols = len(table.columns)

			# Extract cell data
			data = []
			for row in table.rows:
				rowData = []
				for cell in row.cells:
					cellText = cell.text.strip()
					rowData.append(cellText)
				data.append(rowData)

			if self.verbose:
				print(f"  ✓ Extracted PPTX table ({rows}x{cols})")

			return {
				'type': 'table', # standardized type
				'rows': rows,
				'columns': cols,
				'data': data,
				'markdown': self._toMarkdown(data),
				'source': 'pptx'
			}

		except Exception as e:
			if self.verbose:
				print(f"  ❌ Error extracting PPTX table: {e}")
			return {
				'error': str(e),
				'source': 'pptx'
			}

	def handlePdf(self, page, bbox, scale: float = 1.0) -> Dict[str, Any]:
		# Extract table from PDF within bounding box.
		try:
			# Scale bbox to PDF coordinate space
			x0, y0, x1, y1 = bbox
			scaledBbox = (
				x0 * scale,
				y0 * scale,
				x1 * scale,
				y1 * scale
			)

			# Try pdfplumber first
			result = self._extractWithPdfplumber(page, scaledBbox)

			if result and result.get('data'):
				self.pdfplumberSuccess += 1
				if self.verbose:
					rows = result.get('rows', 0)
					cols = result.get('columns', 0)
					print(f"  ✓ Extracted PDF table with pdfplumber ({rows}x{cols})")
				return result

			# Fallback to GPT-4o if enabled
			if self.enableGptFallback:
				if self.verbose:
					print(f"  → pdfplumber failed, trying GPT-4o fallback...")
				result = self._extractWithGpt(page, scaledBbox)
				self.gptFallbackUsed += 1
				return result
			else:
				if self.verbose:
					print(f"  ⚠️  pdfplumber failed, no fallback enabled")
				return {
					'error': 'pdfplumber extraction failed',
					'source': 'pdfplumber'
				}

		except Exception as e:
			if self.verbose:
				print(f"  ❌ Error extracting PDF table: {e}")
			return {
				'error': str(e),
				'source': 'pdf'
			}

	def _extractWithPdfplumber(self, page, bbox) -> Optional[Dict[str, Any]]:
		# Extract table using pdfplumber.
		try:
			# Get the PDF file path from the page
			pdfPath = page.parent.name

			# Open with pdfplumber
			with pdfplumber.open(pdfPath) as pdf:
				pdfPage = pdf.pages[page.number]

				# Crop to bbox region
				x0, y0, x1, y1 = bbox
				cropped = pdfPage.crop((x0, y0, x1, y1))

				# Extract tables from cropped region
				tables = cropped.extract_tables()

				if not tables or len(tables) == 0:
					return None

				# Take the first/largest table
				tableData = tables[0]

				if not tableData or len(tableData) == 0:
					return None

				# Build normalized result
				return self._buildResult(tableData, None, 'pdfplumber')

		except Exception as e:
			if self.verbose:
				print(f"  ⚠️  pdfplumber error: {e}")
			return None

	def _extractWithGpt(self, page, bbox) -> Dict[str, Any]:
		# Extract table using GPT-4o Vision as fallback.
		try:
			# Render the table region as image
			rect = fitz.Rect(bbox)
			mat = fitz.Matrix(2.0, 2.0)  # 2x zoom
			pix = page.get_pixmap(matrix=mat, clip=rect)
			imageBytes = pix.tobytes("png")
			
			return self._extractWithGptBytes(imageBytes, source='gpt-4o-pdf-fallback')

		except Exception as e:
			if self.verbose:
				print(f"  ❌ GPT-4o fallback error: {e}")
			return {
				'error': str(e),
				'source': 'gpt-4o'
			}

	def _extractWithGptBytes(self, imageBytes: bytes, source: str = 'gpt-4o-image') -> Dict[str, Any]:
		# Helper to call LLM with image bytes
		try:
			imageBase64 = base64.b64encode(imageBytes).decode()
			prompt = DESCRIBE_TABLE_PROMPT

			messages = [
				{
					"role": "user",
					"content": [
						{"type": "text", "text": prompt},
						{
							"type": "image_url",
							"image_url": {
								"url": f"data:image/png;base64,{imageBase64}"
							},
						},
					],
				}
			]

			# Call centralized LLM service
			# We use 'chat' here synchronously because this is typically called contextually,
			# but if called from ImageHandler's async flow, ImageHandler wraps it.
			response = self.llm.chat(
				messages=messages,
				model="gpt-4o",
				max_completion_tokens=1000,
				response_format={"type": "json_object"}
			)

			try:
				parsedData = json.loads(response)
			except Exception:
				parsedData = self._parseGptJson(response)
				
			# If we got the expected struct from prompt
			if isinstance(parsedData, dict) and 'rows' in parsedData:
				# Use the data directly if it matches our standard format
				# But we want to normalize it
				data = parsedData.get('rows', []) # user prompt returns {rows: [...]} as data?
				# Wait, prompt says: { "rows": [[val, val], ...], "headers": [...] }
				# Standard format expects data to be list of lists including headers usually?
				
				# Let's align with existing _buildResult
				# Existing _buildResult takes list of lists
				
				raw_rows = parsedData.get('rows', [])
				headers = parsedData.get('headers', [])
				
				# If headers are separate, prepend them
				if headers and raw_rows:
					if raw_rows[0] != headers:
						raw_rows.insert(0, headers)
				elif headers and not raw_rows:
					raw_rows = [headers]
					
				result = self._buildResult(raw_rows, None, source)
				# Add extra fields from new prompt
				result['title'] = parsedData.get('title')
				result['footnotes'] = parsedData.get('footnotes')
				result['type'] = 'table_image'
				return result

			return {
				'description': response,
				'source': source,
				'structured': False
			}

		except Exception as e:
			return {'error': str(e), 'source': source}

	def _callGptVision(self, imageBase64: str, prompt: str) -> str:
		return f"<ERROR: Deprecated method>"

	def _parseGptJson(self, text: str):
		return None # Simplified for now as we enforce json_object

	def _extractBalanced(self, s: str, openCh: str, closeCh: str) -> Optional[str]:
		start = s.find(openCh)
		if start == -1: return None
		depth = 0
		for i in range(start, len(s)):
			ch = s[i]
			if ch == openCh: depth += 1
			elif ch == closeCh: depth -= 1
			if depth == 0: return s[start:i + 1]
		return None

	def _normalizeData(self, data: List[List[str]]) -> List[List[str]]:
		# Trim and pad rows to equal length
		if not data:
			return []
		maxCols = 0
		cleaned = []
		for row in data:
			vals = []
			if isinstance(row, list):
				for cell in row:
					vals.append(cell.strip() if isinstance(cell, str) else "")
			cleaned.append(vals)
			if len(vals) > maxCols:
				maxCols = len(vals)
		if maxCols == 0:
			return cleaned
		normalized = []
		for row in cleaned:
			padded = row + [""] * (maxCols - len(row))
			normalized.append(padded)
		return normalized

	def _buildResult(self, data: List[List[str]], bbox, source: str) -> Dict[str, Any]:
		# Build uniform result for any extractor
		normalized = self._normalizeData(data)
		rows = len(normalized)
		cols = max((len(r) for r in normalized), default=0)
		return {
			'type': 'table',
			'rows': rows,
			'columns': cols,
			'data': normalized,
			'markdown': self._toMarkdown(normalized),
			'source': source
		}

	def _toMarkdown(self, data: List[List[str]]) -> str:
		if not data or len(data) == 0:
			return ""
		lines = []
		headerRow = data[0]
		lines.append("| " + " | ".join(headerRow) + " |")
		lines.append("| " + " | ".join(["---"] * len(headerRow)) + " |")
		for row in data[1:]:
			paddedRow = row + [""] * (len(headerRow) - len(row))
			lines.append("| " + " | ".join(paddedRow) + " |")
		return "\n".join(lines)

	def getStats(self) -> Dict[str, int]:
		return {
			'pdfplumber_success': self.pdfplumberSuccess,
			'gpt_fallback_used': self.gptFallbackUsed,
			'total_pdf_tables': self.pdfplumberSuccess + self.gptFallbackUsed
		}
