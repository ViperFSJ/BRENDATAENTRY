import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.raeq_assign import (
    add_available_raeqs,
    assign_next_raeq,
    history_search_for_raeq,
    is_previously_inspected_by_technician,
    mark_inspection_started,
)


def main() -> None:
    repo_root = REPO_ROOT
    db_path = repo_root / "__test_raeq_assignment.sqlite"
    if db_path.exists():
        db_path.unlink()

    init_db(db_path)

    tech_id = "TECH_A"
    tech_name = "Tech A"
    add_available_raeqs(
        db_path,
        technician_id=tech_id,
        display_name=tech_name,
        raeq_spec="56011-56013",
    )

    assigned1 = assign_next_raeq(
        db_path,
        technician_id=tech_id,
        class_name="Telescopic Boom Lift",
        equipment_fields={"client_name": "Herc Rentals", "client_unit_id": "800383502"},
    )
    assert assigned1 == "RAEQ56011", assigned1

    assigned2 = assign_next_raeq(
        db_path,
        technician_id=tech_id,
        class_name="Telescopic Boom Lift",
        equipment_fields={"client_name": "Herc Rentals", "client_unit_id": "800383502"},
    )
    assert assigned2 == "RAEQ56012", assigned2

    raeq = assigned1
    assert is_previously_inspected_by_technician(
        db_path, technician_id=tech_id, raeq=raeq
    ) is False

    mark_inspection_started(
        db_path,
        technician_id=tech_id,
        raeq=raeq,
        inspection_date="2025-08-28",
        class_name="Telescopic Boom Lift",
    )
    assert is_previously_inspected_by_technician(
        db_path, technician_id=tech_id, raeq=raeq
    ) is True

    # History folder scan test.
    hist_root = repo_root / "__test_history__"
    if hist_root.exists():
        # Best-effort cleanup; no need to be perfect for this test.
        for p in hist_root.rglob("*"):
            if p.is_file():
                p.unlink()
    hist_root.mkdir(parents=True, exist_ok=True)
    (hist_root / "somefile_RAEQ56099_report.pdf").write_text("x", encoding="utf-8")
    (hist_root / "another_RAEQ56011_doc.pdf").write_text("x", encoding="utf-8")
    assert history_search_for_raeq(hist_root, raeq) is True
    assert history_search_for_raeq(hist_root, "RAEQ56012") is False

    print("RAEQ assignment test: PASS")


if __name__ == "__main__":
    main()

