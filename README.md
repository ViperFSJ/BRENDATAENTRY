# NDE Inspection / RAEQ Data Entry

Offline-first workflow: OCR-style field JSON → technician prompts → filled checklist & certificate Word documents, SQLite persistence, RAEQ assignment.

## Quick trial (desktop UI)

1. Install **Python 3.9+** (with **Tkinter** — included with [python.org](https://www.python.org/downloads/) builds).
2. Clone this repository and open a terminal **in the project root** (folder containing `nde_app` and `scripts`).
3. Run:
   ```bash
   python3 scripts/run_desktop_intake.py
   ```
   On Windows, try `py -3 scripts\run_desktop_intake.py`.

Optional: `--force-new-equipment` for repeated tests without “same equipment?” prompts.

**Full step-by-step for clients:** [docs/desktop_ui_trial_guide.md](docs/desktop_ui_trial_guide.md)

**Live demo before client/class are known:** [docs/live_demo_prep.md](docs/live_demo_prep.md) — use `samples/live_trial_manual_extraction.json` for all-manual prompts.

**What to say during a client demo:** [docs/live_demo_narration_script.md](docs/live_demo_narration_script.md)

## CLI demo (photo-first)

```bash
python3 scripts/run_intake_demo.py --class-name "Telescopic Boom Lift" --inspection-date "August 28, 2025" --expiry-date "August 28, 2026"
```

## Project layout

| Path | Purpose |
|------|--------|
| `nde_app/` | Core pipeline (session, DB, DOCX fill, RAEQ, UI service) |
| `Templates/<class>/` | Checklist + certificate Word templates and XML |
| `samples/` | Example extraction JSON for trials |
| `scripts/` | Desktop UI, demos, tests, validation |

## Dependencies

The main app uses the **Python standard library** only (`sqlite3`, `zipfile`, `xml.etree`, `tkinter` for the desktop UI).

Optional (for `scripts/validate_checklist_examples.py` PDF checks):

```bash
pip install -r requirements.txt
```

## Tests / validation

```bash
python3 scripts/test_business_rules_regression.py
python3 scripts/validate_cross_class_matrix.py
```

## License

Proprietary / internal — set as appropriate for your organization.
