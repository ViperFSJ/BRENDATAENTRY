import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.photo_extraction import ExtractedField, ExtractionResult
from nde_app.raeq_assign import add_available_raeqs
from nde_app.session_pipeline import PhotoFirstSessionInput, run_photo_first_session


def _docx_contains(docx_path: Path, text: str) -> bool:
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_name = next(n for n in z.namelist() if n.endswith("word/document.xml"))
        doc = z.read(doc_name).decode("utf-8", "ignore")
    return text in doc


def main() -> None:
    db_path = REPO_ROOT / "__test_low_confidence.sqlite"
    if db_path.exists():
        db_path.unlink()
    init_db(db_path)

    templates_root = REPO_ROOT / "Templates"
    output_root = REPO_ROOT / "__low_conf_out__"
    output_root.mkdir(parents=True, exist_ok=True)

    add_available_raeqs(
        db_path,
        technician_id="DEFAULT_TECH",
        display_name="Default Technician",
        raeq_spec="56200-56205",
    )

    extraction = ExtractionResult(
        fields={
            "serial_no": ExtractedField("0300297206", 0.96, "data_plate"),
            "client_unit_id": ExtractedField("800383502", 0.93, "unit_id_decal"),
            "manufacturer": ExtractedField("JLG", 0.88, "data_plate"),
            "model": ExtractedField("450AJ", 0.90, "data_plate"),
            "client_name": ExtractedField("Herc Rentals", 0.86, "owner_label"),
            "owner_name": ExtractedField("Herc Rentals", 0.74, "owner_label"),
            "equip_type": ExtractedField("Telescopic Boom Lift", 0.92, "full_unit"),
            "province": ExtractedField("AB", 0.78, "data_plate"),
            # Deliberately low confidence: should trigger resolve_missing fallback.
            "capacity": ExtractedField("500 lbs", 0.40, "data_plate"),
            "client_reference": ExtractedField("REF-LOW-CONF", 0.20, "data_plate"),
            "lsd": ExtractedField("LSD 12-34-056-07W4", 0.10, "data_plate"),
        }
    )

    prompted_fields = []
    fallback_values = {
        "job_no": "JOB-LOWCONF-001",
        "location": "Calgary Shop",
        "capacity": "500 lbs",
        "client_reference": "-",
        "lsd": "12-34-056-07W4",
    }

    def resolve_missing(field_name: str, prompt: str) -> str:
        prompted_fields.append(field_name)
        return fallback_values.get(field_name, "UNKNOWN")

    def confirm_existing(candidate):
        return False

    def checklist_provider(rows):
        return {r.label_slug: "OK" for r in rows}

    result = run_photo_first_session(
        db_path=db_path,
        templates_root=templates_root,
        output_root=output_root,
        session=PhotoFirstSessionInput(
            class_name="Telescopic Boom Lift",
            inspection_date="August 28, 2025",
            expiry_date="August 28, 2026",
            extraction_result=extraction,
            defaults={},
            technician_id="DEFAULT_TECH",
        ),
        confirm_existing_callback=confirm_existing,
        resolve_missing_field_callback=resolve_missing,
        checklist_results_provider=checklist_provider,
    )

    assert "job_no" in prompted_fields, prompted_fields
    assert "location" in prompted_fields, prompted_fields
    assert "capacity" in prompted_fields, prompted_fields
    assert "client_reference" in prompted_fields, prompted_fields
    assert "lsd" in prompted_fields, prompted_fields

    assert result.raeq == "RAEQ56200", result.raeq
    assert result.checklist_docx.exists()
    assert result.certificate_docx.exists()
    assert _docx_contains(result.checklist_docx, "JOB-LOWCONF-001")
    assert _docx_contains(result.checklist_docx, "Calgary Shop")
    assert _docx_contains(result.checklist_docx, "500 lbs")

    print("Low-confidence fallback test: PASS")


if __name__ == "__main__":
    main()
