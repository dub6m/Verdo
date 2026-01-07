import os

from doclayout_yolo import YOLOv10
from huggingface_hub import snapshot_download

# --- Classes ------------------------------------------------------------

class ModelLoader:
	def __init__(self, repoId="juliozhao/DocLayout-YOLO-DocStructBench", localDir="./models/DocLayout-YOLO-DocStructBench"):
		self.repoId = repoId
		self.localDir = localDir

	def load(self):
		modelDir = snapshot_download(repo_id=self.repoId, local_dir=self.localDir)
		weights = next((os.path.join(modelDir, f) for f in os.listdir(modelDir) if f.endswith(".pt")), None)
		if not weights:
			raise FileNotFoundError("No .pt weights found in model directory.")
		return YOLOv10(weights)
