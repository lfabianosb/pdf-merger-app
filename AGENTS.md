# PDF Merger Application

A full-stack application for merging multiple PDF files into one.

## Architecture

- **Backend**: FastAPI (Python) — endpoints for merging PDFs, running OCR on images/PDFs, generating an index from multiple PDFs, and merge+index (cover page with embedded index)
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

#### `POST /api/merge-index`
- Description: Receives 2+ PDF files, uses the first file as a cover page, appends an index table (listing all files with their page ranges) to the bottom of that cover page, then merges the cover page with the remaining PDFs into a single downloadable file
- Accepts: multipart/form-data with multiple `files` fields (minimum 2 files)
- Returns: merged PDF as a downloadable file (`Content-Disposition: attachment`)
- Validate that all uploaded files are actual PDFs and that at least 2 files are provided
- The first file in the upload sequence is treated as the cover page
- Generate an index table with columns: File Name, Start Page (1-based), and End Page
  - The cover page is page 1
  - Remaining files' page ranges are offset accordingly (e.g., if cover is 1 page, file #2 starts at page 2)
- Draw the index directly onto the cover page (bottom portion). The index must follow this visual format (matching the reference image "Informação da Evidência.png"):
  - A title at the top: Informação da Evidência and Página
  - A horizontal separator line below the title
  - Items listed with the file name on the left and the starting page number right-aligned
  - Example layout:
    ```
    Informação da Evidência                                 Página
    ──────────────────────────────────────────────────────────────
    Attached file 1 .......................................... 2
    Attached file 2 .......................................... 5
    Attached file 3 .......................................... 8
    ```
- Implementation: use `pypdf` content streams to draw text and lines, or use `reportlab` to generate an overlay image that is then merged onto the cover page via `pypdf`
- Merge the modified cover page with all remaining files in upload order
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
- Four distinct sections/features on the page:

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

### 4. Merge and Index
- File input: accept multiple PDF files via `<input type="file" multiple accept=".pdf">` (minimum 2 files required)
- The first file in the list is treated as the **cover page** — label it clearly in the UI
- Allow reordering files (drag-and-drop within the list) so the user can choose which file is the cover
- Display file list with name, size, a "Cover" badge on the first file, and a remove button per file
- Validate that at least 2 files are selected before enabling the submit button
- Send files via `FormData` with `fetch()` to `/api/merge-index`
- On success: display a preview of the generated index table (showing the same format that will appear on the cover: title, separator, file name and start page), along with a download link for the returned PDF blob
- On error: display a user-friendly message
- Loading state while request is in flight

## Constraints

- No frameworks like React, Vue, or Angular — vanilla JS only
- No build step required — open `index.html` directly in a browser
- Backend must validate MIME type (`application/pdf`)
- Maximum file upload size: 50MB total
