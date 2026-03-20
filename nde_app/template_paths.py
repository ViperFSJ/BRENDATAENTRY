"""
Resolve template file paths under Templates/<class_name>/.

Some classes ship checklist as Word template (.dotx); "General" uses .docx
(same OpenXML package; fillers work the same).
"""
from pathlib import Path
from typing import List, Union


def list_equipment_class_names(templates_root: Union[str, Path]) -> List[str]:
    """
    Sorted folder names that can run a full inspection (checklist + certificate).

    Use this to populate UI dropdowns so technicians never type class names.
    """
    root = Path(templates_root)
    names: List[str] = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        has_checklist = bool(
            list(d.glob("Checklist*.dotx")) + list(d.glob("Checklist*.docx"))
        )
        if has_checklist and any(d.glob("EC-1210D*.dotx")):
            names.append(d.name)
    return names


def find_checklist_template(class_dir: Path) -> Path:
    """
    Return the checklist Word file for this class directory.

    Prefers ``Checklist*.dotx``; falls back to ``Checklist*.docx`` if no dotx exists.
    """
    class_dir = Path(class_dir)
    dotx = sorted(class_dir.glob("Checklist*.dotx"))
    if dotx:
        return dotx[0]
    docx = sorted(class_dir.glob("Checklist*.docx"))
    if docx:
        return docx[0]
    raise FileNotFoundError(
        f"No checklist template (Checklist*.dotx or Checklist*.docx) in {class_dir}"
    )


def find_certificate_template(class_dir: Path) -> Path:
    """Return ``EC-1210D*.dotx`` certificate template."""
    class_dir = Path(class_dir)
    certs = sorted(class_dir.glob("EC-1210D*.dotx"))
    if not certs:
        raise FileNotFoundError(f"No EC-1210D*.dotx certificate template in {class_dir}")
    return certs[0]
