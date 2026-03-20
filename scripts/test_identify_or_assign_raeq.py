import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.db import init_db
from nde_app.raeq_assign import (
    add_available_raeqs,
    assign_next_raeq,
    identify_or_assign_raeq_with_confirmation,
)


def main() -> None:
    db_path = REPO_ROOT / "__test_identify_assign.sqlite"
    if db_path.exists():
        db_path.unlink()
    init_db(db_path)

    tech_id = "TECH_X"
    add_available_raeqs(
        db_path,
        technician_id=tech_id,
        display_name="Tech X",
        raeq_spec="56020-56025",
    )

    # Seed one existing unit
    existing_raeq = assign_next_raeq(
        db_path,
        technician_id=tech_id,
        class_name="Telescopic Boom Lift",
        equipment_fields={
            "client_name": "Herc Rentals",
            "client_unit_id": "800383502",
            "serial_no": "0300297206",
        },
    )
    assert existing_raeq == "RAEQ56020"

    # Case 1: match found + confirmed => reuse existing
    raeq, decision = identify_or_assign_raeq_with_confirmation(
        db_path,
        technician_id=tech_id,
        class_name="Telescopic Boom Lift",
        client_unit_id="800383502",
        serial_no="0300297206",
        equipment_fields={"client_name": "Herc Rentals"},
        confirm_existing_callback=lambda candidate: True,
    )
    assert raeq == "RAEQ56020"
    assert decision == "existing_confirmed"

    # Case 2: match found + rejected => assign next sequential
    raeq2, decision2 = identify_or_assign_raeq_with_confirmation(
        db_path,
        technician_id=tech_id,
        class_name="Telescopic Boom Lift",
        client_unit_id="800383502",
        serial_no="0300297206",
        equipment_fields={
            "client_name": "Herc Rentals",
            "client_unit_id": "different-unit",
            "serial_no": "different-serial",
        },
        confirm_existing_callback=lambda candidate: False,
    )
    assert raeq2 == "RAEQ56021"
    assert decision2 == "existing_rejected_new_assigned"

    # Case 3: no match => assign next sequential
    raeq3, decision3 = identify_or_assign_raeq_with_confirmation(
        db_path,
        technician_id=tech_id,
        class_name="Telescopic Boom Lift",
        client_unit_id="NEW-UNIT-1",
        serial_no="NEW-SERIAL-1",
        equipment_fields={
            "client_name": "Herc Rentals",
            "client_unit_id": "NEW-UNIT-1",
            "serial_no": "NEW-SERIAL-1",
        },
        confirm_existing_callback=lambda candidate: True,
    )
    assert raeq3 == "RAEQ56022"
    assert decision3 == "new_assigned"

    print("Identify-or-assign RAEQ test: PASS")


if __name__ == "__main__":
    main()

