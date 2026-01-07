import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

# --- Classes ------------------------------------------------------------

class PptxToPdfConverter:
	# Converts PPTX files to PDF via pluggable engines.
	# Engines supported:
	# - PowerPoint (Windows Office automation)
	# - LibreOffice (headless soffice)

	def __init__(self, prefer: str = "auto") -> None:
		self.prefer = prefer  # 'auto' | 'powerpoint' | 'libreoffice'

	def convert(self, pptxPath: str, outDir: Optional[str] = None) -> str:
		src = Path(pptxPath)
		if not src.exists():
			raise RuntimeError(f"Source not found: {pptxPath}")
		outRoot = Path(outDir) if outDir else Path(tempfile.gettempdir())
		outRoot.mkdir(parents=True, exist_ok=True)
		dst = outRoot / (src.stem + ".pdf")

		# If output exists and is newer than input, reuse
		if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
			return str(dst)

		engine = self._chooseEngine()
		ok = False
		err: Optional[str] = None

		if engine == "powerpoint":
			try:
				self._convertWithPowerPoint(str(src), str(dst))
				ok = dst.exists()
			except Exception as e:
				err = f"PowerPoint export failed: {e}"
		if not ok:
			try:
				self._convertWithLibreOffice(str(src), str(dst))
				ok = dst.exists()
			except Exception as e:
				err = f"LibreOffice export failed: {e}"

		if not ok:
			raise RuntimeError(err or "Conversion failed")
		return str(dst)

	def _chooseEngine(self) -> str:
		if self.prefer in ("powerpoint", "libreoffice"):
			return self.prefer
		# auto: prefer PowerPoint on Windows if available
		if os.name == "nt" and self._powerPointAvailable():
			return "powerpoint"
		return "libreoffice"

	def _powerPointAvailable(self) -> bool:
		# Heuristic: presence of Office installs doesn't guarantee COM availability,
		# but we try and let conversion fall back if it fails.
		return os.name == "nt"

	def _convertWithPowerPoint(self, src: str, dst: str) -> None:
		# Export via PowerPoint COM (Windows only).
		if os.name != "nt":
			raise RuntimeError("PowerPoint export requires Windows")
		try:
			import win32com.client  # type: ignore
		except Exception as e:
			raise RuntimeError(f"win32com not available: {e}")

		powerpoint = win32com.client.Dispatch("PowerPoint.Application")
		powerpoint.Visible = 1
		try:
			presentation = powerpoint.Presentations.Open(src, WithWindow=False)
			# 32 = ppSaveAsPDF
			presentation.SaveAs(dst, 32)
			presentation.Close()
		finally:
			try:
				powerpoint.Quit()
			except Exception:
				pass

	def _convertWithLibreOffice(self, src: str, dst: str) -> None:
		# Export via headless LibreOffice (cross-platform).
		outDir = str(Path(dst).parent)
		cmd = [
			"soffice",
			"--headless",
			"--convert-to",
			"pdf",
			src,
			"--outdir",
			outDir,
		]
		proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
		if proc.returncode != 0:
			raise RuntimeError(proc.stderr or proc.stdout or "LibreOffice failed")
