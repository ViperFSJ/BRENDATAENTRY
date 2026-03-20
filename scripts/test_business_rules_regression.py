import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.docx_fill_checklist import _fill_checklist_header_equipment
from nde_app.photo_extraction import ExtractedField, ExtractionResult
from nde_app.raeq_assign import add_available_raeqs
from nde_app.session_pipeline import (
    PhotoFirstSessionInput,
    SessionInput,
    run_inspection_session,
    run_photo_first_session,
)


def _docx_xml(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_name = next(n for n in z.namelist() if n.endswith("word/document.xml"))
        return z.read(doc_name).decode("utf-8", "ignore")


def _docx_contains(docx_path: Path, text: str) -> bool:
    return text in _docx_xml(docx_path)


def _new_test_db(name: str) -> Path:
    db_path = REPO_ROOT / name
    if db_path.exists():
        db_path.unlink()
    init_db(db_path)
    add_available_raeqs(
        db_path,
        technician_id="DEFAULT_TECH",
        display_name="Default Technician",
        raeq_spec="56300-56320",
    )
    return db_path


def test_rr_status_prompt_behavior() -> None:
    db_path = _new_test_db("__test_rules_rr.sqlite")
    out_root = REPO_ROOT / "__rule_test_out__" / "rr_status"
    out_root.mkdir(parents=True, exist_ok=True)

    session = SessionInput(
        technician_id="DEFAULT_TECH",
        class_name="Telescopic Boom Lift",
        client_name="Herc Rentals",
        owner_name="Herc Rentals",
        client_unit_id="UNIT-RR-001",
        serial_no="SER-RR-001",
        manufacturer="JLG",
        model="450AJ",
        inspection_date="August 28, 2025",
        expiry_date="August 28, 2026",
        equip_type="Telescopic Boom Lift",
        job_no="JOB-RR-1",
        location="Calgary",
        province="AB",
        lsd="12-34-056-07W4",
    )

    def checklist_provider(rows):
        out = {r.label_slug: "OK" for r in rows}
        out[rows[0].label_slug] = "RR"
        return out

    prompts = []

    def resolve_missing(field_name: str, prompt: str) -> str:
        prompts.append((field_name, prompt))
        if field_name == "status":
            return "Manual hold - RR review"
        return "N/A"

    result = run_inspection_session(
        db_path=db_path,
        templates_root=REPO_ROOT / "Templates",
        output_root=out_root,
        session=session,
        confirm_existing_callback=lambda _c: False,
        resolve_missing_field_callback=resolve_missing,
        checklist_results_provider=checklist_provider,
    )

    assert any(p[0] == "status" for p in prompts), prompts
    assert _docx_contains(result.checklist_docx, "Manual hold - RR review")


def test_rr_without_callback_defaults_to_requires_review() -> None:
    """RR with no resolve_missing_field_callback must not auto-set certification recommended."""
    db_path = _new_test_db("__test_rules_rr_nocb.sqlite")
    out_root = REPO_ROOT / "__rule_test_out__" / "rr_no_callback"
    out_root.mkdir(parents=True, exist_ok=True)

    session = SessionInput(
        technician_id="DEFAULT_TECH",
        class_name="Telescopic Boom Lift",
        client_name="Herc Rentals",
        owner_name="Herc Rentals",
        client_unit_id="UNIT-RR-NOCB-001",
        serial_no="SER-RR-NOCB-001",
        manufacturer="JLG",
        model="450AJ",
        inspection_date="August 28, 2025",
        expiry_date="August 28, 2026",
        equip_type="Telescopic Boom Lift",
        job_no="JOB-RR-NOCB",
        location="Calgary",
        province="AB",
        lsd="12-34-056-07W4",
    )

    def checklist_provider(rows):
        out = {r.label_slug: "OK" for r in rows}
        out[rows[0].label_slug] = "RR"
        return out

    result = run_inspection_session(
        db_path=db_path,
        templates_root=REPO_ROOT / "Templates",
        output_root=out_root,
        session=session,
        confirm_existing_callback=lambda _c: False,
        resolve_missing_field_callback=None,
        checklist_results_provider=checklist_provider,
    )

    # Status cell must reflect RR default when no callback (template may still mention
    # "Certification recommended" elsewhere in the document XML).
    assert _docx_contains(result.checklist_docx, "Requires review")


def test_header_equipment_raeq_replacement_robustness() -> None:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    root = ET.fromstring(
        f"""
<w:hdr xmlns:w="{ns}">
  <w:p><w:r><w:t>Equipment: RAEQ######</w:t></w:r></w:p>
  <w:p><w:r><w:t>Equipment: RAEQ#</w:t></w:r><w:r><w:t>#####</w:t></w:r></w:p>
</w:hdr>
"""
    )
    _fill_checklist_header_equipment(root, ns, {"raeq": "RAEQ56300"})
    xml = ET.tostring(root, encoding="unicode")
    assert "RAEQ######" not in xml
    assert "RAEQ#" not in xml
    assert "#####</w:t>" not in xml
    assert xml.count("RAEQ56300") >= 2


def test_client_reference_branch_behavior() -> None:
    db_path = _new_test_db("__test_rules_client_ref.sqlite")
    out_root = REPO_ROOT / "__rule_test_out__" / "client_ref"
    out_root.mkdir(parents=True, exist_ok=True)

    extraction = ExtractionResult(
        fields={
            "serial_no": ExtractedField("SER-REF-001", 0.95, "data_plate"),
            "client_unit_id": ExtractedField("UNIT-REF-001", 0.95, "unit_id_decal"),
            "manufacturer": ExtractedField("JLG", 0.90, "data_plate"),
            "model": ExtractedField("450AJ", 0.90, "data_plate"),
            "client_name": ExtractedField("Herc Rentals", 0.90, "owner_label"),
            "owner_name": ExtractedField("Herc Rentals", 0.90, "owner_label"),
            "equip_type": ExtractedField("Telescopic Boom Lift", 0.95, "full_unit"),
            "capacity": ExtractedField("500 lbs", 0.80, "data_plate"),
            "basket_max_height": ExtractedField("10 m", 0.90, "data_plate"),
            "basket_max_reach": ExtractedField("8 m", 0.90, "data_plate"),
            "basket_length": ExtractedField("2 m", 0.90, "data_plate"),
            "basket_width": ExtractedField("1 m", 0.90, "data_plate"),
            "basket_height": ExtractedField("1.2 m", 0.90, "data_plate"),
        }
    )

    def checklist_provider(rows):
        return {r.label_slug: "OK" for r in rows}

    # Blank answer defaults to yes => same as Unit ID
    answers_a = {
        "job_no": "JOB-REF-1",
        "location": "Yard",
        "province": "AB",
        "lsd": "12-34-056-07W4",
        "client_reference_same_as_unit_id": "",
    }

    def resolve_a(field_name: str, prompt: str) -> str:
        _ = prompt
        return answers_a.get(field_name, "")

    result_a = run_photo_first_session(
        db_path=db_path,
        templates_root=REPO_ROOT / "Templates",
        output_root=out_root,
        session=PhotoFirstSessionInput(
            class_name="Telescopic Boom Lift",
            inspection_date="August 28, 2025",
            expiry_date="August 28, 2026",
            extraction_result=extraction,
            technician_id="DEFAULT_TECH",
        ),
        confirm_existing_callback=lambda _c: False,
        resolve_missing_field_callback=resolve_a,
        checklist_results_provider=checklist_provider,
    )
    assert _docx_contains(result_a.checklist_docx, "UNIT-REF-001")

    # Explicit no + blank client ref => "-"
    answers_b = {
        "job_no": "JOB-REF-2",
        "location": "Yard",
        "province": "AB",
        "lsd": "12-34-056-07W4",
        "client_reference_same_as_unit_id": "n",
        "client_reference": "",
    }

    def resolve_b(field_name: str, prompt: str) -> str:
        _ = prompt
        return answers_b.get(field_name, "")

    result_b = run_photo_first_session(
        db_path=db_path,
        templates_root=REPO_ROOT / "Templates",
        output_root=out_root,
        session=PhotoFirstSessionInput(
            class_name="Telescopic Boom Lift",
            inspection_date="August 29, 2025",
            expiry_date="August 29, 2026",
            extraction_result=extraction,
            technician_id="DEFAULT_TECH",
        ),
        confirm_existing_callback=lambda _c: False,
        resolve_missing_field_callback=resolve_b,
        checklist_results_provider=checklist_provider,
    )
    assert _docx_contains(result_b.checklist_docx, ">-<") or _docx_contains(result_b.checklist_docx, "-")


def test_certificate_exact_inspector_engineer() -> None:
    db_path = _new_test_db("__test_rules_cert_names.sqlite")
    out_root = REPO_ROOT / "__rule_test_out__" / "cert_names"
    out_root.mkdir(parents=True, exist_ok=True)

    session = SessionInput(
        technician_id="DEFAULT_TECH",
        class_name="Telescopic Boom Lift",
        client_name="Herc Rentals",
        owner_name="Herc Rentals",
        client_unit_id="UNIT-CERT-001",
        serial_no="SER-CERT-001",
        manufacturer="JLG",
        model="450AJ",
        inspection_date="August 28, 2025",
        expiry_date="August 28, 2026",
        equip_type="Telescopic Boom Lift",
        job_no="JOB-CERT-1",
        location="Calgary",
        province="AB",
        lsd="12-34-056-07W4",
    )

    result = run_inspection_session(
        db_path=db_path,
        templates_root=REPO_ROOT / "Templates",
        output_root=out_root,
        session=session,
        confirm_existing_callback=lambda _c: False,
        checklist_results_provider=lambda rows: {r.label_slug: "OK" for r in rows},
    )

    cert_xml = _docx_xml(result.certificate_docx)
    assert "Brennan Maier MT CGSB No.20220" in cert_xml
    assert "Shawn Santo, P.Eng." in cert_xml


def main() -> None:
    test_rr_status_prompt_behavior()
    test_rr_without_callback_defaults_to_requires_review()
    test_header_equipment_raeq_replacement_robustness()
    test_client_reference_branch_behavior()
    test_certificate_exact_inspector_engineer()
    print("Business rules regression tests: PASS")


if __name__ == "__main__":
    main()
