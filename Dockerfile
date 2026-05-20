# PDF Merger — Alpine Linux Docker image
# Serves the FastAPI backend + vanilla HTML/CSS/JS frontend from a single container.
#
# Build:
#   docker build -t pdf-merger .
#
# Run:
#   docker run -p 8000:8000 pdf-merger
#   docker run -p 8000:8000 -e OCR_LANGUAGE=eng+por pdf-merger   # custom OCR langs
#   docker run -p 8000:8000 -e MAX_TOTAL_SIZE_MB=100 pdf-merger  # raise size limit

# ────────────────── Build stage ──────────────────
FROM python:3.12-alpine AS builder

# Install build tools + headers needed to compile Pillow / lxml / etc.
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    jpeg-dev \
    zlib-dev \
    openjpeg-dev \
    tiff-dev \
    freetype-dev \
    lcms2-dev \
    libffi-dev \
    libwebp-dev \
    libpng-dev \
    cargo \
    rust

WORKDIR /app

# Install Python deps into a virtualenv so we can copy the whole thing
# (ensures console scripts like uvicorn land in .../bin/)
COPY backend/requirements.txt .
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir -r requirements.txt

# ────────────────── Final image ──────────────────
FROM python:3.12-alpine

# Runtime-only system packages (no build tools)
RUN apk add --no-cache \
    tesseract-ocr \
    tesseract-ocr-data-eng \
    tesseract-ocr-data-por \
    ghostscript \
    libjpeg-turbo \
    libpng \
    openjpeg \
    zlib \
    libwebp

WORKDIR /app

# Copy the entire virtualenv from builder stage
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy application code
COPY backend/main.py backend/
COPY frontend/ frontend/

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Start Uvicorn directly (bind to 0.0.0.0 so it's reachable from outside the container)
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
