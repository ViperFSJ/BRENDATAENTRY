#!/usr/bin/env python3
"""
Offline-first desktop entry: Tkinter UI wrapping SessionService + photo-first pipeline.

Does not modify CLI behavior of scripts/run_intake_demo.py.
"""
from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.photo_extraction import ExtractedField, ExtractionResult
from nde_app.raeq_assign import add_available_raeqs
from nde_app.template_paths import list_equipment_class_names
from nde_app.ui_service import SessionService, UIInspectionRequest


def _load_extraction_json(path: Path) -> ExtractionResult:
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields: Dict[str, ExtractedField] = {}
    for k, v in raw.get("fields", {}).items():
        fields[k] = ExtractedField(
            value=str(v.get("value", "")),
            confidence=float(v.get("confidence", 0.0)),
            source_photo_type=str(v.get("source_photo_type", "unknown")),
        )
    return ExtractionResult(fields=fields)


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


def main() -> None:
    ap = argparse.ArgumentParser(description="NDE technician intake (desktop / Tkinter).")
    ap.add_argument("--db-path", default=str(REPO_ROOT / "nde_desktop.sqlite"))
    ap.add_argument("--templates-root", default=str(REPO_ROOT / "Templates"))
    ap.add_argument("--output-root", default=str(REPO_ROOT / "desktop_output"))
    ap.add_argument(
        "--extraction-json",
        default=str(REPO_ROOT / "samples" / "telescopic_boom_lift_extraction.json"),
    )
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
    ttk.Entry(frm, textvariable=insp_var, width=50).grid(row=1, column=1, sticky="ew", pady=2)

    ttk.Label(frm, text="Expiry date").grid(row=2, column=0, sticky="w", pady=2)
    exp_var = tk.StringVar(value="August 28, 2026")
    ttk.Entry(frm, textvariable=exp_var, width=50).grid(row=2, column=1, sticky="ew", pady=2)

    ttk.Label(frm, text="Extraction JSON").grid(row=3, column=0, sticky="w", pady=2)
    json_var = tk.StringVar(value=args.extraction_json)

    def browse_json() -> None:
        p = filedialog.askopenfilename(
            parent=root,
            title="Select extraction JSON",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if p:
            json_var.set(p)

    json_row = ttk.Frame(frm)
    json_row.grid(row=3, column=1, sticky="ew", pady=2)
    ttk.Entry(json_row, textvariable=json_var, width=40).pack(side="left", fill="x", expand=True)
    ttk.Button(json_row, text="Browse…", command=browse_json).pack(side="left", padx=(6, 0))

    ttk.Label(frm, text="Photo paths (optional)").grid(row=4, column=0, sticky="nw", pady=2)
    photo_list = tk.Listbox(frm, height=4, width=50)
    photo_list.grid(row=4, column=1, sticky="ew", pady=2)

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
    ph_btns.grid(row=5, column=1, sticky="w")
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
        jpath = Path(json_var.get().strip())
        if not jpath.is_file():
            messagebox.showerror("Invalid file", f"Extraction JSON not found:\n{jpath}", parent=root)
            return

        try:
            extraction = _load_extraction_json(jpath)
        except Exception as exc:
            messagebox.showerror("JSON error", str(exc), parent=root)
            return

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

        photos = [photo_list.get(i) for i in range(photo_list.size())]

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
