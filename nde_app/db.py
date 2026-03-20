import sqlite3
from pathlib import Path
from typing import Dict, Union


RESULT_ALLOWED = {"OK", "RR", "N/A"}


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Union[str, Path]) -> None:
    """
    Create/ensure tables needed for checklist per-item results persistence,
    plus RAEQ pool + equipment + inspection history.
    """
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS checklist_results (
                raeq TEXT NOT NULL,
                class_name TEXT NOT NULL,
                label_slug TEXT NOT NULL,
                result TEXT NOT NULL CHECK (result IN ('OK','RR','N/A')),
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (raeq, class_name, label_slug)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS technicians (
                technician_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS equipment_units (
                raeq TEXT PRIMARY KEY,
                raeq_num INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                client_name TEXT,
                client_unit_id TEXT,
                owner_name TEXT,
                province TEXT,
                manufacturer TEXT,
                model TEXT,
                serial_no TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raeq_pool (
                technician_id TEXT NOT NULL,
                raeq TEXT NOT NULL,
                raeq_num INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('available','assigned','consumed')),
                assigned_equipment_raeq TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (technician_id, raeq_num),
                FOREIGN KEY (technician_id) REFERENCES technicians(technician_id),
                FOREIGN KEY (assigned_equipment_raeq) REFERENCES equipment_units(raeq)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS inspections (
                raeq TEXT NOT NULL,
                technician_id TEXT NOT NULL,
                inspection_date TEXT,
                class_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (raeq, technician_id, inspection_date),
                FOREIGN KEY (raeq) REFERENCES equipment_units(raeq),
                FOREIGN KEY (technician_id) REFERENCES technicians(technician_id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_checklist_results(
    db_path: Union[str, Path],
    *,
    raeq: str,
    class_name: str,
    results_by_label_slug: Dict[str, str],
) -> None:
    """
    Upsert checklist results for a single equipment (raeq) + class.
    """
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        # Validate values early.
        for slug, result in results_by_label_slug.items():
            if result not in RESULT_ALLOWED:
                raise ValueError(f"Invalid result for {slug}: {result}")

        # Upsert each row.
        conn.executemany(
            """
            INSERT INTO checklist_results (raeq, class_name, label_slug, result)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(raeq, class_name, label_slug) DO UPDATE SET
                result=excluded.result,
                updated_at=CURRENT_TIMESTAMP
            """,
            [(raeq, class_name, slug, result) for slug, result in results_by_label_slug.items()],
        )
        # Ensure any previously-stored slugs that are not present now are removed
        # (so "all OK" can overwrite partial RR/N/A sets cleanly).
        if results_by_label_slug:
            conn.execute(
                "DELETE FROM checklist_results WHERE raeq=? AND class_name=? AND label_slug NOT IN ("
                + ",".join(["?"] * len(results_by_label_slug))
                + ")",
                [raeq, class_name] + list(results_by_label_slug.keys()),
            )
        else:
            conn.execute(
                "DELETE FROM checklist_results WHERE raeq=? AND class_name=?",
                [raeq, class_name],
            )
        conn.commit()
    finally:
        conn.close()


def load_checklist_results(
    db_path: Union[str, Path],
    *,
    raeq: str,
    class_name: str,
) -> Dict[str, str]:
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT label_slug, result FROM checklist_results WHERE raeq=? AND class_name=?",
            [raeq, class_name],
        )
        return {row["label_slug"]: row["result"] for row in cur.fetchall()}
    finally:
        conn.close()


def upsert_technician(db_path: Union[str, Path], technician_id: str, display_name: str) -> None:
    db_path = Path(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO technicians (technician_id, display_name)
            VALUES (?, ?)
            ON CONFLICT(technician_id) DO UPDATE SET
                display_name=excluded.display_name
            """,
            [technician_id, display_name],
        )
        conn.commit()
    finally:
        conn.close()

