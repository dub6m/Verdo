import json
import os
import sys
from pathlib import Path

# Resolve project root
PROJECT_ROOT = Path(__file__).resolve()
for _ in range(8):
	if (PROJECT_ROOT / 'app').exists():
		break
	PROJECT_ROOT = PROJECT_ROOT.parent

INGESTER_PATH = PROJECT_ROOT / 'app' / 'services'
sys.path.insert(0, str(INGESTER_PATH))
sys.path.insert(0, str(PROJECT_ROOT))

try:
	from dotenv import load_dotenv
	load_dotenv()
except Exception:
	pass

from app.services.ingester.services.AgenticConceptBuilder import AgenticConceptBuilder

def main():
	# Input/Output paths
	inputFile = PROJECT_ROOT / "out" / "Module7.json"
	outputFile = PROJECT_ROOT / "out" / "Module7_concepts.json"

	if not inputFile.exists():
		print(f"Error: Input file not found: {inputFile}")
		return

	print(f"Reading from: {inputFile}")
	with open(inputFile, "r", encoding="utf-8") as f:
		data = json.load(f)

	# Flatten elements from pages
	allElements = []
	for page in data:
		pageNum = page.get("page_number")
		for elem in page.get("elements", []):
			# Add page number to element for reference if needed
			elem["page_number"] = pageNum
			# Ensure element has an ID (if not present, generate one or use index)
			if "id" not in elem:
				elem["id"] = f"elem_{len(allElements)}"

			# Add global sequence for sorting
			elem["global_sequence"] = len(allElements)
			allElements.append(elem)

	print(f"Total elements to process: {len(allElements)}")

	# Initialize Builder
	builder = AgenticConceptBuilder(printLogging=True)

	# Process
	concepts = builder.processElements(allElements)

	# Save output
	print(f"Writing concepts to: {outputFile}")
	with open(outputFile, "w", encoding="utf-8") as f:
		json.dump(concepts, f, ensure_ascii=False, indent=2)

	print("Done!")

if __name__ == "__main__":
	main()
