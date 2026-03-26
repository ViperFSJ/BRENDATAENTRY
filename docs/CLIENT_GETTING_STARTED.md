# Getting started — download and trial (client copy)

You need **Python 3.9 or newer** on a computer with a **normal desktop** (Windows, Mac, or Linux with a screen). An internet connection is only required **once**, to download the project.

---

## Step 1 — Get the files

Your contact will send a **GitHub repository link** (or a **ZIP** of the same project).

### Option A: Download ZIP (simplest if you do not use Git)

1. Open the GitHub link in a browser.
2. Click the green **Code** button → **Download ZIP**.
3. Unzip the folder somewhere easy to find (e.g. Desktop).
4. The folder you open in the next steps must contain **`nde_app`**, **`scripts`**, **`Templates`**, and **`samples`** inside it.

### Option B: Clone with Git (if you already use Git)

```bash
git clone https://github.com/OWNER/REPO.git
cd REPO
```

Use the exact URL your contact provides.

---

## Step 2 — Install Python (if needed)

1. Download Python from **https://www.python.org/downloads/** and install.
2. During setup on **Windows**, check **“Add Python to PATH”** if offered.
3. Verify in a terminal:

   **Windows (Command Prompt or PowerShell)**

   ```text
   py -3 --version
   ```

   **Mac / Linux**

   ```text
   python3 --version
   ```

You should see **3.9** or higher.

---

## Step 3 — Open a terminal in the project folder

- **Windows:** Shift+right-click the project folder → “Open in Terminal” or open Command Prompt and `cd` into the folder that contains `scripts` and `nde_app`.
- **Mac:** Terminal → `cd` and drag the project folder into the window to paste the path.
- **Linux:** Same as Mac.

Confirm you are in the right place: the folder should **contain** `scripts\run_desktop_intake.py` (Windows) or `scripts/run_desktop_intake.py` (Mac/Linux).

---

## Step 4 — Run the desktop trial app

**Windows**

```text
py -3 scripts\run_desktop_intake.py --force-new-equipment
```

If that fails, try:

```text
python scripts\run_desktop_intake.py --force-new-equipment
```

**Mac / Linux**

```bash
python3 scripts/run_desktop_intake.py --force-new-equipment
```

A window titled **“NDE Inspection — Desktop Intake”** should open.

---

## Step 5 — What to do in the window

1. Choose **Equipment class** from the **dropdown** (do not type the class name).
2. Set **Inspection date** and **Expiry date** if needed.
3. Optional: **Add photos…** to attach images.
4. If photos are added, the app attempts live extraction from those photos for this session.
5. If live extraction fails, the app falls back to **full manual field entry** prompts.
6. If no photos are added, the app uses **full manual field entry** prompts.
7. Click **Run inspection** and answer the pop-up dialogs (job, location, province, checklist, etc.).
8. When finished, your outputs are under **`desktop_output`** inside the project folder, organized by class and **RAEQ** number.

### Live extraction requirement (optional)

- Live extraction uses local `tesseract` OCR when installed.
- macOS install example: `brew install tesseract`
- If `tesseract` is not installed, the app prompts for manual field entry.

---

## Help and troubleshooting

For more detail (photos, optional settings, error messages):

- **Full trial guide:** [desktop_ui_trial_guide.md](desktop_ui_trial_guide.md) (same folder as this file under `docs/` in the repo).
- **Before a live demo (prep checklist):** [live_demo_prep.md](live_demo_prep.md)

**Common issues**

| Problem | What to try |
|--------|--------------|
| `No module named 'tkinter'` | Reinstall Python from python.org; on Linux install `python3-tk`. |
| `No template classes found` | Unzip/clone again; ensure `Templates` is next to `nde_app`. |
| Window does not open | Run from a machine with a monitor (not SSH-only). |

---

## Support

For repository access, invite issues, or business questions, contact the person who shared this document or the GitHub repo owner.
