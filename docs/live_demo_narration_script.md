# Live demo — 2-minute client narration script

Use this while driving `run_desktop_intake.py`. Paraphrase as needed; pauses marked **[pause]**.

---

## Opening (~20 s)

“Today I’m walking through our **offline inspection intake**: we capture what we know from the unit and photos, assign or confirm an **RAEQ**, fill the **checklist** and **certificate** Word documents, and keep everything in a **local database** on this machine—no cloud required for the run.”

**[Open the app, point at the window.]**

---

## What you’re seeing (~25 s)

“This window is the technician-facing step. I’m picking the **equipment class** from a list so we don’t typo the template. Dates match the inspection we’re doing. This **extraction JSON** is either empty or from our capture pipeline—it drives what we auto-fill versus what we confirm by hand.”

**[If using photos:]**  
“I’m adding **photos** here; they’ll be **embedded into the checklist** in the standard figure slots so the deliverable matches your field package.”

---

## Run the flow (~45 s)

“I’ll start the run. **[Click Run inspection.]**  

You’ll see prompts for things we always treat as **technician-provided** in this workflow—**job number**, **location**, **province**, **LSD**—then we resolve **client vs owner**, unit and serial, and equipment details. If anything was uncertain from OCR, we **confirm** it here instead of guessing.”

**[As dialogs appear, briefly name them without reading every field:]**  
“We’re also handling **client reference** the way your process specifies, and we’ll walk the **checklist**—OK, RR, or N/A—then if anything is RR we capture **status** instead of assuming it.”

---

## Outputs (~20 s)

“When this finishes, we get a **checklist** and **certificate** under a folder keyed by **RAEQ**, plus a log of how many **photos** embedded. **[Point at log / paths.]**  

That’s the handoff package you can review in Word on site.”

---

## Close (~10 s)

“Questions I can answer now: how we’d hook this to your **OCR JSON** tomorrow, how **RAEQ** pool and matching work, or how we’d extend the **class list** as templates evolve.”

---

## Optional one-liners (if asked)

- **“Why dropdown for class?”** — “So the template folder name always matches—no fat-fingered class string.”
- **“What if the unit doesn’t fit a template?”** — “We have a **General** catch-all path; we can show that in a follow-up.”
- **“Is this production-ready?”** — “This is the trial build; we’re validating workflow and documents with you before hardening packaging and deployment.”

---

## Timing tip

If you’re tight on time, **skip** the optional one-liners and keep prompts moving—say “I’m entering standard job/site fields” instead of reading values aloud.
