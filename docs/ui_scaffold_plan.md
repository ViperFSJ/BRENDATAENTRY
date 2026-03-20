# NDE Desktop UI Scaffold Plan (Offline-First)

## Goal
Add a thin desktop UI layer that wraps the existing Python pipeline callbacks, without breaking current CLI behavior.

## Constraints Kept
- Existing CLI scripts remain valid and unchanged in behavior.
- Core orchestration remains in `nde_app/session_pipeline.py`.
- SQLite stays local/offline and remains source of truth.

## Thin Architecture
- `nde_app/ui_service.py` provides a minimal service facade:
  - `UIInspectionRequest` for UI payload shape.
  - `SessionService.run_with_callbacks(...)` to bridge UI callbacks to `run_photo_first_session(...)`.
- UI framework: Tkinter (stdlib) — launcher: `python3 scripts/run_desktop_intake.py` (optional flags mirror demo: `--db-path`, `--force-new-equipment`, `--extraction-json`, photo browse, etc.).

## Desktop Callback Contracts
- `confirm_existing_callback(candidate) -> bool`
  - UI renders candidate details + yes/no confirmation.
- `resolve_missing_field_callback(field_name, prompt) -> str`
  - UI prompts user only for required fallbacks.
- `checklist_results_provider(rows) -> Dict[str, str]`
  - UI checklist screen returns `OK/RR/N/A` map keyed by `label_slug`.

## Class selection (avoid typos)

- **Always use a dropdown** (or searchable list) populated from the filesystem — **never** a free-text class field for routine intake.
- The Tk scaffold already does this: `ttk.Combobox(..., values=class_names, state="readonly")` fed by `nde_app.template_paths.list_equipment_class_names(templates_root)` (sorted; includes `General` when templates are present).
- Any future UI (Electron, web local, etc.) should call the same helper or an equivalent scan so labels match folder names exactly.

## Initial Screen Flow
1. Start session (**class from dropdown**, dates, photos ready).
2. Existing equipment confirmation modal (if candidate match found).
3. Missing field prompts (job/location/province/lsd and OCR fallbacks).
4. Client reference branch:
   - same as Unit ID? default yes on blank.
   - if no, prompt client reference; blank => "-".
5. Checklist capture screen (RR should trigger status prompt path).
6. Completion screen with output file paths.

## Release Candidate Path
- Phase 1: **Done** — Tk scaffold (`scripts/run_desktop_intake.py`) delegates to `SessionService` + pipeline callbacks (`messagebox` / `simpledialog` for prompts).
- Phase 2: Add local session history browser from SQLite.
- Phase 3: Package for offline desktop deployment.
