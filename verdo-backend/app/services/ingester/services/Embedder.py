from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

# --- Classes ------------------------------------------------------------

class Embedder:
	def __init__(self, modelName: str = "all-MiniLM-L6-v2"):
		# Load a lightweight, fast model
		self.model = SentenceTransformer(modelName)

	# Generate embedding for a single string
	def getEmbedding(self, text: str) -> List[float]:
		if not text:
			return []

		# Encode returns a numpy array
		embedding = self.model.encode(text)
		return embedding.tolist()

	# Compute cosine similarity between two vectors
	@staticmethod
	def cosineSimilarity(vec1: List[float], vec2: List[float]) -> float:
		if not vec1 or not vec2:
			return 0.0

		a = np.array(vec1)
		b = np.array(vec2)

		normA = np.linalg.norm(a)
		normB = np.linalg.norm(b)

		if normA == 0 or normB == 0:
			return 0.0

		return float(np.dot(a, b) / (normA * normB))
