#!/usr/bin/env python3
"""
Offline-first desktop entry: Tkinter UI wrapping SessionService + photo-first pipeline.

Does not modify CLI behavior of scripts/run_intake_demo.py.
"""
from __future__ import annotations

import argparse
import calendar
import sys
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.live_photo_extraction import extract_from_photos
from nde_app.photo_extraction import ExtractionResult
from nde_app.raeq_assign import add_available_raeqs
from nde_app.template_paths import list_equipment_class_names
from nde_app.ui_service import SessionService, UIInspectionRequest, UIStatusChoice


def _parse_index_list(raw: str, n: int) -> List[int]:
    out: List[int] = []
    if not raw.strip():
        return out
    for t in raw.replace(",", " ").split():
        if t.isdigit():
            i = int(t)
            if 0 <= i < n and i not in out:
                out.append(i)
    return out


def _parse_ui_date(raw: str) -> date:
    s = (raw or "").strip()
    fmts = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return date.today()


class DatePickerDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, initial_text: str) -> None:
        super().__init__(parent)
        self.title("Select date")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.result: Optional[str] = None

        initial = _parse_ui_date(initial_text)
        self.year_var = tk.IntVar(value=initial.year)
        self.month_var = tk.IntVar(value=initial.month)
        self.day_var = tk.IntVar(value=initial.day)

        frm = ttk.Frame(self, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm, text="Year").grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Label(frm, text="Month").grid(row=0, column=1, sticky="w", padx=(0, 6))
        ttk.Label(frm, text="Day").grid(row=0, column=2, sticky="w")

        self.year_spin = ttk.Spinbox(frm, from_=2000, to=2100, textvariable=self.year_var, width=8)
        self.year_spin.grid(row=1, column=0, sticky="w", padx=(0, 6))
        self.month_spin = ttk.Spinbox(frm, from_=1, to=12, textvariable=self.month_var, width=6)
        self.month_spin.grid(row=1, column=1, sticky="w", padx=(0, 6))
        self.day_spin = ttk.Spinbox(frm, from_=1, to=31, textvariable=self.day_var, width=6)
        self.day_spin.grid(row=1, column=2, sticky="w")

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=self._on_cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=self._on_ok).pack(side="right", padx=(0, 6))

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())

        self.update_idletasks()
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 20)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 20)
        self.geometry(f"+{x}+{y}")

    def _normalize_day(self) -> int:
        y = int(self.year_var.get())
        m = int(self.month_var.get())
        m = max(1, min(12, m))
        self.month_var.set(m)
        max_day = calendar.monthrange(y, m)[1]
        d = int(self.day_var.get())
        d = max(1, min(max_day, d))
        self.day_var.set(d)
        return d

    def _on_ok(self) -> None:
        d = self._normalize_day()
        y = int(self.year_var.get())
        m = int(self.month_var.get())
        self.result = date(y, m, d).strftime("%B %d, %Y")
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


def _pick_date(parent: tk.Tk, current_value: str) -> Optional[str]:
    dlg = DatePickerDialog(parent, current_value)
    parent.wait_window(dlg)
    return dlg.result


def main() -> None:
    ap = argparse.ArgumentParser(description="NDE technician intake (desktop / Tkinter).")
    ap.add_argument("--db-path", default=str(REPO_ROOT / "nde_desktop.sqlite"))
    ap.add_argument("--templates-root", default=str(REPO_ROOT / "Templates"))
    ap.add_argument("--output-root", default=str(REPO_ROOT / "desktop_output"))
    ap.add_argument("--seed-raeq-spec", default="56400-56420")
    ap.add_argument("--technician-id", default="DEFAULT_TECH")
    ap.add_argument(
        "--force-new-equipment",
        action="store_true",
        help="Skip existing-unit confirmation and always assign from pool",
    )
    ap.add_argument("--history-root", default=None)
    args = ap.parse_args()

    templates_root = Path(args.templates_root)
    class_names = list_equipment_class_names(templates_root)
    if not class_names:
        raise SystemExit(f"No template classes found under {templates_root}")

    root = tk.Tk()
    root.title("NDE Inspection — Desktop Intake")
    root.minsize(520, 380)

    frm = ttk.Frame(root, padding=10)
    frm.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    ttk.Label(frm, text="Equipment class").grid(row=0, column=0, sticky="w", pady=2)
    class_var = tk.StringVar(value=class_names[0])
    class_cb = ttk.Combobox(frm, textvariable=class_var, values=class_names, width=48, state="readonly")
    class_cb.grid(row=0, column=1, sticky="ew", pady=2)

    ttk.Label(frm, text="Inspection date").grid(row=1, column=0, sticky="w", pady=2)
    insp_var = tk.StringVar(value="August 28, 2025")
    insp_row = ttk.Frame(frm)
    insp_row.grid(row=1, column=1, sticky="ew", pady=2)
    ttk.Entry(insp_row, textvariable=insp_var, width=40, state="readonly").pack(side="left", fill="x", expand=True)
    ttk.Button(
        insp_row,
        text="Calendar…",
        command=lambda: (lambda v: insp_var.set(v) if v else None)(_pick_date(root, insp_var.get())),
    ).pack(side="left", padx=(6, 0))

    ttk.Label(frm, text="Expiry date").grid(row=2, column=0, sticky="w", pady=2)
    exp_var = tk.StringVar(value="August 28, 2026")
    exp_row = ttk.Frame(frm)
    exp_row.grid(row=2, column=1, sticky="ew", pady=2)
    ttk.Entry(exp_row, textvariable=exp_var, width=40, state="readonly").pack(side="left", fill="x", expand=True)
    ttk.Button(
        exp_row,
        text="Calendar…",
        command=lambda: (lambda v: exp_var.set(v) if v else None)(_pick_date(root, exp_var.get())),
    ).pack(side="left", padx=(6, 0))

    ttk.Label(frm, text="Photo paths (optional)").grid(row=3, column=0, sticky="nw", pady=2)
    photo_list = tk.Listbox(frm, height=4, width=50)
    photo_list.grid(row=3, column=1, sticky="ew", pady=2)

    def add_photos() -> None:
        paths = filedialog.askopenfilenames(
            parent=root,
            title="Select photos",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp"), ("All", "*.*")],
        )
        for p in paths:
            photo_list.insert(tk.END, p)

    def clear_photos() -> None:
        photo_list.delete(0, tk.END)

    ph_btns = ttk.Frame(frm)
    ph_btns.grid(row=4, column=1, sticky="w")
    ttk.Button(ph_btns, text="Add photos…", command=add_photos).pack(side="left", padx=(0, 6))
    ttk.Button(ph_btns, text="Clear", command=clear_photos).pack(side="left")

    log = tk.Text(frm, height=10, width=60, state="disabled", wrap="word")
    log.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(10, 4))
    frm.rowconfigure(6, weight=1)
    frm.columnconfigure(1, weight=1)

    def log_line(msg: str) -> None:
        log.configure(state="normal")
        log.insert(tk.END, msg + "\n")
        log.see(tk.END)
        log.configure(state="disabled")
        root.update_idletasks()

    def confirm_existing(candidate: Dict[str, str]) -> bool:
        if args.force_new_equipment:
            return False
        msg = (
            f"Possible existing unit:\n\n"
            f"RAEQ: {candidate.get('raeq', '')}\n"
            f"Match: {candidate.get('match_strength', '')}\n"
            f"Unit ID: {candidate.get('client_unit_id', '')}\n"
            f"Serial: {candidate.get('serial_no', '')}\n"
            f"Class: {candidate.get('class_name', '')}\n\n"
            f"Is this the same equipment?"
        )
        return messagebox.askyesno("Confirm equipment", msg, parent=root, default=messagebox.YES)

    def resolve_missing(field_name: str, prompt: str) -> str:
        title = field_name.replace("_", " ").title()
        val = simpledialog.askstring(title, f"{prompt}\n\nField: {field_name}", parent=root)
        return (val or "").strip()

    def choose_status(options: List[UIStatusChoice]) -> str:
        dlg = tk.Toplevel(root)
        dlg.title("Select Status")
        dlg.transient(root)
        dlg.grab_set()
        dlg.resizable(False, False)
        result: Dict[str, str] = {"value": ""}

        frm_status = ttk.Frame(dlg, padding=10)
        frm_status.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frm_status, text="RR items found. Select Status:").grid(row=0, column=0, sticky="w")
        labels = [o.label for o in options]
        default_label = next((o.label for o in options if o.is_default), labels[0] if labels else "")
        selected_var = tk.StringVar(value=default_label)
        cb = ttk.Combobox(frm_status, values=labels, textvariable=selected_var, width=48, state="readonly")
        cb.grid(row=1, column=0, sticky="ew", pady=(6, 0))

        def on_ok() -> None:
            chosen = selected_var.get().strip()
            if not chosen:
                messagebox.showerror("Missing status", "Please choose a status.", parent=dlg)
                return
            result["value"] = chosen
            dlg.destroy()

        def on_cancel() -> None:
            result["value"] = default_label
            dlg.destroy()

        btns = ttk.Frame(frm_status)
        btns.grid(row=2, column=0, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="Cancel", command=on_cancel).pack(side="right")
        ttk.Button(btns, text="OK", command=on_ok).pack(side="right", padx=(0, 6))
        dlg.bind("<Escape>", lambda _e: on_cancel())
        dlg.bind("<Return>", lambda _e: on_ok())
        dlg.wait_window()
        return result["value"]

    def checklist_results_provider(rows):
        lines = "\n".join(f"  [{r.index}] {r.item_label}" for r in rows[:80])
        if len(rows) > 80:
            lines += f"\n  … ({len(rows) - 80} more rows)"
        all_ok = messagebox.askyesno(
            "Checklist",
            f"Are all checklist items OK?\n\n{lines}",
            parent=root,
            default=messagebox.YES,
        )
        if all_ok:
            return {r.label_slug: "OK" for r in rows}

        rr_raw = simpledialog.askstring(
            "Checklist RR",
            "Enter row indexes to mark RR (comma/space separated, blank for none):",
            parent=root,
        ) or ""
        na_raw = simpledialog.askstring(
            "Checklist N/A",
            "Enter row indexes to mark N/A (comma/space separated, blank for none):",
            parent=root,
        ) or ""

        rr = set(_parse_index_list(rr_raw, len(rows)))
        na = set(_parse_index_list(na_raw, len(rows)))
        results: Dict[str, str] = {}
        for r in rows:
            if r.index in na:
                results[r.label_slug] = "N/A"
            elif r.index in rr:
                results[r.label_slug] = "RR"
            else:
                results[r.label_slug] = "OK"
        return results

    def run_session() -> None:
        photos = [photo_list.get(i) for i in range(photo_list.size())]
        extraction: ExtractionResult
        if photos:
            try:
                log_line("Running live photo extraction...")
                extraction = extract_from_photos(photos)
                if not extraction.fields:
                    log_line("OCR returned no usable fields.")
                    log_line("Falling back to full manual field entry.")
                    extraction = ExtractionResult(fields={})
            except Exception as exc:
                log_line(f"Live extraction failed: {exc}")
                log_line("Falling back to full manual field entry.")
                extraction = ExtractionResult(fields={})
        else:
            # No photos provided -> manual data entry only.
            log_line("No photos selected. Using full manual field entry.")
            extraction = ExtractionResult(fields={})

        db_path = Path(args.db_path)
        output_root = Path(args.output_root)
        history_root: Optional[Path] = Path(args.history_root) if args.history_root else None

        init_db(db_path)
        add_available_raeqs(
            db_path,
            technician_id=args.technician_id,
            display_name="Desktop Technician",
            raeq_spec=args.seed_raeq_spec,
        )

        service = SessionService(
            db_path=db_path,
            templates_root=templates_root,
            output_root=output_root,
            history_root=history_root,
        )

        log_line("Starting session…")
        root.config(cursor="watch")
        root.update()

        try:
            result = service.run_with_callbacks(
                request=UIInspectionRequest(
                    class_name=class_var.get().strip(),
                    inspection_date=insp_var.get().strip(),
                    expiry_date=exp_var.get().strip(),
                    extraction_result=extraction,
                    technician_id=args.technician_id,
                    defaults={},
                    photo_paths=photos or None,
                ),
                confirm_existing_callback=confirm_existing,
                resolve_missing_field_callback=resolve_missing,
                checklist_results_provider=checklist_results_provider,
                status_choice_callback=choose_status,
            )
        except Exception as exc:
            root.config(cursor="")
            messagebox.showerror("Session failed", str(exc), parent=root)
            log_line(f"ERROR: {exc}")
            return

        root.config(cursor="")
        log_line(f"RAEQ: {result.raeq}")
        log_line(f"Decision: {result.decision}")
        log_line(f"Checklist: {result.checklist_docx}")
        log_line(f"Certificate: {result.certificate_docx}")
        log_line(f"Photos embedded: {result.inserted_photo_count}")
        messagebox.showinfo(
            "Complete",
            f"Session complete.\n\nRAEQ: {result.raeq}\n\nOutputs written under:\n{output_root}",
            parent=root,
        )

    ttk.Button(frm, text="Run inspection", command=run_session).grid(
        row=7, column=0, columnspan=2, pady=(8, 0)
    )

    root.mainloop()


if __name__ == "__main__":
    main()
