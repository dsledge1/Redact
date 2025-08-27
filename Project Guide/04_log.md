# Project Log

⚠️ **Rules for this file:**
- Append-only. Do not delete or rewrite past entries.  
- Each entry must have:
  1. A date  
  2. A short title  
  3. A brief description (1–3 sentences) of what was done or decided  
  4. Optional cross-references (ToDo IDs, Known Issues, commits, etc.)

---

## Example Entries

### [2025-08-25] Project Guidelines Established
- Created `Project_Guidelines/` folder with Overview, Conventions, ToDo, Log, and Known Issues files.  
- Goal: provide persistent memory and guardrails for future development.  
- Cross-ref: TODO-000 (Guidelines setup).  

---

### [2025-08-26] State Management Decision
- Initially attempted React Context for global state, caused excessive prop drilling.  
- Adopted Zustand as global state manager.  
- Added to Conventions and Known Issues.  
- Cross-ref: TODO-001 (Login Form), ISSUE-001 (State Management Reintroduction).  