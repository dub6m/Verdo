import os
import uuid

from app.services.ingester.analyzers.pdf_analyzer import PdfAnalyzer
from app.services.ingester.analyzers.pptx_analyzer import PptxAnalyzer
from app.services.ingester.converter.pptx_to_pdf import PptxToPdfConverter
from app.services.ingester.extractor.content_extractor import ContentExtractor
from app.services.ingester.services.LLM import LLM

# --- Classes ------------------------------------------------------------

class Router:
	def __init__(self, openaiApiKey=None, verbose=True):
		# Initialize LLM for parallel processing
		self.llm = LLM(maxWorkers=30)

		# Initialize analyzers
		self.analyzers = {
			".pptx": PptxAnalyzer(),
			".pdf": PdfAnalyzer()
		}

		# Initialize extractor with LLM client
		self.extractor = ContentExtractor(
			verbose=verbose,
			apiKey=openaiApiKey,
			llmClient=self.llm,
			enableCache=True
		)

		# Initialize PPTX to PDF converter
		self.pptxConverter = PptxToPdfConverter()
		self.verbose = verbose

	def process(self, filePath: str, maxPages: int = None):
		ext = "." + filePath.split(".")[-1].lower()

		if ext not in self.analyzers and ext != ".pptx":
			raise ValueError(f"No analyzer for {ext} files.")

		# Handle PPTX files: convert to PDF first
		if ext == ".pptx":
			if self.verbose:
				print(f"\n📄 Converting PPTX to PDF...")

			try:
				# Convert PPTX to PDF
				pdfPath = self.pptxConverter.convert(filePath)

				if self.verbose:
					print(f"✓ Converted to: {pdfPath}")
					print(f"\n🔍 Processing converted PDF...\n")

				# Process the converted PDF
				try:
					analyzed = self.analyzers[".pdf"].analyze(pdfPath, maxPages=maxPages)
					extracted = self.extractor.extract(pdfPath, analyzed)
					
					# Assign unique IDs to all elements
					for page in extracted:
						for element in page.get('elements', []):
							element['id'] = str(uuid.uuid4())
							
					return extracted
				finally:
					# Clean up temporary PDF
					if os.path.exists(pdfPath):
						try:
							os.remove(pdfPath)
							if self.verbose:
								print(f"\n🗑️  Cleaned up temporary PDF")
						except Exception as e:
							if self.verbose:
								print(f"⚠️  Could not remove temporary PDF: {e}")

			except Exception as e:
				raise RuntimeError(f"PPTX conversion failed: {e}")

		# Handle PDF files directly
		# Step 1: Analyze (detect elements)
		analyzed = self.analyzers[ext].analyze(filePath, maxPages=maxPages)

		# Step 2: Extract (process elements with handlers)
		extracted = self.extractor.extract(filePath, analyzed)

		# Assign unique IDs to all elements
		for page in extracted:
			for element in page.get('elements', []):
				element['id'] = str(uuid.uuid4())

		return extracted

	def getStats(self):
		if hasattr(self.extractor.imageHandler, 'getStats'):
			return self.extractor.imageHandler.getStats()
		return {}