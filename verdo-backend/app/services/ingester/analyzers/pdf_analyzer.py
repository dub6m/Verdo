import os

import fitz

from app.services.ingester.core.model_loader import ModelLoader
from app.services.ingester.core.nms_processor import NmsProcessor

# --- Classes ------------------------------------------------------------

class PdfAnalyzer:
	def __init__(self, confThreshold=0.4, iouThreshold=0.7, dpi=250):
		self.model = ModelLoader().load()
		self.nms = NmsProcessor()
		self.confThreshold = confThreshold
		self.iouThreshold = iouThreshold
		self.dpi = dpi

	def analyze(self, filePath: str, maxPages: int = None):
		doc = fitz.open(filePath)
		results = []

		totalPages = len(doc)
		if maxPages:
			totalPages = min(totalPages, maxPages)

		for pageNum in range(totalPages):
			page = doc[pageNum]
			imgPath = f"temp_page_{pageNum}.png"
			page.get_pixmap(dpi=self.dpi).save(imgPath)
			detections = []

			preds = self.model.predict(imgPath, imgsz=1024, conf=self.confThreshold)
			if hasattr(preds[0], 'boxes'):
				boxes = preds[0].boxes
				for i in range(len(boxes)):
					classId = int(boxes.cls[i])
					conf = float(boxes.conf[i])
					bbox = boxes.xyxy[i].tolist()
					cls = preds[0].names[classId]
					if cls == 'abandon':
						continue
					detections.append({'class_name': cls, 'bbox': bbox, 'conf': conf})

			detections = self.nms.removeDuplicates(detections, iouThreshold=self.iouThreshold)
			results.append({'page_number': pageNum + 1, 'detections': detections})
			os.remove(imgPath)

		doc.close()
		return results
