#!/usr/bin/env python3
"""
OCR PDF - Creates a searchable copy of a scanned/image-based PDF.

Dependencies (Ubuntu):
    sudo apt-get update
    sudo apt-get install -y tesseract-ocr tesseract-ocr-por poppler-utils ghostscript
    pip install ocrmypdf pdf2image pytesseract pypdf

Usage:
    python ocr_pdf.py input.pdf
    python ocr_pdf.py input.pdf --output searchable_output.pdf
    python ocr_pdf.py input.pdf --lang por+eng
"""

import argparse
import subprocess
import sys
from pathlib import Path


def check_dependencies():
    """Check that required system tools are installed."""
    missing = []
    for tool in ["tesseract", "gs", "pdftoppm"]:
        result = subprocess.run(["which", tool], capture_output=True)
        if result.returncode != 0:
            missing.append(tool)
    if missing:
        print("❌ Missing system tools:", ", ".join(missing))
        print("\nInstall them with:")
        print("  sudo apt-get update")
        print("  sudo apt-get install -y tesseract-ocr tesseract-ocr-por poppler-utils ghostscript")
        sys.exit(1)

    try:
        import ocrmypdf  # noqa: F401
    except ImportError:
        print("❌ Python package 'ocrmypdf' not found.")
        print("  Install with: pip install ocrmypdf")
        sys.exit(1)


def list_tesseract_languages():
    """Return available Tesseract language packs."""
    result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    # Output goes to stderr in older versions
    langs = (result.stdout + result.stderr).strip().splitlines()
    # Filter out the header line
    return [l for l in langs if not l.startswith("List") and l.strip()]


def run_ocr(input_path: str, output_path: str, lang: str = "por+eng",
            deskew: bool = True, rotate: bool = True):
    """
    Run OCR on input_path and write a searchable PDF to output_path.

    Args:
        input_path:  Path to the source PDF.
        output_path: Path for the output searchable PDF.
        lang:        Tesseract language codes, e.g. 'por+eng' for Portuguese + English.
        deskew:      Automatically straighten skewed pages.
        rotate:      Automatically rotate pages to correct orientation.
    """
    import ocrmypdf

    input_file = Path(input_path)
    if not input_file.exists():
        print(f"❌ Input file not found: {input_path}")
        sys.exit(1)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"📄 Input  : {input_file}")
    print(f"💾 Output : {output_file}")
    print(f"🌐 Language(s): {lang}")

    available = list_tesseract_languages()
    requested = lang.split("+")
    for req in requested:
        if req not in available:
            print(f"⚠️  Language '{req}' not found in Tesseract. Available: {available}")
            print("   Install Portuguese with: sudo apt-get install -y tesseract-ocr-por")

    try:
        ocrmypdf.ocr(
            str(input_file),           # positional: input_file_or_options
            str(output_file),          # positional: output_file
            language=lang.split("+"), # list of language codes, e.g. ['por', 'eng']
            deskew=deskew,
            rotate_pages=rotate,
            force_ocr=True,            # OCR even if text layer already exists
            optimize=1,                # Light optimisation – keeps file small
            output_type="pdf",         # Use 'pdfa' for PDF/A archival format
            progress_bar=True,
        )
        print(f"\n✅ Searchable PDF created: {output_file}")
        print(f"   File size: {output_file.stat().st_size / 1024:.1f} KB")
    except Exception as exc:
        print(f"❌ OCR failed: {exc}")
        sys.exit(1)


def preview_extracted_text(output_path: str, max_chars: int = 1000):
    """Print a preview of the extracted text from the searchable PDF."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(output_path)
        print("\n--- Text preview (first page) ---")
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                print(text[:max_chars])
                if len(text) > max_chars:
                    print(f"... [{len(text) - max_chars} more characters]")
                break
        else:
            print("(No selectable text found on first page)")
        print("---------------------------------\n")
    except ImportError:
        pass  # pypdf is optional for the preview


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Create a searchable (OCR'd) copy of an image-based PDF."
    )
    parser.add_argument("input", help="Path to the input PDF file")
    parser.add_argument(
        "--output", "-o",
        help="Path for the output PDF (default: <input>_searchable.pdf)",
        default=None,
    )
    parser.add_argument(
        "--lang", "-l",
        help="Tesseract language codes, e.g. 'por+eng' (default: por+eng)",
        default="por+eng",
    )
    parser.add_argument(
        "--no-deskew", action="store_true",
        help="Disable automatic page deskewing"
    )
    parser.add_argument(
        "--no-rotate", action="store_true",
        help="Disable automatic page rotation"
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="Print a text preview after OCR completes"
    )

    args = parser.parse_args()

    # Build output path if not given
    if args.output is None:
        input_path = Path(args.input)
        args.output = str(input_path.parent / f"{input_path.stem}_searchable.pdf")

    check_dependencies()
    run_ocr(
        input_path=args.input,
        output_path=args.output,
        lang=args.lang,
        deskew=not args.no_deskew,
        rotate=not args.no_rotate,
    )

    if args.preview:
        preview_extracted_text(args.output)


if __name__ == "__main__":
    main()