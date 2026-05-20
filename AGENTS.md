# PDF Merger Application

A full-stack application for merging multiple PDF files into one.

## Architecture

- **Backend**: FastAPI (Python) — endpoints for merging PDFs, running OCR on images/PDFs, and generating an index from multiple PDFs
- **Frontend**: Vanilla HTML, CSS, and JavaScript — drag-and-drop or file picker to select PDFs, send to backend, and download the result

## Backend

- Framework: FastAPI
- PDF manipulation: `pypdf` (formerly PyPDF2)
- OCR: `pytesseract` + `pdf2image` (for OCR on images/PDFs)
- Include CORS middleware to allow frontend origin

### Endpoints

#### `POST /api/merge`
- Description: Merges multiple PDFs into a single file
- Accepts: multipart/form-data with multiple `files` fields
- Returns: merged PDF as a downloadable file (`Content-Disposition: attachment`)
- Validate that all uploaded files are actual PDFs
- Preserve page order based on upload sequence
- Clean up temporary files after response is sent

#### `POST /api/ocr`
- Description: Runs OCR on an uploaded file (PNG, JPG, or PDF) and returns a PDF with the extracted text overlaid
- Accepts: multipart/form-data with a single `file` field
- Validates: file must be PNG, JPG, or PDF
- Returns: a downloadable PDF with the OCR result (`Content-Disposition: attachment`)
- For image files: run OCR directly via `pytesseract` and embed the recognized text into a searchable PDF
- For PDF files: convert each page to an image, run OCR on each page, then rebuild a searchable PDF
- Clean up temporary files after response is sent

#### `POST /api/index`
- Description: Receives a list of PDF files and returns a JSON object containing the index of each file, as if all PDFs were concatenated
- Accepts: multipart/form-data with multiple `files` fields
- Returns: a JSON array with objects containing:
  - `filename`: the original file name
  - `start_page`: the page number where the file starts in the concatenated document (1-based)
  - `end_page`: the page number where the file ends
- Page count calculated by reading each PDF's metadata
- Clean up temporary files after response is sent

## Frontend

- Single-page HTML with embedded CSS and JavaScript
- Three distinct sections/features on the page:

### 1. PDF Merger
- File input: accept multiple PDF files via `<input type="file" multiple accept=".pdf">`
- Allow reordering files (drag-and-drop within the list)
- Display file list with size, name, and remove button per file
- Send files via `FormData` with `fetch()` to `/api/merge`
- On success: create a temporary download link for the returned PDF blob
- On error: display a user-friendly message
- Loading state while request is in flight

### 2. OCR
- File input: accept a single file via `<input type="file" accept=".png,.jpg,.jpeg,.pdf">`
- Display selected file name and size
- Send file via `FormData` with `fetch()` to `/api/ocr`
- On success: create a temporary download link for the returned PDF blob
- On error: display a user-friendly message
- Loading state while request is in flight

### 3. PDF Index
- File input: accept multiple PDF files via `<input type="file" multiple accept=".pdf">`
- Display file list with name, size, and remove button per file
- Send files via `FormData` with `fetch()` to `/api/index`
- On success: display a table showing:
  - File name
  - Start page (1-based)
  - End page
  - Total pages per file
- On error: display a user-friendly message
- Loading state while request is in flight

## Constraints

- No frameworks like React, Vue, or Angular — vanilla JS only
- No build step required — open `index.html` directly in a browser
- Backend must validate MIME type (`application/pdf`)
- Maximum file upload size: 50MB total
