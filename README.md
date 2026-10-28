# PackGuard AI — Packaging Artwork & Specification Verification

PackGuard AI compares product specification spreadsheets (`.xlsx`, `.xls`) against packaging artwork (`.pdf`). It identifies inconsistencies, missing information, incorrect values, and potential content that requires review or addition to packaging artwork with rigorous, traceable evidence.

---

## Key Architecture & Features

- **Strict Primary Workflow**: Opens with exactly two choices: **Analyse Existing Product** and **Analyse New Product**.
- **Initially Empty Catalog**: Zero demo or fake seed products. Starts completely clean.
- **Multi-File Specification Contradiction Check**: Stops analysis and alerts if uploaded spreadsheets specify conflicting or incompatible values.
- **Traceable Evidence**: Every finding cites exact Excel filename, sheet, and cell, as well as PDF page and bounding box coordinates.
- **Interactive Visual Previews**:
  - **Artwork Preview**: High-resolution rendered PDF with an animated highlight outline directly on the verified bounding box.
  - **Specification Preview**: Displays supporting sheet, target cell, and surrounding cell context matrix.
- **Safe PDF Fix Engine**:
  - Applies edits only when layout, font family, font size, and text boundaries can be safely preserved.
  - Non-destructive candidate preview before committing.
  - **Undo**: Discards candidate without modifying files.
  - **Save**: Creates an immutable, numbered version (`v1`, `v2`, etc.) while strictly preserving the original uploaded PDF.
- **Analysis History Delta**: Automatically tracks resolved issues, persistent issues, and newly detected issues between consecutive analyses.
- **CSV Export**: Comprehensive export of all findings and evidence, secured against formula injection (`=`, `+`, `-`, `@`).
- **Email Report Draft**: Constructs a factual review request and launches the default email application via `mailto:`.

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── config.py              # Environment configuration & paths
│   │   ├── models.py              # Pydantic data schemas
│   │   ├── storage.py             # JSON file & version storage service
│   │   ├── test_engine.py         # End-to-end backend verification test
│   │   ├── services/
│   │   │   ├── excel_parser.py    # Sheet and cell-level field extraction
│   │   │   ├── conflict_detector.py # Multi-specification contradiction detector
│   │   │   ├── pdf_parser.py      # PyMuPDF text span, coordinates & page renderer
│   │   │   ├── analysis_engine.py # Bidirectional verification & safety rules
│   │   │   ├── pdf_fixer.py       # Safe redaction, insertion, candidate preview & versioning
│   │   │   ├── ai_service.py      # LLM reasoning & deterministic fallback
│   │   │   ├── history_comparator.py # Cross-analysis delta comparator
│   │   │   ├── csv_exporter.py    # CSV generator with formula injection protection
│   │   │   └── email_report_builder.py # Mailto draft builder
│   │   └── main.py                # FastAPI REST router
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Home.jsx           # Initial screen with exactly 2 options
│   │   │   ├── ExistingProducts.jsx # Product card grid with search & deletion
│   │   │   ├── NewProductForm.jsx # Upload form with contradiction alert
│   │   │   ├── ProductDetail.jsx  # Historical analyses & product actions
│   │   │   ├── AnalysisResults.jsx # Results dashboard, checkboxes, metrics
│   │   │   ├── ArtworkPreview.jsx # PDF preview with exact bbox overlay
│   │   │   ├── SpecPreview.jsx    # Excel cell context matrix preview
│   │   │   ├── FixModal.jsx       # Candidate inspection, Undo, and Save
│   │   │   ├── DetailsModal.jsx   # Complete evidence drill-down
│   │   │   └── EmailModal.jsx     # Email draft preview & mailto launcher
│   │   ├── App.jsx                # Main router & layout coordinator
│   │   ├── App.css                # Professional packaging industry CSS
│   │   └── index.css              # Design tokens and base styles
│   ├── vite.config.js             # Vite configuration with /api proxy
│   └── package.json
├── data/                          # Persistent storage for products, analyses & versions
├── .env.example                   # Environment configuration template
├── package.json                   # Root package configuration with convenient dev scripts
├── requirements.txt               # Python package dependencies
└── README.md
```

---

## Prerequisites

Before running the application, make sure you have:
1. **Python 3.10+** (Python 3.12 recommended)
2. **Node.js 18+** (Node v20+ recommended)

---

## Quick Setup (One Time)

### 1. Install Backend Dependencies
Open your terminal in the project root:
```bash
pip install -r requirements.txt
```
*(Dependencies: `fastapi`, `uvicorn`, `python-multipart`, `pydantic`, `openpyxl`, `pymupdf`, `httpx`, `python-dotenv`)*

### 2. Install Frontend Dependencies
```bash
cd frontend
npm install
cd ..
```

### 3. Environment Configuration (Optional)
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(On Windows Command Prompt: `copy .env.example .env`)*

- If you have an OpenAI, Gemini, or Anthropic API key, you can add it to `.env`.
- **Note:** If no API key is provided, PackGuard AI runs automatically in **deterministic mode** with rule-based verification, requiring zero external services or costs.

---

## Running the Application

Execution is kept as standard and simple as possible.

### Option 1: Standard Direct Commands (Recommended)

Open two terminal windows:

#### Terminal 1 — Backend (FastAPI)
```bash
cd backend
python -m uvicorn app.main:app --reload
```
The backend will start at: **`http://127.0.0.1:8000`**

#### Terminal 2 — Frontend (Vite + React)
```bash
cd frontend
npm run dev
```
The frontend will start at: **`http://localhost:5173`**

---

### Option 2: From the Root Directory via npm

You can also run both commands directly from the root project folder:

#### Terminal 1 (Backend):
```bash
npm run backend
```

#### Terminal 2 (Frontend):
```bash
npm run dev
```

Then open your browser at **[http://localhost:5173](http://localhost:5173)**.

---

## Step-by-Step Usage Guide

### 1. Home Screen
When you launch PackGuard AI, you see two choices:
- **Analyse Existing Product**: Browse previously saved products and their historical analyses.
- **Analyse New Product**: Set up a new product verification.

### 2. Analysing a New Product
1. Click **Analyse New Product**.
2. Enter the **Product Name** (e.g. `Nature Valley Granola`).
3. Click the Excel upload area and select one or more `.xlsx` or `.xls` specification files.
4. Click the PDF upload area and select exactly **one** packaging artwork `.pdf`.
5. Click **Analyse Documents**.
   - If the specification files contain contradictory product information (e.g., File A specifies 500g and File B specifies 400g), analysis is stopped, showing a clear contradiction table detailing the exact files, sheets, and cells.
   - If validation succeeds, the analysis is performed and you are taken to the **Analysis Results Page**.

### 3. Reviewing Findings & Previews
- **Summary Metrics**: View total Mismatches, Items Needing Review, Matches, and Not Checked.
- **Interactive Highlighting**: Click any finding card in the list. The **Artwork Preview** updates and draws an outline marker directly over the extracted location in the PDF.
- **Specification Matrix**: The **Specification Preview** displays the exact sheet, target cell, and adjacent rows/columns from the Excel file.
- **Details Inspection**: Click the **Details** button on any finding to inspect all underlying evidence, values, and coordinates.

### 4. Applying Safe PDF Corrections
1. For any mismatch where safe correction is possible, the **Fix** button is enabled.
2. Clicking **Fix** displays a candidate preview of the modified PDF page.
3. Click **Undo Candidate (Discard)** to cancel without changing anything.
4. Click **Save & Commit Version** to accept the correction:
   - A new immutable version (`v1`, `v2`, etc.) is recorded.
   - The original uploaded PDF is strictly preserved.
   - The finding status updates to **Match** with verification evidence.

### 5. Exporting Findings & Sharing
- **CSV Export**: Click the **CSV Export** button at the top right to download a CSV report with formula-injection escaping and full evidence columns.
- **Email Report**: Click **Email Report**, enter the recipient's email address, and click **Open Draft in Default Email App**. This generates a concise report and launches your default email client with a pre-filled draft.

### 6. Managing Historical Analyses
- Go to **Analyse Existing Product** to view products.
- Click any product to view all historical analyses.
- Consecutive analyses automatically highlight resolved issues, persistent issues, and newly detected items.
- Products or individual historical analyses can be deleted with a confirmation prompt.

---

## Running Verification Tests

To verify that all backend modules, parsers, safe fixes, and data models are functioning properly, run from the `backend` directory:
```bash
cd backend
python -m app.test_engine
```
Expected output:
```
--- 1. Testing Clean Empty Catalog ---
Initial products count: 0 (Expected: 0)
--- 2. Testing Specification Contradiction Detector ---
Conflicts detected: 1
--- 3. Testing PDF Parser ---
Extracted 4 text spans across 1 page(s)
--- 4. Testing Bidirectional Analysis Engine ---
Total findings: 7
--- 5. Testing Safe PDF Fix Workflow ---
Candidate fix generated: Candidate correction generated successfully.
Committed new version: v1_...
Original PDF verified untouched!
Corrected version contains verified '500g' replacement!
--- 6. Testing CSV Exporter with Formula Injection Escaping ---
CSV export formula protection verified successfully!
--- 7. Testing Email Report Builder ---
Email report draft built with verified structure and mailto link!
--- 8. Testing History Comparator ---
History comparison: Resolved=1, Persistent=2, New=0
ALL BACKEND ENGINE TESTS PASSED!
```
