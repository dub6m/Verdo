# --- Classes ------------------------------------------------------------

class NmsProcessor:
	# Calculate IoU between two boxes
	@staticmethod
	def computeIou(b1, b2):
		x1Min, y1Min, x1Max, y1Max = b1
		x2Min, y2Min, x2Max, y2Max = b2
		interXMin, interYMin = max(x1Min, x2Min), max(y1Min, y2Min)
		interXMax, interYMax = min(x1Max, x2Max), min(y1Max, y2Max)
		if interXMax < interXMin or interYMax < interYMin:
			return 0.0
		interArea = (interXMax - interXMin) * (interYMax - interYMin)
		box1Area = (x1Max - x1Min) * (y1Max - y1Min)
		box2Area = (x2Max - x2Min) * (y2Max - y2Min)
		return interArea / (box1Area + box2Area - interArea)

	# Remove overlapping detections (same class + IoU > threshold)
	@staticmethod
	def removeDuplicates(detections, iouThreshold=0.7):
		if not detections: return []
		detections.sort(key=lambda x: x['conf'], reverse=True)
		keep = []
		while detections:
			best = detections.pop(0)
			keep.append(best)
			detections = [
				d for d in detections
				if d['class_name'] != best['class_name'] or
				NmsProcessor.computeIou(d['bbox'], best['bbox']) <= iouThreshold
			]
		return keep
