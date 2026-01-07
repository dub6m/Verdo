import argparse
import json
import os
import sys
from pathlib import Path

# Resolve project root (expects 'app' dir present up the tree)
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

from app.services.ingester.core.router import Router

def main():
	parser = argparse.ArgumentParser(description="Process a PPTX by converting to PDF and extracting clean data.")
	parser.add_argument("--file", "-f", default=str(PROJECT_ROOT / "app" / "services" / "test_files" / "Module7.pptx"), help="Path to input .pptx file")
	parser.add_argument("--out", "-o", default=str(PROJECT_ROOT / "out" / "Module7.json"), help="Path to output JSON file")
	parser.add_argument("--verbose", action="store_true", help="Verbose logging")
	args = parser.parse_args()

	pptxPath = Path(args.file)
	if not pptxPath.exists():
		raise SystemExit(f"Input PPTX not found: {pptxPath}")

	# Ensure output directory exists
	outPath = Path(args.out)
	outPath.parent.mkdir(parents=True, exist_ok=True)

	router = Router(openaiApiKey=os.getenv("OPENAI_API_KEY") or os.getenv("OPENAIKEY"), verbose=args.verbose)

	# Router handles: convert PPTX -> PDF, analyze PDF, extract; then cleans up temp PDF
	data = router.process(str(pptxPath))

	with open(outPath, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False, indent=2)

	print(f"Wrote: {outPath}")


if __name__ == "__main__":
	main()
