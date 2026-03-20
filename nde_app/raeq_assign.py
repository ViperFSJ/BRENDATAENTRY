import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Union

from .db import init_db, upsert_technician, _connect


def extract_raeq_num(raeq_str: Union[str, int]) -> int:
    s = str(raeq_str).strip()
    # Grab the first run of digits.
    m = re.search(r"(\d+)", s)
    if not m:
        raise ValueError(f"Could not extract numeric RAEQ from: {raeq_str}")
    return int(m.group(1))


def normalize_raeq(raeq_str: Union[str, int]) -> Tuple[str, int]:
    raeq_num = extract_raeq_num(raeq_str)
    return f"RAEQ{raeq_num}", raeq_num


def expand_raeq_spec(spec: str) -> List[Tuple[str, int]]:
    """
    Expand inputs like:
      - 'RAEQ56011'
      - '56011,56012'
      - 'RAEQ56011-RAEQ56015'
      - '56011 - 56015'
    Returns list of canonical (raeq_str, raeq_num), in the order found (later we sort when assigning).
    """
    raw = (spec or "").strip()
    if not raw:
        return []

    # Split by commas first; keep ranges intact.
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    out: List[Tuple[str, int]] = []

    for part in parts:
        # Range?
        m = re.match(r"^\s*(.+?)-(.+?)\s*$", part)
        if m:
            start = normalize_raeq(m.group(1))[1]
            end = normalize_raeq(m.group(2))[1]
            if end < start:
                raise ValueError(f"Invalid RAEQ range (end < start): {part}")
            for n in range(start, end + 1):
                out.append((f"RAEQ{n}", n))
        else:
            raeq_str, raeq_num = normalize_raeq(part)
            out.append((raeq_str, raeq_num))

    return out


def add_available_raeqs(
    db_path: Union[str, Path],
    *,
    technician_id: str,
    display_name: str,
    raeq_spec: str,
) -> None:
    """
    Add/update a technician's available RAEQs.
    """
    init_db(db_path)
    entries = expand_raeq_spec(raeq_spec)
    if not entries:
        return

    conn = _connect(Path(db_path))
    try:
        upsert_technician(db_path, technician_id, display_name)

        conn.executemany(
            """
            INSERT INTO raeq_pool (technician_id, raeq, raeq_num, status, assigned_equipment_raeq)
            VALUES (?, ?, ?, 'available', NULL)
            ON CONFLICT(technician_id, raeq_num) DO UPDATE SET
                status=CASE WHEN raeq_pool.status='available' THEN 'available' ELSE raeq_pool.status END,
                assigned_equipment_raeq=CASE WHEN raeq_pool.status='available' THEN NULL ELSE raeq_pool.assigned_equipment_raeq END
            """,
            [(technician_id, raeq_str, raeq_num) for raeq_str, raeq_num in entries],
        )
        conn.commit()
    finally:
        conn.close()


def assign_next_raeq(
    db_path: Union[str, Path],
    *,
    technician_id: str,
    class_name: str,
    equipment_fields: Optional[Dict[str, str]] = None,
) -> str:
    """
    Assign the next available (lowest raeq_num) to new equipment in `class_name`.
    Creates `equipment_units` row if needed and marks the pool entry as assigned.
    Returns canonical `RAEQ####` string.
    """
    equipment_fields = equipment_fields or {}
    conn = _connect(Path(db_path))
    try:
        row = conn.execute(
            """
            SELECT raeq, raeq_num
            FROM raeq_pool
            WHERE technician_id=? AND status='available'
            ORDER BY raeq_num ASC
            LIMIT 1
            """,
            [technician_id],
        ).fetchone()
        if not row:
            raise ValueError(f"No available RAEQ entries for technician_id={technician_id}")

        raeq_str = row["raeq"]
        raeq_num = row["raeq_num"]

        # Create or ensure equipment record.
        conn.execute(
            """
            INSERT INTO equipment_units (raeq, raeq_num, class_name, client_name, client_unit_id, owner_name, province, manufacturer, model, serial_no)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(raeq) DO UPDATE SET
                class_name=excluded.class_name
            """,
            [
                raeq_str,
                raeq_num,
                class_name,
                equipment_fields.get("client_name"),
                equipment_fields.get("client_unit_id"),
                equipment_fields.get("owner_name"),
                equipment_fields.get("province"),
                equipment_fields.get("manufacturer"),
                equipment_fields.get("model"),
                equipment_fields.get("serial_no"),
            ],
        )

        # Mark pool entry as assigned and link to equipment.
        conn.execute(
            """
            UPDATE raeq_pool
            SET status='assigned', assigned_equipment_raeq=?
            WHERE technician_id=? AND raeq_num=?
            """,
            [raeq_str, technician_id, raeq_num],
        )
        conn.commit()
        return raeq_str
    finally:
        conn.close()


def mark_inspection_started(
    db_path: Union[str, Path],
    *,
    technician_id: str,
    raeq: str,
    inspection_date: Union[str, datetime],
    class_name: str,
) -> None:
    """
    Record that a technician started an inspection for this equipment.
    Used for "previously inspected by them" checks.
    """
    init_db(db_path)
    if isinstance(inspection_date, datetime):
        iso_date = inspection_date.date().isoformat()
    else:
        iso_date = str(inspection_date)

    conn = _connect(Path(db_path))
    try:
        conn.execute(
            """
            INSERT INTO inspections (raeq, technician_id, inspection_date, class_name)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(raeq, technician_id, inspection_date) DO NOTHING
            """,
            [raeq, technician_id, iso_date, class_name],
        )
        conn.commit()
    finally:
        conn.close()


def is_previously_inspected_by_technician(
    db_path: Union[str, Path],
    *,
    technician_id: str,
    raeq: str,
) -> bool:
    init_db(db_path)
    conn = _connect(Path(db_path))
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM inspections
            WHERE technician_id=? AND raeq=?
            LIMIT 1
            """,
            [technician_id, raeq],
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def history_search_for_raeq(history_root: Union[str, Path], raeq: str) -> bool:
    """
    Offline history check by scanning folder/file names for the RAEQ.
    """
    history_root = Path(history_root)
    if not history_root.exists():
        return False

    canonical_num = str(extract_raeq_num(raeq))
    canonical_text = f"RAEQ{canonical_num}"

    for root, dirs, files in os.walk(str(history_root)):
        name_parts = [Path(root).name] + dirs + files
        for name in name_parts:
            if canonical_text in name or canonical_num in name or raeq in name:
                return True
    return False


def find_equipment_candidate_by_identifiers(
    db_path: Union[str, Path],
    *,
    client_unit_id: Optional[str],
    serial_no: Optional[str],
) -> Optional[Dict[str, str]]:
    """
    Match existing equipment by:
      1) unit_id + serial (strong)
      2) unit_id only
      3) serial only
    Returns best candidate record if found.
    """
    unit = (client_unit_id or "").strip()
    serial = (serial_no or "").strip()
    if not unit and not serial:
        return None

    conn = _connect(Path(db_path))
    try:
        if unit and serial:
            row = conn.execute(
                """
                SELECT raeq, class_name, client_name, client_unit_id, serial_no, owner_name, province, manufacturer, model
                FROM equipment_units
                WHERE client_unit_id=? AND serial_no=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [unit, serial],
            ).fetchone()
            if row:
                d = dict(row)
                d["match_strength"] = "unit+serial"
                return d

        if unit:
            row = conn.execute(
                """
                SELECT raeq, class_name, client_name, client_unit_id, serial_no, owner_name, province, manufacturer, model
                FROM equipment_units
                WHERE client_unit_id=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [unit],
            ).fetchone()
            if row:
                d = dict(row)
                d["match_strength"] = "unit_only"
                return d

        if serial:
            row = conn.execute(
                """
                SELECT raeq, class_name, client_name, client_unit_id, serial_no, owner_name, province, manufacturer, model
                FROM equipment_units
                WHERE serial_no=?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                [serial],
            ).fetchone()
            if row:
                d = dict(row)
                d["match_strength"] = "serial_only"
                return d

        return None
    finally:
        conn.close()


def history_search_by_identifiers(
    history_root: Union[str, Path],
    *,
    client_unit_id: Optional[str],
    serial_no: Optional[str],
) -> Optional[str]:
    """
    Search folder/file names for unit/serial and attempt to extract an RAEQ.
    Returns canonical RAEQ if found, else None.
    """
    history_root = Path(history_root)
    if not history_root.exists():
        return None

    unit = (client_unit_id or "").strip()
    serial = (serial_no or "").strip()
    if not unit and not serial:
        return None

    # Require both when available; otherwise allow single identifier.
    for root, dirs, files in os.walk(str(history_root)):
        names = [Path(root).name] + dirs + files
        for name in names:
            s = name or ""
            if unit and serial:
                if unit not in s and serial not in s:
                    continue
            elif unit:
                if unit not in s:
                    continue
            elif serial:
                if serial not in s:
                    continue

            # Try extract RAEQ from matched name.
            m = re.search(r"RAEQ[-_ ]?(\d+)", s, flags=re.IGNORECASE)
            if m:
                return f"RAEQ{int(m.group(1))}"
    return None


def identify_or_assign_raeq_with_confirmation(
    db_path: Union[str, Path],
    *,
    technician_id: str,
    class_name: str,
    client_unit_id: Optional[str],
    serial_no: Optional[str],
    equipment_fields: Optional[Dict[str, str]],
    confirm_existing_callback: Callable[[Dict[str, str]], bool],
    history_root: Optional[Union[str, Path]] = None,
) -> Tuple[str, str]:
    """
    First check existing equipment by Unit ID + Serial and ask tech to confirm.
    If not confirmed / not found, assign next available RAEQ.

    Returns:
      (raeq, decision) where decision is one of:
      - 'existing_confirmed'
      - 'existing_rejected_new_assigned'
      - 'new_assigned'
      - 'history_confirmed'
      - 'history_rejected_new_assigned'
    """
    equipment_fields = equipment_fields or {}

    candidate = find_equipment_candidate_by_identifiers(
        db_path,
        client_unit_id=client_unit_id,
        serial_no=serial_no,
    )
    if candidate:
        if confirm_existing_callback(candidate):
            return candidate["raeq"], "existing_confirmed"
        # technician rejected candidate -> continue to new assignment
        raeq_new = assign_next_raeq(
            db_path,
            technician_id=technician_id,
            class_name=class_name,
            equipment_fields=equipment_fields,
        )
        return raeq_new, "existing_rejected_new_assigned"

    # Optional filesystem history fallback by identifiers.
    if history_root is not None:
        raeq_hist = history_search_by_identifiers(
            history_root,
            client_unit_id=client_unit_id,
            serial_no=serial_no,
        )
        if raeq_hist:
            hist_candidate = {
                "raeq": raeq_hist,
                "class_name": class_name,
                "client_unit_id": client_unit_id or "",
                "serial_no": serial_no or "",
                "match_strength": "history_filename",
            }
            if confirm_existing_callback(hist_candidate):
                return raeq_hist, "history_confirmed"
            raeq_new = assign_next_raeq(
                db_path,
                technician_id=technician_id,
                class_name=class_name,
                equipment_fields=equipment_fields,
            )
            return raeq_new, "history_rejected_new_assigned"

    raeq_new = assign_next_raeq(
        db_path,
        technician_id=technician_id,
        class_name=class_name,
        equipment_fields=equipment_fields,
    )
    return raeq_new, "new_assigned"

