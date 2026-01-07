# --- Classes ------------------------------------------------------------

class DefaultHandler:
	# Fallback handler for unimplemented element types

	def handle(self, *args, **kwargs):
		# Generic handle method
		return "<UNHANDLED_ELEMENT>"

	def handlePptx(self, shape, **kwargs):
		# PPTX-specific fallback
		return "<UNHANDLED_ELEMENT>"

	def handlePdf(self, page, bbox, scale):
		# PDF-specific fallback
		return "<UNHANDLED_ELEMENT>"
