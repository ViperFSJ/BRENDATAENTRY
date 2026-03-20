import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.photo_extraction import ExtractedField, ExtractionResult
from nde_app.raeq_assign import add_available_raeqs
from nde_app.session_pipeline import PhotoFirstSessionInput, run_photo_first_session


def _load_extraction_json(path: Path) -> ExtractionResult:
    """
    JSON format:
    {
      "fields": {
        "serial_no": {"value":"0300297206","confidence":0.95,"source_photo_type":"data_plate"},
        ...
      }
    }
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    fields = {}
    for k, v in raw.get("fields", {}).items():
        fields[k] = ExtractedField(
            value=str(v.get("value", "")),
            confidence=float(v.get("confidence", 0.0)),
            source_photo_type=str(v.get("source_photo_type", "unknown")),
        )
    return ExtractionResult(fields=fields)


def _prompt_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    ans = input(prompt + suffix).strip().lower()
    if ans == "":
        return default_yes
    return ans in ("y", "yes")


def _confirm_existing(candidate: Dict[str, str]) -> bool:
    print("\nPossible existing unit found:")
    print(f"  RAEQ: {candidate.get('raeq', '')}")
    print(f"  Match strength: {candidate.get('match_strength', '')}")
    print(f"  Unit ID: {candidate.get('client_unit_id', '')}")
    print(f"  Serial: {candidate.get('serial_no', '')}")
    print(f"  Class: {candidate.get('class_name', '')}")
    return _prompt_yes_no("Is this the same equipment?", default_yes=True)


def _resolve_missing(field_name: str, prompt: str) -> str:
    value = input(f"{prompt}: ").strip()
    return value


def _acknowledge_photos_ready() -> None:
    input("Photos captured/uploaded. Press Enter to continue: ")


def _confirm_existing_force_new(candidate: Dict[str, str]) -> bool:
    # Demo mode helper: always treat as new equipment.
    _ = candidate
    return False


def _checklist_results_provider(rows):
    # Simple technician workflow:
    # Ask if all OK, then allow RR/N/A overrides by row index.
    print("\nChecklist items:")
    for r in rows:
        print(f"  [{r.index}] {r.item_label}")

    all_ok = _prompt_yes_no("Are all checklist items OK?", default_yes=True)
    if all_ok:
        return {r.label_slug: "OK" for r in rows}

    rr_raw = input("Enter indexes to mark RR (comma/space separated, blank for none): ").strip()
    na_raw = input("Enter indexes to mark N/A (comma/space separated, blank for none): ").strip()

    def parse(raw: str):
        out = []
        if not raw:
            return out
        for t in raw.replace(",", " ").split():
            if t.isdigit():
                i = int(t)
                if 0 <= i < len(rows) and i not in out:
                    out.append(i)
        return out

    rr = set(parse(rr_raw))
    na = set(parse(na_raw))

    results = {}
    for r in rows:
        if r.index in na:
            results[r.label_slug] = "N/A"
        elif r.index in rr:
            results[r.label_slug] = "RR"
        else:
            results[r.label_slug] = "OK"
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description="Technician intake demo (photo-first).")
    ap.add_argument("--db-path", default=str(REPO_ROOT / "nde_demo.sqlite"))
    ap.add_argument("--templates-root", default=str(REPO_ROOT / "Templates"))
    ap.add_argument("--output-root", default=str(REPO_ROOT / "demo_output"))
    ap.add_argument(
        "--extraction-json",
        default=str(REPO_ROOT / "samples" / "telescopic_boom_lift_extraction.json"),
    )
    ap.add_argument(
        "--use-low-confidence-sample",
        action="store_true",
        help="Use sample OCR payload with low-confidence optional fields to exercise manual fallback prompts",
    )
    ap.add_argument("--history-root", default=None)
    ap.add_argument(
        "--force-new-equipment",
        action="store_true",
        help="Bypass existing-unit confirmation and always assign from available RAEQ pool",
    )
    ap.add_argument("--class-name", default=None)
    ap.add_argument("--inspection-date", default=None)
    ap.add_argument("--expiry-date", default=None)
    ap.add_argument("--seed-raeq-spec", default="56150-56160")
    ap.add_argument("--technician-id", default="DEFAULT_TECH")
    ap.add_argument("--photo-path", action="append", default=[], help="Photo path to embed (repeatable)")
    ap.add_argument(
        "--use-provided-test-photos",
        action="store_true",
        help="Use provided PXL_* images from cursor assets for Figure boxes",
    )
    ap.add_argument(
        "--require-photo-ack",
        action="store_true",
        help="Testing only: require tech acknowledgement at photo stage before continuing",
    )
    args = ap.parse_args()

    db_path = Path(args.db_path)
    templates_root = Path(args.templates_root)
    output_root = Path(args.output_root)
    extraction_json = Path(args.extraction_json)
    if args.use_low_confidence_sample:
        extraction_json = REPO_ROOT / "samples" / "telescopic_boom_lift_extraction_low_confidence.json"
    history_root = Path(args.history_root) if args.history_root else None
    photo_paths: List[str] = list(args.photo_path or [])
    if args.use_provided_test_photos:
        assets_dir = Path("/Users/dillon/.cursor/projects/Users-dillon-BrenDataEntry/assets")
        if assets_dir.exists():
            auto_photos = sorted(str(p) for p in assets_dir.glob("PXL_*"))
            photo_paths.extend(auto_photos)

    init_db(db_path)
    # Keep idempotent: this upsert/insert flow won't break if run multiple times.
    add_available_raeqs(
        db_path,
        technician_id=args.technician_id,
        display_name="Default Technician",
        raeq_spec=args.seed_raeq_spec,
    )

    extraction = _load_extraction_json(extraction_json)

    # Start new inspection UX
    print("=== New Inspection ===")
    class_name = args.class_name or input("Select class (e.g. Telescopic Boom Lift): ").strip()
    inspection_date = args.inspection_date or input("Inspection date (e.g. August 28, 2025): ").strip()
    expiry_date = args.expiry_date or input("Expiry date (e.g. August 28, 2026): ").strip()
    if args.require_photo_ack:
        _acknowledge_photos_ready()

    result = run_photo_first_session(
        db_path=db_path,
        templates_root=templates_root,
        output_root=output_root,
        session=PhotoFirstSessionInput(
            class_name=class_name,
            inspection_date=inspection_date,
            expiry_date=expiry_date,
            extraction_result=extraction,
            defaults={},
            technician_id=args.technician_id,
            photo_paths=photo_paths,
        ),
        confirm_existing_callback=_confirm_existing_force_new if args.force_new_equipment else _confirm_existing,
        resolve_missing_field_callback=_resolve_missing,
        checklist_results_provider=_checklist_results_provider,
        history_root=history_root,
    )

    print("\n=== Session Complete ===")
    print(f"RAEQ: {result.raeq}")
    print(f"Decision: {result.decision}")
    print(f"Checklist docx: {result.checklist_docx}")
    print(f"Certificate docx: {result.certificate_docx}")
    print(f"Photos inserted into Figure boxes: {result.inserted_photo_count}")


if __name__ == "__main__":
    main()

