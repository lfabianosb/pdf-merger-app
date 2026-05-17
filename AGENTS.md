# PDF Merger Application

A full-stack application for merging multiple PDF files into one.

## Architecture

- **Backend**: FastAPI (Python) — single endpoint that receives a list of PDF files, merges them in order, and returns the merged file
- **Frontend**: Vanilla HTML, CSS, and JavaScript — drag-and-drop or file picker to select PDFs, send to backend, and download the result

## Backend

- Framework: FastAPI
- PDF manipulation: `pypdf` (formerly PyPDF2)
- Endpoint: `POST /api/merge`
- Accepts: multipart/form-data with multiple `files` fields
- Returns: merged PDF as a downloadable file (`Content-Disposition: attachment`)
- Validate that all uploaded files are actual PDFs
- Preserve page order based on upload sequence
- Clean up temporary files after response is sent
- Include CORS middleware to allow frontend origin

## Frontend

- Single-page HTML with embedded CSS and JavaScript
- File input: accept multiple PDF files via `<input type="file" multiple accept=".pdf">`
- Allow reordering files (drag-and-drop within the list)
- Display file list with size, name, and remove button per file
- Send files via `FormData` with `fetch()` to backend
- On success: create a temporary download link for the returned PDF blob
- On error: display a user-friendly message
- Loading state while request is in flight

## Constraints

- No frameworks like React, Vue, or Angular — vanilla JS only
- No build step required — open `index.html` directly in a browser
- Backend must validate MIME type (`application/pdf`)
- Maximum file upload size: 50MB total
