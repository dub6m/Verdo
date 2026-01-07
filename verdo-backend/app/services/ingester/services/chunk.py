from typing import List


class Chunk:
	def __init__(self, chunk_id: str, data: List[str]):
		self.id = chunk_id
		self.data = data
