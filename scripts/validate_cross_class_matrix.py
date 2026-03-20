import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.checklist_xml import extract_checklist_items_for_class
from nde_app.docx_fill_certificate import fill_certificate_dotx
from nde_app.docx_fill_checklist import fill_checklist_results_in_dotx
from nde_app.template_paths import find_certificate_template, find_checklist_template


def _docx_contains(docx_path: Path, text: str) -> bool:
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_name = next(n for n in z.namelist() if n.endswith("word/document.xml"))
        doc = z.read(doc_name).decode("utf-8", "ignore")
    return text in doc


def _valid_class_dirs(templates_root: Path) -> List[Path]:
    """Directories with checklist + certificate dotx and matching xml (for slug extraction)."""
    out: List[Path] = []
    for class_dir in sorted(p for p in templates_root.iterdir() if p.is_dir()):
        has_checklist = bool(
            list(class_dir.glob("Checklist*.dotx")) + list(class_dir.glob("Checklist*.docx"))
        )
        has_cert = any(class_dir.glob("EC-1210D*.dotx"))
        has_checklist_xml = any(class_dir.glob("Checklist*.xml"))
        has_cert_xml = any(class_dir.glob("EC-1210D*.xml"))
        if has_checklist and has_cert and has_checklist_xml and has_cert_xml:
            out.append(class_dir)
    return out


def _class_summaries(
    templates_root: Path,
    out_root: Path,
    *,
    limit: Optional[int],
) -> Tuple[List[Dict[str, Any]], List[Tuple[str, str]]]:
    class_dirs = _valid_class_dirs(templates_root)
    if limit is not None:
        class_dirs = class_dirs[:limit]

    matrix_rows: List[Dict[str, Any]] = []
    failures: List[Tuple[str, str]] = []

    for class_dir in class_dirs:
        class_name = class_dir.name
        safe = class_name.replace(" ", "_")
        class_out = out_root / safe
        class_out.mkdir(parents=True, exist_ok=True)
        row: Dict[str, Any] = {
            "class_name": class_name,
            "status": "FAIL",
            "row_count": None,
            "checklist_docx": None,
            "certificate_docx": None,
            "error": None,
        }

        try:
            checklist_template = find_checklist_template(class_dir)
            cert_template = find_certificate_template(class_dir)

            rows = extract_checklist_items_for_class(templates_root, class_name)
            if not rows:
                raise ValueError("No checklist rows extracted.")
            row["row_count"] = len(rows)

            checklist_results = {r.label_slug: "OK" for r in rows}
            checklist_results[rows[0].label_slug] = "RR"

            checklist_out = class_out / "matrix_checklist.docx"
            cert_out = class_out / "matrix_certificate.docx"

            fill_checklist_results_in_dotx(
                checklist_template,
                checklist_out,
                templates_root,
                class_name,
                checklist_results,
                fields={
                    "client_name": "Matrix Client",
                    "owner_name": "Matrix Owner",
                    "raeq": "RAEQ59999",
                    "job_no": "MATRIX-JOB-001",
                    "equip_type": class_name,
                    "location": "Matrix Yard",
                    "manufacturer": "Matrix Mfr",
                    "model": "Matrix Model",
                    "serial_no": "SER-MATRIX-001",
                    "client_unit_id": "UNIT-MATRIX-001",
                    "client_reference": "REF-MATRIX-001",
                    "capacity": "1000 lbs",
                    "next_inspection_date": "August 28, 2026",
                    "status": "Requires review",
                    "inspection_date": "August 28, 2025",
                    "inspection_type": "Visual/MPI",
                    "lsd": "12-34-056-07W4",
                    "province": "AB",
                    "basket_max_height": "10 m",
                    "basket_max_reach": "8 m",
                    "basket_length": "2 m",
                    "basket_width": "1 m",
                    "basket_height": "1.2 m",
                },
            )

            fill_certificate_dotx(
                cert_template,
                cert_out,
                fields={
                    "client_name": "Matrix Client",
                    "raeq": "RAEQ59999",
                    "equip_type": class_name,
                    "inspection_date": "August 28, 2025",
                    "expiry_date": "August 28, 2026",
                    "manufacturer": "Matrix Mfr",
                    "model": "Matrix Model",
                    "serial_no": "SER-MATRIX-001",
                    "client_unit_id": "UNIT-MATRIX-001",
                    "inspector_name": "Brennan Maier MT CGSB No.20220",
                    "engineer_name": "Shawn Santo, P.Eng.",
                },
            )

            if not _docx_contains(checklist_out, "RR"):
                raise ValueError("Checklist output missing RR result.")
            if not _docx_contains(checklist_out, "RAEQ59999"):
                raise ValueError("Checklist output missing assigned RAEQ.")
            if not _docx_contains(cert_out, "Brennan Maier MT CGSB No.20220"):
                raise ValueError("Certificate output missing inspector name.")
            if not _docx_contains(cert_out, "Shawn Santo, P.Eng."):
                raise ValueError("Certificate output missing engineer name.")

            row["status"] = "PASS"
            row["checklist_docx"] = str(checklist_out.resolve())
            row["certificate_docx"] = str(cert_out.resolve())

            per_class_summary = {
                "class_name": class_name,
                "status": "PASS",
                "row_count": row["row_count"],
                "checklist_docx": row["checklist_docx"],
                "certificate_docx": row["certificate_docx"],
            }
            (class_out / "class_summary.json").write_text(
                json.dumps(per_class_summary, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            err = str(exc)
            row["error"] = err
            failures.append((class_name, err))
            (class_out / "class_summary.json").write_text(
                json.dumps(
                    {
                        "class_name": class_name,
                        "status": "FAIL",
                        "error": err,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        matrix_rows.append(row)

    return matrix_rows, failures


def main() -> None:
    ap = argparse.ArgumentParser(description="Cross-class checklist/certificate validation matrix.")
    ap.add_argument(
        "--templates-root",
        default=str(REPO_ROOT / "Templates"),
        help="Root containing class subfolders",
    )
    ap.add_argument(
        "--out-root",
        default=str(REPO_ROOT / "__validation_out__" / "cross_class"),
        help="Output directory for docx artifacts and summaries",
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Only validate first N classes (sorted by name); default = all",
    )
    args = ap.parse_args()

    templates_root = Path(args.templates_root)
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    matrix_rows, failures = _class_summaries(
        templates_root,
        out_root,
        limit=args.limit,
    )

    if not matrix_rows:
        raise SystemExit("No valid classes found for cross-class matrix.")

    pass_count = sum(1 for r in matrix_rows if r["status"] == "PASS")
    fail_count = sum(1 for r in matrix_rows if r["status"] == "FAIL")

    matrix_summary: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "templates_root": str(templates_root.resolve()),
        "out_root": str(out_root.resolve()),
        "limit": args.limit,
        "total": len(matrix_rows),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "classes": matrix_rows,
    }
    summary_path = out_root / "matrix_summary.json"
    summary_path.write_text(json.dumps(matrix_summary, indent=2) + "\n", encoding="utf-8")

    print("Cross-class validation matrix")
    for r in matrix_rows:
        print(f"- {r['class_name']}: {r['status']}")
    print(f"\nSummary: {pass_count} PASS, {fail_count} FAIL")
    print(f"Wrote {summary_path}")

    if failures:
        print("\nFailures:")
        for class_name, err in failures:
            print(f"- {class_name}: {err}")
        raise SystemExit(1)

    print("\nCross-class matrix: PASS")


if __name__ == "__main__":
    main()
