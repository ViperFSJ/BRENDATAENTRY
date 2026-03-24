# Live equipment trial — prep when client & class are TBD

Use this when you **don’t know** the customer or equipment type until you’re on site. The app can still run: you pick the **template class** from the dropdown at the last second, and you type or paste everything else as the dialogs appear.

---

## The night before (or morning of)

1. **Machine check**
   - Laptop charged; bring power adapter.
   - Confirm **Python 3.9+** and that the desktop UI starts:
     ```bash
     cd /path/to/BrenDataEntry
     python3 scripts/run_desktop_intake.py
     ```
   - On Windows use `py -3` if `python3` is missing.

2. **Repo / folder**
   - Use a **fresh clone or copy** of the project so `Templates/` and `samples/` are present.
   - Optional: run one dry run with the sample JSON to confirm outputs appear under `desktop_output/`.

3. **“Unknown equipment” mode**
   - For a **fully manual** walkthrough (no OCR values), use the empty extraction file:
     - Path: `samples/live_trial_manual_extraction.json`
   - In the desktop UI: set **Extraction JSON** to that file (Browse…), or launch:
     ```bash
     python3 scripts/run_desktop_intake.py \
       --extraction-json samples/live_trial_manual_extraction.json \
       --force-new-equipment
     ```
   - You will get **more prompts** (client, unit ID, serial, manufacturer, model, equipment type, basket fields, etc.) — that is expected and good for a live demo.

4. **RAEQ pool**
   - Default seed range is fine for a demo. If you’ve burned through numbers testing, widen the range once:
     ```bash
     python3 scripts/run_desktop_intake.py --seed-raeq-spec "57000-57999"
     ```
   - Or delete the local SQLite file (`nde_desktop.sqlite` by default) for a clean numbering story (only if you don’t need old trial data).

5. **Photos (optional)**
   - If you’ll embed photos into the checklist, have **image files on disk** (phone transfer or camera card). Use **Add photos…** in the desktop UI before **Run inspection**.

6. **Class choice on the day**
   - **Pick the closest matching folder** in the **Equipment class** dropdown (e.g. Telescopic Boom Lift, Mobile Crane, **General** if nothing fits).
   - **General** uses a generic checklist manifest — fine for “we’re not sure yet” as long as you explain it’s a catch-all template.

7. **Cheat sheet to keep visible**
   - Job number, location, province (2 letters), LSD format you use on forms.
   - Reminder: inspection type is **Visual/MPI** in the pipeline; RR items will ask for **Status** if a callback is used (desktop does).

---

## On site (when client & equipment are known)

1. Open the desktop UI (`run_desktop_intake.py`).
2. Set **Inspection date** / **Expiry date** to real values.
3. **Equipment class** → choose from dropdown (no typing).
4. **Extraction JSON** → `live_trial_manual_extraction.json` until/unless you have a real OCR JSON from your capture pipeline.
5. **Run inspection** → answer prompts calmly; say out loud what you’re entering so observers follow.
6. Show outputs: `desktop_output/<Class>/<RAEQ>/` — checklist + certificate `.docx`.

---

## If something goes wrong

| Symptom | Quick fix |
|--------|-----------|
| `No module named 'tkinter'` | Install Python from python.org (includes Tk), or on Linux `sudo apt install python3-tk`. |
| Wrong class picked | Close, reopen, pick another class — use `--force-new-equipment` so RAEQ assignment isn’t confused by an earlier match attempt. |
| Too many prompts | Expected with empty JSON; pre-fill a JSON tomorrow morning if you get plate photos + OCR overnight. |
| No network | OK — app is offline; SQLite + local files only. |

---

## Optional: tomorrow morning with 10 minutes of data

If you can snap **data plate photos** and run your OCR export before the meeting, replace the empty JSON path with that file — fewer prompts, faster demo, same flow.
