"""PDF Merger Backend — FastAPI application that merges multiple PDF files
with optional OCR to make image-based text searchable."""

import logging
import tempfile
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader, PdfWriter
from starlette.background import BackgroundTask

logger = logging.getLogger(__name__)

MAX_TOTAL_SIZE_MB = 50
MAX_TOTAL_SIZE_BYTES = MAX_TOTAL_SIZE_MB * 1024 * 1024

# --- Shrink settings ---
# Image recompression quality (0–100). 90 keeps visual quality near-original
# while reducing file size for PNG/JPEG images embedded in the PDF.
IMAGE_QUALITY = 90

# zlib compression level for page content streams (0–9). 9 = best lossless
# compression, higher CPU cost.
COMPRESS_LEVEL = 9

# --- OCR settings ---
OCR_LANGUAGE = "por+eng"      # Tesseract language code(s), e.g. "por+eng"
OCR_SKIP_TEXT = True          # Only OCR pages that lack selectable text
OCR_OPTIMIZE = 1              # Light optimisation for ocrmypdf (1=light)
OCR_DPI = 300                 # DPI for rendering pages to images before OCR


def _is_ocrmypdf_available() -> bool:
    """Check whether ocrmypdf (and tesseract) are installed."""
    try:
        import ocrmypdf  # type: ignore # noqa: F401
        return True
    except ImportError:
        return False


def validate_pdf(file: UploadFile) -> None:
    """Validate that the uploaded file is a valid PDF."""
    content_type = file.content_type or ""
    if content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{content_type}'. Only PDF files are allowed.",
        )

    header = file.file.read(5)
    file.file.seek(0)
    if header != b"%PDF-":
        raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF.")

    try:
        PdfReader(file.file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted PDF: {exc}") from exc
    finally:
        file.file.seek(0)


def ocr_pdf(input_path: Path, output_path: Path) -> None:
    """Run OCR on *input_path* and write the searchable PDF to *output_path*.

    Uses parameters and behaviour aligned with backend/ocr.py: deskew/rotate
    and force OCR to ensure a searchable output. Language is passed as a
    list (e.g. ['por','eng']).
    """
    import ocrmypdf  # type: ignore

    logger.info(
        "Running OCR on %s (lang=%s, force_ocr=%s, dpi=%d)…",
        input_path.name,
        OCR_LANGUAGE,
        True,
        OCR_DPI,
    )

    # ocrmypdf accepts a list of language codes
    languages = OCR_LANGUAGE.split("+") if isinstance(OCR_LANGUAGE, str) else OCR_LANGUAGE

    ocrmypdf.ocr(
        str(input_path),
        str(output_path),
        language=languages,
        deskew=True,
        rotate_pages=True,
        force_ocr=True,
        optimize=OCR_OPTIMIZE,
        output_type="pdf",
        pdf_render_dpi=OCR_DPI,
        quiet=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    if not _is_ocrmypdf_available():
        logger.warning(
            "ocrmypdf is not installed — OCR will be unavailable. "
            "Install it with: pip install ocrmypdf"
        )
    yield


app = FastAPI(
    title="PDF Merger API",
    description="Merge multiple PDF files into a single PDF, with optional OCR.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    ocr_available = _is_ocrmypdf_available()
    return {
        "status": "ok",
        "ocr_available": ocr_available,
    }


@app.post("/api/merge")
async def merge_pdfs(
    request: Request,
    files: list[UploadFile],
    ocr: bool = Query(
        default=True,
        description="Whether to run OCR on image-based pages before merging.",
    ),
) -> FileResponse:
    """Receive a list of PDF files, optionally OCR them, merge in order, and return the result."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    if len(files) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 PDF files are required for merging.",
        )

    if ocr and not _is_ocrmypdf_available():
        raise HTTPException(
            status_code=501,
            detail="OCR was requested but ocrmypdf is not installed on the server.",
        )

    total_size = 0
    for pdf in files:
        content = await pdf.read()
        total_size += len(content)
        pdf.file.seek(0)
        if total_size > MAX_TOTAL_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Total file size exceeds {MAX_TOTAL_SIZE_MB}MB limit.",
            )

    for pdf in files:
        validate_pdf(pdf)

    writer = PdfWriter()
    temp_input_files: list[Path] = []
    ocr_temp_files: list[Path] = []

    try:
        # --- Step 1: save each uploaded PDF to a temp file ---
        for pdf in files:
            suffix = Path(pdf.filename or "document.pdf").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await pdf.read()
                tmp.write(content)
                temp_input_files.append(Path(tmp.name))

        # --- Step 2: OCR each file (if enabled), producing searchable copies ---
        if ocr:
            for tmp_path in temp_input_files:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".pdf"
                ) as ocr_tmp:
                    ocr_output_path = Path(ocr_tmp.name)
                ocr_temp_files.append(ocr_output_path)

                try:
                    ocr_pdf(tmp_path, ocr_output_path)
                except Exception:
                    logger.exception(
                        "OCR failed for %s — falling back to original", tmp_path.name
                    )
                    # Discard the (possibly empty) OCR output and keep original
                    with suppress(FileNotFoundError):
                        ocr_output_path.unlink()
                    ocr_temp_files[-1] = tmp_path  # use original for this file
            source_files = ocr_temp_files
        else:
            source_files = temp_input_files

        # --- Step 3: append each (possibly OCR'd) file to the merged PDF ---
        for src_path in source_files:
            writer.append(str(src_path))

        # --- Step 4: skipping compression ---
        logger.info("Skipping compression step; preserving original page content and images.")

        # --- Step 5: write merged result ---
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as merged_tmp:
            output_path = Path(merged_tmp.name)

        writer.write(str(output_path))
        writer.close()

    except Exception as exc:
        writer.close()
        for tmp_path in temp_input_files:
            with suppress(FileNotFoundError):
                tmp_path.unlink()
        for tmp_path in ocr_temp_files:
            with suppress(FileNotFoundError):
                tmp_path.unlink()
        raise HTTPException(
            status_code=500, detail=f"Failed to merge PDFs: {exc}"
        ) from exc

    finally:
        for tmp_path in temp_input_files:
            with suppress(FileNotFoundError):
                tmp_path.unlink()
        # Only clean OCR temp files that aren't aliased to input files
        if ocr:
            input_set = set(temp_input_files)
            for tmp_path in ocr_temp_files:
                if tmp_path not in input_set:
                    with suppress(FileNotFoundError):
                        tmp_path.unlink()

    return FileResponse(
        path=output_path,
        filename="merged.pdf",
        media_type="application/pdf",
        background=BackgroundTask(lambda p=output_path: p.unlink(missing_ok=True)),
    )


# ── Static files mount (MUST come last so API routes take precedence) ──
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
