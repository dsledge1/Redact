# 02_Conventions.md

⚠️ **This file defines project-wide conventions.**

- Once a convention is adopted here, it should not be changed.
- New conventions may be added when the project reaches decision points.
- This document is append-only: do not delete or rewrite existing entries. Comment out old lines if they are superseded.

---

## 1. General Coding Rules

- Use **English** for all identifiers, comments, and documentation.
- No commented-out code should be left in source files (remove unused code).
- Use TODO: comments for work-in-progress items, with initials + date.
- Keep functions small and focused (≤ 30 lines where possible).

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

```import os
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
- No use of any (unless commented justification given).
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

- Semantic tags (<header>, <main>, <section>, <footer>).
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
```

### Testing

- Python: pytest, all tests under backend/app/tests/.
- TypeScript: Jest (or Vitest), colocated in __tests__/.
- All new features require tests.

### Logging

- Backend: use logging module, no bare print().
- Frontend: console logging only for debugging; remove before commit.

## 7. Comments

Comments explain why, not what.

Example:

```# Using regex here because input format is inconsistent across sources.
pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
```

## 8. Decision Log (Append-only)

- [2025-08-25] Adopted Black + Ruff for Python formatting and linting.
- [2025-08-25] Strict TypeScript enabled, functional components only.
- [2025-08-25] Directory layout fixed as shown above.

## 9. Known Issues (Append-only)

- [ ]