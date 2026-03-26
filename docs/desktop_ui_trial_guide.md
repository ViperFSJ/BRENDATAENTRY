# NDE Desktop UI — Trial guide (for technicians / clients)

This walks through testing the **offline desktop intake** window (`Tkinter`). It uses the same pipeline as the CLI demo but with mouse/keyboard dialogs instead of a terminal.

---

## 1. What you need

| Requirement | Notes |
|-------------|--------|
| **Computer** | macOS, Windows, or Linux with a **graphical desktop** (not SSH-only). |
| **Python 3** | Version **3.9+** recommended. Check: open Terminal / Command Prompt and run `python3 --version` (Mac/Linux) or `py -3 --version` / `python --version` (Windows). |
| **Tkinter** | Usually included with Python from **python.org**. If the app fails with `No module named 'tkinter'`, install it (e.g. Ubuntu: `sudo apt install python3-tk`). |
| **Project folder** | The full **BrenDataEntry** (or your deployment) folder containing `nde_app/`, `Templates/`, and `scripts/`. |

---

## 2. Install / open the project

1. Copy or clone the project to a folder on the machine (e.g. `BrenDataEntry`).
2. Open **Terminal** (Mac/Linux) or **Command Prompt / PowerShell** (Windows).
3. Go to that folder:

   **Mac/Linux**
   ```bash
   cd /path/to/BrenDataEntry
   ```

   **Windows (example)**
   ```cmd
   cd C:\Users\YourName\BrenDataEntry
   ```

---

## 3. Launch the desktop UI

From the **project root** (the folder that contains `scripts` and `nde_app`):

**Mac / Linux**
```bash
python3 scripts/run_desktop_intake.py
```

**Windows** (try one of these if `python3` is not found)
```cmd
py -3 scripts\run_desktop_intake.py
```
or
```cmd
python scripts\run_desktop_intake.py
```

A window titled **“NDE Inspection — Desktop Intake”** should open.

### Optional: trial-friendly command (skip “same equipment?” prompts)

For repeated tests on the same machine, you can force **new** RAEQ assignment every time:

**Mac / Linux**
```bash
python3 scripts/run_desktop_intake.py --force-new-equipment
```

**Windows**
```cmd
py -3 scripts\run_desktop_intake.py --force-new-equipment
```

---

## 4. Step-by-step in the window

1. **Equipment class**  
   Use the **dropdown** (do not type free text). Pick e.g. **Telescopic Boom Lift** or **General**.

2. **Inspection date** / **Expiry date**  
   Use the **Calendar…** buttons and confirm dates.

3. **Photos (optional)**  
   - **Add photos…** to provide current session photos for OCR auto-fill and checklist figures.  
   - **Clear** removes the list.

4. Click **Run inspection**.

5. **Follow the pop-up dialogs** (order may vary slightly based on data):
   - **Existing equipment?** — If the system finds a possible match (unit + serial), you’ll be asked to confirm. Choose **Yes** or **No**.  
     - With `--force-new-equipment`, this step is skipped (always “new”).
   - **Job number**, **Location**, **Province** (2 letters, e.g. `AB`), **LSD** — type answers and click OK (or leave as prompted by the dialog).
   - **Client reference** — You may be asked if client reference is the same as Unit ID; then possibly a reference field.
   - **Checklist** — You’ll be asked if **all items are OK**.  
     - If **No**, you’ll enter row **indexes** (numbers shown in the list) for **RR** and **N/A**, separated by commas or spaces.
  - If any item is **RR**, you will choose **Status** from template options.

7. When finished, a **completion** message shows the **RAEQ** and reminds you where files were written. The main window **log** at the bottom lists paths to the **checklist** and **certificate** `.docx` files.

---

## 5. Where outputs go (defaults)

| Item | Default location (under project folder) |
|------|----------------------------------------|
| SQLite database | `nde_desktop.sqlite` |
| Generated Word files | `desktop_output/<Class Name>/<RAEQ>/` |

Example:
`desktop_output/Telescopic Boom Lift/RAEQ56400/`

You can change locations when launching:

```bash
python3 scripts/run_desktop_intake.py \
  --db-path /path/to/my_trial.sqlite \
  --output-root /path/to/my_outputs
```

---

## 6. OCR/manual behavior

- If photos are provided and OCR succeeds, fields are pre-filled from those photos.
- If OCR fails (or confidence is too low), prompts collect missing fields manually.
- If no photos are provided, the session runs in full manual entry mode.

---

## 7. Troubleshooting

| Problem | What to try |
|---------|-------------|
| `No module named 'tkinter'` | Install Python from python.org, or on Linux install `python3-tk`. |
| Window does not appear | Run from a **local** session with a monitor; remote desktop may need display forwarding. |
| `No template classes found` | Run the command from the **project root**; ensure the `Templates` folder is next to `nde_app`. |
| Wrong Python | Use `python3` on Mac/Linux; on Windows use `py -3` to force Python 3. |
| OCR not available | Install `tesseract` or continue with manual entry prompts. |

---

## 8. Support checklist for your trial

- [ ] Python 3 runs from terminal.  
- [ ] `python3 scripts/run_desktop_intake.py` opens the window.  
- [ ] Completed one full run with either photo OCR or full manual entry.  
- [ ] Located output `.docx` files under `desktop_output/`.  
- [ ] (Optional) Ran with `--force-new-equipment` for a second run without match prompts.  
- [ ] (Optional) Verified manual fallback by running without photos.

---

*For internal reference: implementation lives in `scripts/run_desktop_intake.py` and uses `nde_app.ui_service.SessionService`.*
