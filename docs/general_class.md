# `General` equipment class (catch-all)

## Purpose

Use **`General`** when equipment does not map cleanly to a specific template class (e.g. custom or rare units). It uses:

- `Templates/General/Checklist - General BM1_Lbfgf9.docx` (checklist; `.docx` not `.dotx`)
- `Templates/General/EC-1210D*.dotx` (certificate)
- `Templates/General/Checklist*.xml` (export for tooling)

## Blank checklist rows

The General checklist Word file has **empty Item / Type of Inspection cells** in the table body (results/comments placeholders only). Because of that:

1. **LABELSLUG extraction from XML** returns no item labels.
2. The app loads **`Templates/General/checklist_manifest.json`**, an ordered list of line labels whose **length must match** the number of checklist data rows in the `.docx` (currently 25).
3. **Filling results** uses **row order** (not label text matching) for `General` only.

Edit `checklist_manifest.json` if you need different wording; keep the same number of entries as table rows.

## What if the tech types a class that does not exist?

There is **no fuzzy match**: `class_name` must match a folder name under `Templates/` exactly (e.g. `Telescopic Boom Lift`).

Typical failures:

| Situation | Error |
|-----------|--------|
| Folder missing | `FileNotFoundError: Class template directory not found: Templates/<name>` |
| No `Checklist*.xml` | `FileNotFoundError: No Checklist*.xml found in ...` |
| No checklist template | `FileNotFoundError: No checklist template (Checklist*.dotx or Checklist*.docx) ...` |
| No certificate | `FileNotFoundError: No EC-1210D*.dotx certificate template ...` |

Use **`General`** (or add a new folder under `Templates/` with full checklist + certificate + XML).
