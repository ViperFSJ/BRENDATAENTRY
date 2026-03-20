from pathlib import Path
import sys
import re
import zipfile
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nde_app.docx_fill_certificate import fill_certificate_dotx


def _local(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _docx_has_text(docx_path: Path, text: str) -> bool:
    with zipfile.ZipFile(docx_path, "r") as z:
        doc_name = next(n for n in z.namelist() if n.endswith("word/document.xml"))
        doc = z.read(doc_name).decode("utf-8", "ignore")
    return doc.find(text) != -1


def main() -> None:
    repo_root = REPO_ROOT
    templates_root = REPO_ROOT / "Templates"

    class_name = "Telescopic Boom Lift"
    template = next((templates_root / class_name).glob("EC-1210D*.dotx"))

    out = repo_root / "__test_cert_filled.docx"

    fill_certificate_dotx(
        template,
        out,
        fields={
            "client_name": "Herc Rentals",
            "raeq": "RAEQ56011",
            "equip_type": "Telescopic Boom Lift",
            "inspection_date": "August 28, 2025",
            "expiry_date": "August 28, 2026",
            "manufacturer": "JLG",
            "model": "450AJ",
            "serial_no": "0300297206",
            "client_unit_id": "800383502",
        },
    )

    # Simple XML presence checks.
    checks = [
        "RAEQ56011",
        "Herc Rentals",
        "Telescopic Boom Lift",
        "August 28, 2025",
        "August 28 2026",  # expiry placeholder has no comma in template
        "JLG",
        "450AJ",
        "0300297206",
        "800383502",
    ]
    missing = [c for c in checks if not _docx_has_text(out, c)]
    if missing:
        raise SystemExit(f"Certificate fill validation failed; missing: {missing}")
    print("Certificate fill test: PASS")


if __name__ == "__main__":
    main()

