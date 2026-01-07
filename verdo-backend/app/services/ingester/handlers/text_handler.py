import fitz  # PyMuPDF

# --- Classes ------------------------------------------------------------

class TextHandler:
	# Handles text extraction for PPTX and PDF.

	def handlePptx(self, shape, **kwargs):
		# Extract text from PPTX shape.
		if not shape.has_text_frame:
			return ""
		return shape.text.strip()

	def handlePdf(self, page, bbox, scale=1.0):
		# Extract text from PDF within bounding box.
		# Scale bbox to PDF coordinate space
		xMin, yMin, xMax, yMax = bbox
		scaledRect = fitz.Rect(
			xMin * scale,
			yMin * scale,
			xMax * scale,
			yMax * scale
		)

		# Extract text within bbox
		text = page.get_text("text", clip=scaledRect)

		# Clean up whitespace
		return " ".join(text.split()).strip()
