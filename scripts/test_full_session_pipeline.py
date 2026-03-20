import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.raeq_assign import add_available_raeqs
from nde_app.session_pipeline import SessionInput, run_inspection_session


def _docx_contains(docx_path: Path, text: str) -> bool:
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_name = next(n for n in z.namelist() if n.endswith("word/document.xml"))
        doc = z.read(doc_name).decode("utf-8", "ignore")
    return text in doc


def main() -> None:
    db_path = REPO_ROOT / "__test_full_session.sqlite"
    if db_path.exists():
        db_path.unlink()
    init_db(db_path)

    templates_root = REPO_ROOT / "Templates"
    output_root = REPO_ROOT / "__session_out__"
    output_root.mkdir(parents=True, exist_ok=True)

    add_available_raeqs(
        db_path,
        technician_id="TECH_PIPE",
        display_name="Pipeline Tech",
        raeq_spec="56050-56055",
    )

    session = SessionInput(
        technician_id="TECH_PIPE",
        class_name="Telescopic Boom Lift",
        client_name="Herc Rentals",
        owner_name="Herc Rentals",
        client_unit_id="800383502",
        serial_no="0300297206",
        manufacturer="JLG",
        model="450AJ",
        inspection_date="August 28, 2025",
        expiry_date="August 28, 2026",
        equip_type="Telescopic Boom Lift",
        province="AB",
    )

    def _confirm(candidate):
        # For this first run, treat as new unit path.
        return False

    def _results_provider(rows):
        # Default all OK; mark one as RR to test override persistence.
        out = {r.label_slug: "OK" for r in rows}
        if rows:
            out[rows[0].label_slug] = "RR"
        return out

    result = run_inspection_session(
        db_path=db_path,
        templates_root=templates_root,
        output_root=output_root,
        session=session,
        confirm_existing_callback=_confirm,
        checklist_results_provider=_results_provider,
    )

    assert result.raeq == "RAEQ56050", result.raeq
    assert result.checklist_docx.exists(), result.checklist_docx
    assert result.certificate_docx.exists(), result.certificate_docx

    # Spot checks in generated docs
    assert _docx_contains(result.certificate_docx, "RAEQ56050")
    assert _docx_contains(result.certificate_docx, "Herc Rentals")
    assert _docx_contains(result.checklist_docx, "RR")

    print("Full session pipeline test: PASS")


if __name__ == "__main__":
    main()

