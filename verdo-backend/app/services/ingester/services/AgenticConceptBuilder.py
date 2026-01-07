import concurrent.futures
import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.services.ingester.prompts import (
	CONCEPT_DECISIONS_SYSTEM_PROMPT,
	CONCEPT_DECISIONS_USER_PROMPT,
	UPDATE_SUMMARY_SYSTEM_PROMPT,
	UPDATE_SUMMARY_USER_PROMPT,
)
from app.services.ingester.services.LLM import LLM

# --- Classes ------------------------------------------------------------

@dataclass
class ConceptNode:
	# Represents a single pedagogical concept
	id: str
	title: str
	summary: str
	elements: List[str] = field(default_factory=list)

	# Phase 2 fields (populated during synthesis, null for now)
	definition: Optional[str] = None
	explanation: Optional[str] = None
	formulas: List[str] = field(default_factory=list)
	figures: List[str] = field(default_factory=list)
	examples: List[str] = field(default_factory=list)
	prerequisites: List[str] = field(default_factory=list)
	parent: Optional[str] = None

	# Convert to dictionary for JSON serialization
	def toDict(self) -> dict:
		return asdict(self)


class AgenticConceptBuilder:
	# Builds educational concepts from document elements using batched LLM processing.
	# Processes elements in batches, making sequential decisions about whether each element
	# should start a new concept, join an existing one, or be skipped.

	def __init__(self, llmClient=None, batchSize: int = 10, printLogging: bool = True):
		# Initialize the concept builder
		# Args:
		#   llmClient: LLM client instance (defaults to creating a new one)
		#   batchSize: Number of elements to process per batch
		#   printLogging: Whether to print progress logs

		self.concepts: Dict[str, ConceptNode] = {}  # conceptId -> ConceptNode
		self.allElements: Dict[str, dict] = {}  # elementId -> element dict
		self.batchSize = batchSize
		self.llm = llmClient or LLM(maxWorkers=30)
		self.printLogging = printLogging
		self.processedElements: List[dict] = []  # Track order of processing

	# Main entry point. Process all elements in batches.
	# Args:
	#   elements: List of element dictionaries with id, type, content, etc.
	#   parallel: Whether to use parallel processing (Map-Reduce)
	#   numWorkers: Number of parallel workers
	# Returns:
	#   Dictionary of conceptId -> concept dict
	def processElements(self, elements: List[dict], parallel: bool = True, numWorkers: int = 5) -> Dict[str, dict]:
		# Store all elements for later lookup
		self.allElements = {elem['id']: elem for elem in elements}

		# Sort elements by global_sequence to ensure document order
		sortedElements = sorted(elements, key=lambda x: x.get('global_sequence', 0))

		if parallel and len(sortedElements) > 20:
			return self._processElementsParallel(sortedElements, numWorkers)

		totalBatches = (len(sortedElements) + self.batchSize - 1) // self.batchSize

		if self.printLogging:
			print(f"\n{'='*70}")
			print(f"🧠 AGENTIC CONCEPT BUILDER (Serial)")
			print(f"{'='*70}")
			print(f"Total elements: {len(sortedElements)}")
			print(f"Batch size: {self.batchSize}")
			print(f"Total batches: {totalBatches}")
			print(f"{'='*70}\n")

		# Process in batches
		for i in range(0, len(sortedElements), self.batchSize):
			batch = sortedElements[i:i + self.batchSize]
			batchNum = i // self.batchSize + 1

			if self.printLogging:
				print(f"\n{'='*70}")
				print(f"📦 Batch {batchNum}/{totalBatches} (elements {i+1}-{min(i+self.batchSize, len(sortedElements))})")
				print(f"{'='*70}")

			self._processBatch(batch, i)

		if self.printLogging:
			print(f"\n{'='*70}")
			print(f"✅ PROCESSING COMPLETE")
			print(f"{'='*70}")
			print(f"Total concepts created: {len(self.concepts)}")
			print(f"Total elements processed: {len(self.processedElements)}")
			skipped = len(sortedElements) - len(self.processedElements)
			print(f"Elements skipped: {skipped}")
			print(f"{'='*70}\n")

		# Return as dict format
		return {cid: concept.toDict() for cid, concept in self.concepts.items()}

	# Map-Reduce implementation
	def _processElementsParallel(self, elements: List[dict], numWorkers: int) -> Dict[str, dict]:
		if self.printLogging:
			print(f"\n{'='*70}")
			print(f"🧠 AGENTIC CONCEPT BUILDER (Map-Reduce Parallel)")
			print(f"{'='*70}")
			print(f"Total elements: {len(elements)}")
			print(f"Workers: {numWorkers}")
			print(f"{'='*70}\n")

		# 1. MAP PHASE: Split and Process
		chunkSize = math.ceil(len(elements) / numWorkers)
		chunks = [elements[i:i + chunkSize] for i in range(0, len(elements), chunkSize)]

		allConcepts = []

		with concurrent.futures.ThreadPoolExecutor(max_workers=numWorkers) as executor:
			futures = []
			for i, chunk in enumerate(chunks):
				# Create a new builder for each chunk to avoid state conflicts
				# We share the LLM client to respect rate limits/connection pools
				futures.append(executor.submit(self._processChunkWorker, chunk, i, self.llm))

			for future in concurrent.futures.as_completed(futures):
				try:
					chunkConcepts = future.result()
					allConcepts.extend(chunkConcepts.values())
				except Exception as e:
					print(f"Worker failed: {e}")

		# 2. REDUCE PHASE: Merge
		if self.printLogging:
			print(f"\n🔄 Merging {len(allConcepts)} concepts from parallel chunks...")

		mergedConcepts = self._mergeConcepts(allConcepts)

		# Update self.concepts with merged result
		self.concepts = mergedConcepts

		if self.printLogging:
			print(f"✅ Merge complete. Final concept count: {len(self.concepts)}")

		return {cid: c.toDict() for cid, c in self.concepts.items()}

	# Worker function for parallel processing
	# Returns Dict[str, ConceptNode]
	@staticmethod
	def _processChunkWorker(chunk: List[dict], chunkId: int, llmClient) -> Dict[str, ConceptNode]:
		builder = AgenticConceptBuilder(llmClient=llmClient, printLogging=True)
		# We disable internal parallelism to avoid recursion issues, though it defaults to serial anyway
		builder.processElements(chunk, parallel=False)
		return builder.concepts

	# Intelligent merge of concepts using LLM
	# concepts: List of ConceptNode objects (or dicts if coming from raw)
	def _mergeConcepts(self, concepts: List[dict]) -> Dict[str, ConceptNode]:
		# 1. Deduplicate by exact title match first
		tempMap = {}
		for c in concepts:
			# Handle both dict and object input
			cObj = c if isinstance(c, ConceptNode) else ConceptNode(**c)

			if cObj.title in tempMap:
				# Merge elements
				existing = tempMap[cObj.title]
				existing.elements.extend(cObj.elements)
				# Append summary if different
				if len(cObj.summary) > len(existing.summary):
					existing.summary = cObj.summary
			else:
				tempMap[cObj.title] = cObj

		# 2. Semantic Merge via LLM
		# If we have too many concepts, we might want to ask LLM to find synonyms
		# For now, we'll stick to the exact title match + simple list return
		# because the LLM in the map phase is instructed to be consistent.
		# A full semantic merge would require another batch LLM call.

		# Let's do a quick semantic check if list is small enough
		finalConcepts = {}
		for c in tempMap.values():
			finalConcepts[c.id] = c

		return finalConcepts

	# Process a batch of elements
	# Args:
	#   batch: List of element dicts to process
	#   batchStartIdx: Starting index in the full element list
	def _processBatch(self, batch: List[dict], batchStartIdx: int):
		# Get decisions from LLM for this batch
		decisions = self._getBatchDecisions(batch)

		# Apply decisions in order
		for decision in decisions.get('decisions', []):
			elementId = decision.get('element_id')
			decisionType = decision.get('decision')
			conceptId = decision.get('concept_id')
			reasoning = decision.get('reasoning', '')

			if not elementId or elementId not in self.allElements:
				if self.printLogging:
					print(f"  ⚠️  Unknown element: {elementId}")
				continue

			element = self.allElements[elementId]

			if decisionType == 'skip':
				if self.printLogging:
					print(f"  ⏭️  Skipped [{elementId}] {element['type']}: {reasoning}")

			elif decisionType == 'create_new':
				title = decision.get('title', 'Untitled Concept')
				summary = decision.get('summary', '')

				if not conceptId:
					conceptId = self._generateConceptId()

				self._createConcept(conceptId, title, summary, elementId, element)
				self.processedElements.append(element)

			elif decisionType == 'add_to_existing':
				if conceptId and conceptId in self.concepts:
					self._addToConcept(conceptId, elementId, element)
					self.processedElements.append(element)
				else:
					if self.printLogging:
						print(f"  ⚠️  Cannot add to unknown concept: {conceptId}")

	# Call LLM to get decisions for all elements in the batch
	# Args:
	#   batch: List of elements to process
	# Returns:
	#   Dict with 'decisions' key containing list of decision dicts
	def _getBatchDecisions(self, batch: List[dict]) -> dict:
		# Get concept outline (all concepts with title and summary only)
		conceptOutline = self._getConceptOutline()

		# Get context from previous batch
		contextSection = "PREVIOUS CONTEXT:\n"
		if self.processedElements:
			for elem in self.processedElements[-3:]:  # Last 3 processed elements
				contentPreview = elem['content'][:100] + "..." if len(elem['content']) > 100 else elem['content']
				contextSection += f"- [{elem['id']}, {elem['type']}] {contentPreview}\n"
		else:
			contextSection += "(This is the first batch)\n"

		# Format elements list
		elementsList = ""
		for i, elem in enumerate(batch, 1):
			contentPreview = elem['content'][:150] + "..." if len(elem['content']) > 150 else elem['content']
			elementsList += f"{i}. [{elem['id']}, {elem['type']}] {contentPreview}\n\n"

		userPrompt = CONCEPT_DECISIONS_USER_PROMPT.format(
			concept_outline=conceptOutline,
			context_section=contextSection,
			elements_list=elementsList
		)

		# Call LLM
		try:
			response = self.llm.chat(
				messages=[
					{"role": "system", "content": CONCEPT_DECISIONS_SYSTEM_PROMPT},
					{"role": "user", "content": userPrompt}
				],
				model="glm-4-flash-250414",
				response_format={"type": "json_object"}
			)

			# Parse JSON response
			decisions = json.loads(response)
			return decisions

		except json.JSONDecodeError as e:
			if self.printLogging:
				print(f"  ⚠️  JSON parse error: {e}")
				print(f"  Response: {response[:200]}...")
			return {"decisions": []}
		except Exception as e:
			if self.printLogging:
				print(f"  ⚠️  Error getting batch decisions: {e}")
			return {"decisions": []}

	# Format current concepts for the LLM to see
	# Shows all concepts but only title and summary fields
	# Returns:
	#   Formatted string of current concepts
	def _getConceptOutline(self) -> str:
		if not self.concepts:
			return "=== CURRENT CONCEPTS ===\nNo concepts created yet.\n"

		outline = f"=== CURRENT CONCEPTS (Total: {len(self.concepts)}) ===\n\n"

		for concept in self.concepts.values():
			lastElemContent = concept.elements[-1] if concept.elements else ''
			lastElemPreview = lastElemContent[:80] + "..." if len(lastElemContent) > 80 else lastElemContent

			outline += f"""---
Concept ID: {concept.id}
Title: "{concept.title}"
Summary: {concept.summary}
Elements: {len(concept.elements)} elements
Last element content: {lastElemPreview}
---

"""
		return outline

	# Generate a unique concept ID using UUID
	def _generateConceptId(self) -> str:
		return f"c_{uuid.uuid4().hex[:8]}"

	# Create a new concept with the first element
	# Args:
	#   conceptId: Unique identifier for the concept
	#   title: Concept title
	#   summary: Brief description of the concept
	#   elementId: ID of the first element
	#   element: The element dict
	def _createConcept(self, conceptId: str, title: str, summary: str,
					   elementId: str, element: dict):
		self.concepts[conceptId] = ConceptNode(
			id=conceptId,
			title=title,
			summary=summary,
			elements=[element.get('content', '')]
		)

		if self.printLogging:
			elemPreview = element['content'][:60] + "..." if len(element['content']) > 60 else element['content']
			print(f"  ✨ Created concept {conceptId}: \"{title}\"")
			print(f"     First element: [{elementId}, {element['type']}] {elemPreview}")

	# Add element to existing concept and UPDATE THE SUMMARY
	# Args:
	#   conceptId: ID of concept to add to
	#   elementId: ID of element to add
	#   element: The element dict
	def _addToConcept(self, conceptId: str, elementId: str, element: dict):
		concept = self.concepts[conceptId]
		concept.elements.append(element.get('content', ''))

		# Update summary
		newSummary = self._updateConceptSummary(conceptId, element)
		if newSummary:
			concept.summary = newSummary

		if self.printLogging:
			elemPreview = element['content'][:60] + "..." if len(element['content']) > 60 else element['content']
			print(f"  ➕ Added to {conceptId} (\"{concept.title}\")")
			print(f"     Element: [{elementId}, {element['type']}] {elemPreview}")
			print(f"     Total elements: {len(concept.elements)}")

	# Update concept summary after adding a new element
	# Args:
	#   conceptId: ID of concept being updated
	#   newElement: The newly added element dict
	# Returns:
	#   Updated summary string, or None if update failed
	def _updateConceptSummary(self, conceptId: str, newElement: dict) -> Optional[str]:
		concept = self.concepts[conceptId]

		userPrompt = UPDATE_SUMMARY_USER_PROMPT.format(
			title=concept.title,
			summary=concept.summary,
			element_id=newElement.get('id', 'N/A'),
			element_type=newElement.get('type', 'N/A'),
			content=newElement.get('content', '')[:300]
		)

		try:
			response = self.llm.chat(
				messages=[
					{"role": "system", "content": UPDATE_SUMMARY_SYSTEM_PROMPT},
					{"role": "user", "content": userPrompt}
				],
				model="glm-4-flash-250414"
			)

			return response.strip()

		except Exception as e:
			if self.printLogging:
				print(f"    ⚠️  Could not update summary: {e}")
			return None

	# Get concepts as a list of dictionaries
	def getConceptsList(self) -> List[dict]:
		return [concept.toDict() for concept in self.concepts.values()]

	# Get a specific concept by ID
	def getConceptById(self, conceptId: str) -> Optional[dict]:
		if conceptId in self.concepts:
			return self.concepts[conceptId].toDict()
		return None

	# Get statistics about the concept building process
	def getStats(self) -> dict:
		if not self.concepts:
			return {
				"totalConcepts": 0,
				"totalElementsProcessed": 0,
				"avgElementsPerConcept": 0,
				"minElementsPerConcept": 0,
				"maxElementsPerConcept": 0
			}

		elementCounts = [len(c.elements) for c in self.concepts.values()]

		return {
			"totalConcepts": len(self.concepts),
			"totalElementsProcessed": len(self.processedElements),
			"avgElementsPerConcept": sum(elementCounts) / len(elementCounts),
			"minElementsPerConcept": min(elementCounts),
			"maxElementsPerConcept": max(elementCounts)
		}
