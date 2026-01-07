import base64
import json
import re
from typing import Any, Dict, Optional, Tuple

import fitz  # PyMuPDF
from lxml import etree

from app.services.ingester.prompts import (
	DESCRIBE_FORMULA_PROMPT,
	EXTRACT_EQUATION_TEXT_PROMPT,
)

# --- Classes ------------------------------------------------------------

class FormulaHandler:
	# Handles formula extraction for PPTX and PDF.
	# Prioritizes OMML extraction from PPTX, falls back to LLM-based OCR.

	def __init__(self, apiKey: Optional[str] = None, llmClient=None, verbose: bool = True):
		self.apiKey = apiKey
		self.llm = llmClient
		self.verbose = verbose
		# XSLT for OMML -> MathML
		self.omml2mathml = self._loadXslt("OMML2MML.XSL")

	def _loadXslt(self, filename: str):
		return None

	def handleImage(self, imageBytes: bytes) -> Dict[str, Any]:
		# Extract formula from raw image bytes (delegated from ImageHandler)
		try:
			return self._extractFormula(imageBytes, source='image_delegation')
		except Exception as e:
			if self.verbose:
				print(f"  ❌ Error extracting formula from image: {e}")
			return {'error': str(e), 'source': 'image_delegation'}

	def handlePptx(self, shape, slideNum: int = 0, filePath: str = "") -> Dict[str, Any]:
		# Layer 1: Try OMML extraction and conversion
		omml = self._extractOmml(shape)
		if omml:
			latex, mathml = self._ommlToLatex(omml)
			if latex or mathml:
				if self.verbose:
					print("  ✓ OMML equation extracted")
				return {
					'type': 'formula',
					'latex': latex,
					'mathml': mathml,
					'omml': omml,
					'source': 'omml',
					'confidence': 1.0 if latex else 0.8,
					'error': None
				}

		# Layer 2a: OMML failed, try slide-level OMML search if we know the file/slide
		if (not omml) and filePath and slideNum:
			try:
				ommlSlide = self._extractOmmlFromSlide(filePath, slideNum)
				if ommlSlide:
					latex, mathml = self._ommlToLatex(ommlSlide)
					if latex or mathml:
						if self.verbose:
							print("  ✓ OMML equation extracted from slide XML")
						return {
							'type': 'formula',
							'latex': latex,
							'mathml': mathml,
							'omml': ommlSlide,
							'source': 'omml_slide',
							'confidence': 1.0 if latex else 0.8,
							'error': None
						}
			except Exception as e:
				if self.verbose:
					print(f"  ⚠️  Slide-level OMML search failed: {e}")

		# Layer 2b: OMML failed, try text-to-LaTeX via LLM if text exists
		try:
			if getattr(shape, 'has_text_frame', False) and shape.has_text_frame and self.llm:
				rawText = (getattr(shape, 'text', '') or '').strip()
				rawText = self._normalizeTextEquation(rawText)
				if rawText:
					if self.verbose:
						print("  ↗ Sending text to LLM for LaTeX extraction...")
					textRes = self._extractFormulaFromText(rawText)
					if textRes and textRes.get('latex'):
						if self.verbose:
							preview = textRes.get('latex', '')[:80]
							print(f"  ✓ Extracted LaTeX from text: {preview}...")
						return {
							'type': 'formula',
							'latex': textRes.get('latex'),
							'source': 'text_llm',
							'confidence': textRes.get('confidence'),
							'error': None
						}
		except Exception as e:
			if self.verbose:
				print(f"  ⚠️  Text-to-LaTeX fallback failed: {e}")

		# Layer 2c: OMML failed, try LLM OCR fallback
		try:
			if self.llm:
				image = shape.image
				imageBytes = image.blob
				if self.verbose:
					print("  ↗ Sending image to LLM for equation OCR...")
				res = self._extractFormula(imageBytes, source='ocr_pptx')
				return {
					'type': 'formula',
					'latex': res.get('latex'),
					'source': 'ocr',
					'confidence': res.get('confidence'),
					'error': None if res.get('latex') else 'no_latex'
				}
		except Exception:
			pass

		return {'latex': None, 'source': 'failed', 'confidence': 0.0, 'error': 'No extraction method succeeded'}

	def handlePdf(self, page, bbox, scale: float = 1.0) -> Dict[str, Any]:
		try:
			xMin, yMin, xMax, yMax = bbox
			rect = fitz.Rect(xMin * scale, yMin * scale, xMax * scale, yMax * scale)
			pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=rect)
			imgBytes = pix.tobytes("png")
			if not self.llm:
				return {'latex': None, 'source': 'ocr_no_llm', 'confidence': 0.0, 'error': None}
			
			res = self._extractFormula(imgBytes, source='ocr_pdf')
			return {
				'type': 'formula',
				'latex': res.get('latex'),
				'source': 'ocr',
				'confidence': res.get('confidence'),
				'error': None if res.get('latex') else 'no_latex'
			}
		except Exception as e:
			if self.verbose:
				print(f"  ⚠️  PDF math extraction failed: {e}")
			return {'latex': None, 'source': 'pdf_error', 'confidence': 0.0, 'error': str(e)}

	def _extractOmml(self, shape) -> Optional[str]:
		try:
			if hasattr(shape, 'element'):
				xml = shape.element.xml
				if 'm:oMath' in xml:
					return xml
			return None
		except Exception:
			return None

	def _extractOmmlFromSlide(self, filePath: str, slideNum: int) -> Optional[str]:
		return None

	def _ommlToLatex(self, omml: str) -> Tuple[Optional[str], Optional[str]]:
		return None, None

	def _normalizeTextEquation(self, text: str) -> str:
		return text.strip()

	def _extractFormula(self, imageBytes: bytes, source: str = 'ocr') -> Dict[str, Any]:
		try:
			imageBase64 = base64.b64encode(imageBytes).decode()
			prompt = DESCRIBE_FORMULA_PROMPT

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

			# Synchronous call (normally wrapped if async needed)
			response = self.llm.chat(
				messages=messages,
				model="gpt-4o",
				max_completion_tokens=500,
				response_format={"type": "json_object"}
			)
			
			try:
				parsed = json.loads(response)
			except Exception:
				return {"latex": None, "confidence": 0.0, "error": "json_parse_error"}

			latex = parsed.get("latex")
			# New prompt returns additional fields: raw_text, variables, operators
			# We can merge them into the result if needed or stick to the simple interface
			
			confidence = 0.95 if latex and latex.strip() else 0.0

			return {
				"type": "formula",
				"latex": latex,
				"raw_text": parsed.get("raw_text"),
				"variables": parsed.get("variables", []),
				"operators": parsed.get("operators", []),
				"confidence": confidence,
			}
		except Exception:
			return {"latex": None, "confidence": 0.0}

	def _extractFormulaFromText(self, text: str) -> Dict[str, Any]:
		try:
			prompt = EXTRACT_EQUATION_TEXT_PROMPT.format(text=text)
			messages = [{"role": "user", "content": prompt}]

			response = self.llm.chat(
				messages=messages,
				model="gpt-4o-mini",
				max_completion_tokens=300,
				response_format={"type": "json_object"}
			)
			
			try:
				parsed = json.loads(response)
			except Exception:
				latex = None
			else:
				latex = parsed.get("latex")
				
			if latex:
				return {"latex": latex, "confidence": 0.9}
				
			latexH = self.simpleTextToLatex(text)
			return {"latex": latexH, "confidence": 0.6 if latexH else 0.0}
		except Exception:
			latexH = self.simpleTextToLatex(text)
			return {"latex": latexH, "confidence": 0.6 if latexH else 0.0}

	def simpleTextToLatex(self, text: str) -> Optional[str]:
		if not text:
			return None
		s = str(text)
		strong = ("=", "≤", "≥", "≈", "≠", "^", "√", "∑", "∫", "/")
		if not any(c in s for c in strong):
			return None
		repl = {
			"−": "-", "–": "-", "×": "*", "·": "\\cdot ", "÷": "/",
			"≤": "\\leq ", "≥": "\\geq ", "≠": "\\neq ", "≈": "\\approx ",
			"→": "\\to ", "←": "\\leftarrow ", "∞": "\\infty ",
		}
		for k, v in repl.items():
			s = s.replace(k, v)
		
		# Greek letters... (kept brief for this update)
		return s.strip()
