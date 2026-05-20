"""PDF Merger Backend — FastAPI application with three endpoints:

    POST /api/merge  – Merge multiple PDFs into one
    POST /api/ocr    – Run OCR on an image or PDF, return a searchable PDF
    POST /api/index  – Return a JSON page index for a list of PDFs
"""

import logging
import tempfile
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pypdf import PdfReader, PdfWriter
from starlette.background import BackgroundTask

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────────

MAX_TOTAL_SIZE_MB = 50
MAX_TOTAL_SIZE_BYTES = MAX_TOTAL_SIZE_MB * 1024 * 1024

IMAGE_QUALITY = 90        # JPEG quality for image→PDF conversion (0–100)
COMPRESS_LEVEL = 9        # zlib compression for PDF streams (0–9)

OCR_LANGUAGE = "por+eng"  # Tesseract language codes
OCR_OPTIMIZE = 1           # ocrmypdf optimisation level (0–3)
OCR_DPI = 300              # PDF render DPI before OCR

ALLOWED_IMAGE_MIME = {"image/png", "image/jpeg"}

# ── Optional dependency checks ───────────────────────────────────────────────


def _is_ocrmypdf_available() -> bool:
    """Return True if ocrmypdf (and its Tesseract dependency) are installed."""
    try:
        import ocrmypdf  # type: ignore # noqa: F401
        return True
    except ImportError:
        return False


# ── Validation helpers ───────────────────────────────────────────────────────


def validate_pdf(file: UploadFile) -> None:
    """Raise HTTPException if *file* is not a valid PDF."""
    content_type = file.content_type or ""
    if content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{content_type}'. Only PDF files are accepted.",
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


def validate_image_or_pdf(file: UploadFile) -> None:
    """Raise HTTPException if *file* is not a PNG, JPEG, or PDF."""
    content_type = file.content_type or ""
    if content_type == "application/pdf":
        validate_pdf(file)
        return
    if content_type in ALLOWED_IMAGE_MIME:
        return
    raise HTTPException(
        status_code=400,
        detail=f"Unsupported file type '{content_type}'. Allowed: PNG, JPEG, PDF.",
    )


# ── Processing helpers ───────────────────────────────────────────────────────


def image_to_pdf(image_path: Path, pdf_path: Path) -> None:
    """Convert a raster image (PNG/JPEG) to a single-page PDF."""
    img = Image.open(image_path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    img.save(str(pdf_path), "PDF", quality=IMAGE_QUALITY)


def ocr_pdf(input_path: Path, output_path: Path) -> None:
    """Run ocrmypdf on *input_path*, writing a searchable PDF to *output_path*.

    Handles deskew, rotation, and forces OCR so scanned/image-based pages
    always receive a text layer.
    """
    import ocrmypdf  # type: ignore

    languages = OCR_LANGUAGE.split("+")
    logger.info(
        "OCR: %s  lang=%s  dpi=%d  force_ocr=True",
        input_path.name, OCR_LANGUAGE, OCR_DPI,
    )
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


def get_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF file."""
    return len(PdfReader(str(pdf_path)).pages)


def save_upload(file: UploadFile) -> Path:
    """Write an uploaded file to a temporary location and return its Path."""
    suffix = Path(file.filename or "upload").suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file.file.read())
    tmp.close()
    return Path(tmp.name)


def cleanup(*paths: Path) -> None:
    """Safely delete multiple temporary files."""
    for p in paths:
        with suppress(FileNotFoundError):
            p.unlink()


# ── Lifespan ─────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log warnings about missing optional dependencies on startup."""
    if not _is_ocrmypdf_available():
        logger.warning(
            "ocrmypdf is not installed — /api/ocr will be unavailable. "
            "Install it with: pip install ocrmypdf"
        )
    yield


# ── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="PDF Tools API",
    description="Merge PDFs, run OCR, and generate indexes.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    """Health check — also reports whether OCR is available."""
    return {
        "status": "ok",
        "ocr_available": _is_ocrmypdf_available(),
    }


@app.post("/api/merge", summary="Merge PDFs")
async def merge_pdfs(
    files: list[UploadFile],
) -> FileResponse:
    """Receive multiple PDFs, merge them in upload order, return a single PDF."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="At least 2 PDF files are required.")

    # ── Size validation ──
    total = 0
    for f in files:
        content = await f.read()
        total += len(content)
        f.file.seek(0)
    if total > MAX_TOTAL_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Total file size exceeds {MAX_TOTAL_SIZE_MB} MB limit.",
        )

    # ── Content validation ──
    for f in files:
        validate_pdf(f)

    # ── Merge ──
    temp_files: list[Path] = []
    writer = PdfWriter()

    try:
        for f in files:
            temp_files.append(save_upload(f))

        for src in temp_files:
            writer.append(str(src))

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            output_path = Path(tmp.name)
        writer.write(str(output_path))
        writer.close()

    except Exception as exc:
        writer.close()
        cleanup(*temp_files)
        raise HTTPException(status_code=500, detail=f"Failed to merge PDFs: {exc}") from exc
    finally:
        writer.close()
        cleanup(*temp_files)

    return FileResponse(
        path=output_path,
        filename="merged.pdf",
        media_type="application/pdf",
        background=BackgroundTask(lambda: cleanup(output_path)),
    )


@app.post("/api/ocr", summary="OCR a file")
async def ocr_endpoint(
    files: list[UploadFile],
) -> FileResponse:
    """Receive a single PNG/JPEG/PDF, OCR it, and return a searchable PDF."""
    if not files:
        raise HTTPException(status_code=400, detail="No file provided.")
    if len(files) > 1:
        raise HTTPException(status_code=400, detail="Only one file is accepted for OCR.")

    if not _is_ocrmypdf_available():
        raise HTTPException(
            status_code=501,
            detail="OCR is unavailable — ocrmypdf is not installed on the server.",
        )

    file = files[0]

    # ── Size validation ──
    content = await file.read()
    file.file.seek(0)
    if len(content) > MAX_TOTAL_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File size exceeds {MAX_TOTAL_SIZE_MB} MB limit.",
        )

    # ── Content validation ──
    validate_image_or_pdf(file)

    # ── Process ──
    input_tmp: Path | None = None
    work_pdf: Path | None = None

    try:
        input_tmp = save_upload(file)
        content_type = file.content_type or ""

        if content_type in ALLOWED_IMAGE_MIME:
            # Convert image → PDF, then OCR that PDF
            work_pdf = Path(tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name)
            image_to_pdf(input_tmp, work_pdf)
        else:
            # Already a PDF — OCR directly
            work_pdf = input_tmp

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            output_path = Path(tmp.name)

        ocr_pdf(work_pdf, output_path)

    except Exception as exc:
        cleanup(input_tmp, work_pdf)
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc
    finally:
        if work_pdf is not input_tmp:
            cleanup(input_tmp)   # keep work_pdf for response
        if work_pdf is input_tmp:
            pass  # input_tmp is also work_pdf, cleaned up below if needed

    # Clean up intermediate files (but NOT output_path — that's the response)
    if content_type in ALLOWED_IMAGE_MIME:
        # input_tmp (image) and work_pdf (temp PDF) both can go
        cleanup(input_tmp, work_pdf)
    else:
        cleanup(input_tmp)  # input_tmp was the PDF we OCR'd

    base_name = Path(file.filename or "document").stem

    return FileResponse(
        path=output_path,
        filename=f"{base_name}_searchable.pdf",
        media_type="application/pdf",
        background=BackgroundTask(lambda: cleanup(output_path)),
    )


@app.post("/api/index", summary="Generate PDF index")
async def index_pdfs(
    files: list[UploadFile],
):
    """Receive multiple PDFs and return a JSON page index as if they were concatenated."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # ── Size validation ──
    total = 0
    for f in files:
        content = await f.read()
        total += len(content)
        f.file.seek(0)
    if total > MAX_TOTAL_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Total file size exceeds {MAX_TOTAL_SIZE_MB} MB limit.",
        )

    # ── Content validation ──
    for f in files:
        validate_pdf(f)

    # ── Build index ──
    temp_files: list[Path] = []
    index: list[dict] = []
    current_page = 1

    try:
        for f in files:
            tmp = save_upload(f)
            temp_files.append(tmp)
            pages = get_page_count(tmp)
            index.append({
                "filename": f.filename or "unknown.pdf",
                "start_page": current_page,
                "end_page": current_page + pages - 1,
                "total_pages": pages,
            })
            current_page += pages

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read PDFs: {exc}") from exc
    finally:
        cleanup(*temp_files)

    return index


# ── Static files (MUST be last so API routes take precedence) ────────────────

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
