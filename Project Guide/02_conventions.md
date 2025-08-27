# 02_Conventions.md

⚠️ **This file defines project-wide conventions.**

- Once a convention is adopted here, it should not be changed.
- New conventions may be added when the project reaches decision points - ASK ME.
- This document is append-only: do not delete or rewrite existing entries. Comment out old lines if they are superseded.

---

## 1. General Coding Rules

- Use **English** for all identifiers, comments, and documentation.
- No commented-out code should be left in source files (remove unused code).
- Use TODO: comments for work-in-progress items, with initials + date.
- Keep functions small and focused (≤ 30 lines where possible).
- Limit interdependencies, functional code where possible to minimize side effects.
- Write unit tests as you write functions. All critical functions must have unit tets, aim for >= 80% coverage.
- Add comments to explain the logic behind your code and what you are accomplishing with it.

---

## 2. Python (Backend / Django)

### Style

- Follow **PEP 8**.  
- Auto-format with **Black** (`line length = 100`).  
- Lint with **Ruff** or `flake8`.

### Typing & Documentation

- Type hints required for all public functions.
- Docstrings in **Google style** for all classes and functions.  
  Example:

  ```python
  def process_file(path: str) -> str:
      """
      Reads a file, processes it, and returns the result.

      Args:
          path (str): Path to the file.

      Returns:
          str: Processed output.
      """
  ```

### Imports

- Group order: stdlib → third-party → local.
- Example:

```
import os
import requests

from app.services.file_parser import parse_file
```

### Django-Specific

- Views: keep thin, delegate logic to services/ or utils/.
- Models: always implement __str__ and Meta: ordering = [].
- Templates: minimal logic, no complex transformations.

## 3. TypeScript (Frontend / Services)

### Style

- Strict mode ON ("strict": true).
- No use of "any" (unless commented justification given).
- Use camelCase for variables, PascalCase for components and types.

### Components

- Functional components only (no class components).
- Example:

```type ButtonProps = {
  label: string;
  onClick: () => void;
};

export function Button({ label, onClick }: ButtonProps) {
  return <button onClick={onClick}>{label}</button>;
}
```

### API Calls

- All API requests go through /src/services/.
- No direct fetch calls inside components.
- Always handle errors and return typed results.

## 4. HTML/Templates

- Semantic tags:
 ```(<header>, <main>, <section>, <footer>).
 ```
- Accessibility required: alt attributes on images, aria- labels where needed.
- Template inheritance required ({% extends "base.html" %}).

## 5. CSS

- Prefer utility-first classes (Tailwind if available).
- Otherwise, use BEM naming: .block__element--modifier.
- No inline styles except debugging.
- CSS should be scoped per component or feature.

## 6. Project-Wide Structure

### Directory Layout

```project_root/
  backend/
    manage.py
    app/
      models.py
      views.py
      services/
      templates/
      tests/
  frontend/
    src/
      components/
      services/
      styles/
      __tests__/
  Project_Guide/
    01_project_overview.md
    02_conventions.md
    03_todo.md
    04_log.md
    05_known_issues.md
  test_documents/
```

### Testing

- Python: pytest, all tests under backend/app/tests/.
- TypeScript: Jest (or Vitest), colocated in __tests__/.
- All new features require tests.
- Functional tests to be performed on files added to test_documents/
- Test real-world scenarios such as:
  - Corrupted files
  - Password-protected PDFs
  - Very large files
- Performance benchmarking:
  - Should process 100 page PDF in < 30 seconds
- Security tests, watching for injections for example

### Logging

- Backend: use logging module, no bare print().
- Frontend: console logging only for debugging; remove before commit.
- Log levels: DEBUG for dev, INFO for key actions, WARNING for recoverable issues, ERROR/CRITICAL for failures.

### Frontend Conventions
- All components must live in /components/ with one file per component.
- Shared utility functions go in /utils/.
- No inline event handlers (onClick={() => ...}) except for trivial cases.

## 7. Comments

Comments explain why, not what.

Example:

```# Using regex here because input format is inconsistent across sources.
pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
```

## 8. Log (Append-only)

Log all decisions and actions taken in Project_Guide/04_log.md. Never delete, only append new lines to the end. 
- Append-only. Do not delete or rewrite past entries.  
- Each entry must have:
  1. A date  
  2. A short title  
  3. A brief description (1–3 sentences) of what was done or decided  
  4. Optional cross-references (ToDo IDs, Known Issues, commits, etc.)

### Purpose of Log
- Provides a **chronological narrative** of the project’s progression.  
- Helps onboard new contributors (human or AI).  
- Prevents “forgotten history” — why decisions were made, and when.  
- Works alongside the ToDo and Known Issues logs for full traceability.  

Example:
### [2025-08-25] Project Guide Established
- Created `Project_Guide/` folder with Overview, Conventions, ToDo, Log, and Known Issues files.  
- Goal: provide persistent memory and guardrails for future development.  
- Cross-ref: TODO-000 (Guidelines setup).  

---

### [2025-08-26] State Management Decision
- Initially attempted React Context for global state, caused excessive prop drilling.  
- Adopted Zustand as global state manager.  
- Added to Conventions and Known Issues.  
- Cross-ref: TODO-001 (Login Form), ISSUE-001 (State Management Reintroduction).  

### Format for Future Entries

### [YYYY-MM-DD] Short Title
Brief description of what was done or decided (1–3 sentences).
Cross-ref: TODO-XXX, ISSUE-XXX, commit hash, or related doc updates.

## 9. Known Issues (Append-only)

Add all known issues and bugs to Project_Guide/05_known_issues.md as you find them. Do not delete issues, but you may edit the attempted fixes and status if the status changes. 

### Format

Use the following format for issues:

### ISSUE-XXX: Short Title

- **Date:** YYYY-MM-DD
- **Description:** Concise explanation of the bug, limitation, or failed approach.
- **Attempted Fixes:** Brief summary of what was tried (and dates, if known).
- **Status:** Open | Mitigated | Resolved (YYYY-MM-DD) | Won’t Fix

### Status Definitions

- **Open** → Active issue that still needs investigation or resolution.  
- **Mitigated** → Temporary workaround in place, but not fully resolved.  
- **Resolved** → Issue is fixed and confirmed (include resolution date).  
- **Won’t Fix** → Issue acknowledged but intentionally left unresolved (document why).  

## 10. TODO List (Append-only)

All planned future tasks should be added to the TODO list in Project_Guide/03_todo.md. Do this for tasks laid out at project inception and any new tasks that come up through the course of development. 

- Append-only. Do not delete or remove lines.  
- If a task changes, **comment out** the old line (prefix with `~~` for strikethrough in Markdown) and add a new one beneath it with the updated info.  
- Each task must have:
  1. A unique ID (TODO-001, TODO-002, …)  
  2. A date added  
  3. A short description  
  4. Optional tags (e.g., [backend], [frontend], [bug], [feature])  
  5. A status (Planned, In Progress, Blocked, Done, Abandoned)

---

### Current Tasks

- **TODO-000 (2025-08-25)** [example] Setup project guidelines structure.  
  - **Status:** Done (2025-08-25)  

---

### Format for Future Tasks

- **TODO-XXX (YYYY-MM-DD)** [tags] Short task description.
  - **Status:** Planned | In Progress | Blocked | Done (YYYY-MM-DD) | Abandoned (YYYY-MM-DD, reason)

---

### Status Definitions
- **Planned** → Task has been identified but not started.  
- **In Progress** → Work is actively being done.  
- **Blocked** → Cannot proceed due to dependency, bug, or external factor.  
- **Done** → Completed and merged/verified (include completion date).  
- **Abandoned** → No longer relevant or intentionally discarded (include reason + date).  

---

### Example Task Progression

- ~~**TODO-001 (2025-08-26)** [frontend, auth] Build login form using Context API.~~  
  - **Status:** Abandoned (2025-08-26, switched to Zustand for state management)  

- **TODO-001 (2025-08-26)** [frontend, auth] Build login form using Zustand for state.  
  - **Status:** In Progress  

---

## 11. Security Conventions

- Always use Django's CSRF protection
- Never log or persist user-uploaded file contents
- Validate and sanitize all file inputs

## 12. Error Handling

### Error Response Structure

**Backend Error Format:**
```python
class APIError(Exception):
    def __init__(self, message: str, code: str, status: int, details: dict = None):
        self.message = message
        self.code = code  # e.g., "PDF_CORRUPT", "OCR_FAILED"
        self.status = status
        self.details = details or {}

# Response format
{
    "error": {
        "message": "Unable to process PDF file",  # User-facing
        "code": "PDF_CORRUPT",                    # For frontend handling
        "details": {                              # Debug info (dev only)
            "page": 5,
            "reason": "Invalid xref table"
        }
    },
    "request_id": "req_abc123"  # For log correlation
}
```

### Error Categories & Responses

```
# Define in errors.py
ERROR_MAPPINGS = {
    # File errors
    "FILE_TOO_LARGE": (413, "File exceeds 100MB limit"),
    "INVALID_PDF": (400, "File is not a valid PDF"),
    "PDF_ENCRYPTED": (400, "Password-protected PDFs are not supported"),
    
    # Processing errors  
    "OCR_FAILED": (500, "Unable to read text from image"),
    "TIMEOUT": (504, "Processing took too long, please try a smaller file"),
    "FUZZY_MATCH_FAILED": (500, "Text matching encountered an error"),
    
    # User errors
    "NO_MATCHES_FOUND": (404, "No text matching your criteria was found"),
    "INVALID_REGEX": (400, "The pattern you entered is invalid"),
}
```

### Logging Format

```
import structlog

logger = structlog.get_logger()

# Log with context
logger.error(
    "pdf_processing_failed",
    request_id=request_id,
    session_id=session_id,
    error_code="PDF_CORRUPT",
    file_size=file_size,
    page_count=page_count,
    exc_info=True  # Include stack trace
)

# Output format (JSON for production, pretty for dev):
{
    "timestamp": "2025-01-15T10:30:45Z",
    "level": "error",
    "event": "pdf_processing_failed",
    "request_id": "req_abc123",
    "session_id": "sess_xyz789",
    "error_code": "PDF_CORRUPT",
    "file_size": 5242880,
    "page_count": 42,
    "exception": "PyPDF2.errors.PdfReadError: Invalid xref table"
}
```

## 13. API Structure

/api/redact/ - POST, accepts PDF + redaction params
/api/split/ - POST, accepts PDF + split instructions
/api/merge/ - POST, accepts multiple PDFs
/api/extract/ - POST, accepts PDF + extraction type

## 14. Frontend State Management (Zustand)

```markdown
### State Management Architecture

**Global State (Zustand) vs Local State (useState)**

**Goes in Global State:**
- User session/auth info
- Current PDF document metadata
- Processing status across pages
- Redaction settings and matches
- Error notifications

**Stays in Component State:**
- Form inputs before submission
- UI toggles (dropdown open/closed)
- Temporary hover states
- Page-specific view settings

**Zustand Store Structure:**
```typescript
interface PDFStore {
  // Document state
  document: {
    id: string | null;
    fileName: string;
    pageCount: number;
    fileSize: number;
    uploadedAt: Date | null;
  };
  
  // Processing state
  processing: {
    status: 'idle' | 'uploading' | 'processing' | 'ready' | 'error';
    progress: number;  // 0-100
    currentStep: string;  // "Extracting text...", "Running OCR..."
    errors: Array<{code: string; message: string}>;
  };
  
  // Redaction state
  redactions: {
    searchTerms: string[];
    fuzzyThreshold: number;  // 0.0-1.0
    matches: Array<{
      id: string;
      text: string;
      page: number;
      confidence: number;
      approved: boolean | null;  // null = pending review
      bounds: {x: number; y: number; w: number; h: number};
    }>;
    manualRedactions: Array<{
      page: number;
      bounds: {x: number; y: number; w: number; h: number};
    }>;
  };
  
  // Actions
  actions: {
    uploadFile: (file: File) => Promise<void>;
    approveMatch: (matchId: string) => void;
    rejectMatch: (matchId: string) => void;
    addManualRedaction: (page: number, bounds: Bounds) => void;
    finalizeRedactions: () => Promise<{downloadUrl: string}>;
    reset: () => void;
  };
}

// Create store
const usePDFStore = create<PDFStore>((set, get) => ({
  document: { id: null, fileName: '', pageCount: 0, fileSize: 0, uploadedAt: null },
  processing: { status: 'idle', progress: 0, currentStep: '', errors: [] },
  redactions: { searchTerms: [], fuzzyThreshold: 0.8, matches: [], manualRedactions: [] },
  
  actions: {
    uploadFile: async (file) => {
      set({ processing: { status: 'uploading', progress: 0, currentStep: 'Uploading file...', errors: [] }});
      
      // Upload logic with progress updates
      const xhr = new XMLHttpRequest();
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          set({ processing: { ...get().processing, progress: (e.loaded / e.total) * 50 }});
        }
      };
      // ... rest of upload
    },
    // ... other actions
  }
}));
```

### Upload Progress Handling

```
// Component using the store
function UploadProgress() {
  const { status, progress, currentStep } = usePDFStore(s => s.processing);
  
  if (status === 'idle') return null;
  
  return (
    <div className="upload-progress">
      <div className="progress-bar">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <p>{currentStep}</p>
      {status === 'error' && <ErrorDisplay />}
    </div>
  );
}

// Separate concerns: UI state stays local
function PDFViewer() {
  const [zoom, setZoom] = useState(1.0);  // Local: view-only
  const [currentPage, setCurrentPage] = useState(1);  // Local: navigation
  const matches = usePDFStore(s => s.redactions.matches);  // Global: shared data
  
  // ...
}
```