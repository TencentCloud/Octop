"""Render an Office document in its execution environment, without modifying the source."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def libreoffice_command() -> str:
    for command in ("soffice", "libreoffice"):
        if found := shutil.which(command):
            return found
    candidates: list[Path] = []
    if sys.platform == "darwin":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    elif os.name == "nt":
        for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
            if base := os.environ.get(variable):
                candidates.append(Path(base) / "LibreOffice" / "program" / "soffice.com")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise OSError("LibreOffice is required to render Office documents.")


def render(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if not source.is_file() or source.suffix.lower() not in {".docx", ".xlsx", ".pptx"}:
        raise ValueError("Expected a .docx, .xlsx or .pptx file.")
    if destination.exists():
        raise FileExistsError(f"Choose a new preview directory: {destination}")
    office = libreoffice_command()
    poppler = shutil.which("pdftoppm")
    if poppler is None:
        raise OSError("Poppler pdftoppm is required to render page images.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        work = Path(temporary)
        pages = work / "pages"
        pages.mkdir()
        subprocess.run(
            [
                office,
                f"-env:UserInstallation={(work / 'profile').as_uri()}",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(work),
                str(source),
            ],
            check=True,
            timeout=180,
        )
        converted = work / source.with_suffix(".pdf").name
        if not converted.is_file():
            raise OSError("LibreOffice did not produce a PDF.")
        pdf = pages / "document.pdf"
        converted.rename(pdf)
        subprocess.run(
            [poppler, "-png", "-r", "120", str(pdf), str(pages / "page")], check=True, timeout=180
        )
        if not any(pages.glob("page-*.png")):
            raise OSError("Poppler did not produce any page images.")
        pages.rename(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        render(args.source, args.destination)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"{exc}\n")
    print(args.destination.absolute())
    return 0


if __name__ == "__main__":
    sys.exit(main())
