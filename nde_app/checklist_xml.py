import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from .checklist_labelslug import make_labelslugs

# Word "General" checklist .docx often has blank Item/Type cells; use checklist_manifest.json.
GENERAL_CLASS_NAME = "General"


@dataclass(frozen=True)
class ChecklistRow:
    index: int
    item_label: str
    label_slug: str


def _local_name(tag: str) -> str:
    # ElementTree tags look like "{namespace}local".
    return tag.split("}")[-1] if "}" in tag else tag


def _cell_text(tc_elem: ET.Element) -> str:
    # WordprocessingML text nodes are typically <w:t>.
    parts: List[str] = []
    for t in tc_elem.iter():
        if _local_name(t.tag) == "t" and t.text:
            parts.append(t.text)
    # Join and normalize whitespace.
    s = "".join(parts)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _iter_child_table_rows(tbl_elem: ET.Element) -> Iterable[ET.Element]:
    for tr in tbl_elem.iter():
        if _local_name(tr.tag) == "tr":
            yield tr


def _find_checklist_table(root: ET.Element) -> Tuple[Optional[ET.Element], Optional[int]]:
    """
    Find the first <w:tbl> that contains a header row with:
    - Item
    - Type of Inspection
    - Results
    - Comments
    """
    for tbl in root.iter():
        if _local_name(tbl.tag) != "tbl":
            continue
        for i, tr in enumerate(_iter_child_table_rows(tbl)):
            # Build cell text list for this row.
            tcs = [tc for tc in tr if _local_name(tc.tag) == "tc"]
            if not tcs:
                continue
            cells = [_cell_text(tc) for tc in tcs]
            joined = " | ".join(cells).lower()
            if "item" in joined and "type of inspection" in joined and "comments" in joined and "result" in joined:
                # Choose this table and row index as the header.
                return tbl, i
    return None, None


def _extract_columns_from_header_row(header_row_tcs: Sequence[ET.Element]) -> Tuple[int, int, int]:
    """
    Returns: item_col, type_col, results_col
    comments_col is not needed for extraction.
    """
    cells = [_cell_text(tc) for tc in header_row_tcs]

    def find_first(predicate) -> Optional[int]:
        for idx, txt in enumerate(cells):
            if predicate(txt):
                return idx
        return None

    item_col = find_first(lambda t: t == "Item" or t.lower() == "item")  # exact match preferred
    type_col = find_first(lambda t: "type of inspection" in t.lower())

    # Results header can be "Results" or "Inspection Results" depending on template.
    results_col = find_first(lambda t: t.lower() in {"results", "inspection results"} or "result" in t.lower())

    if item_col is None or type_col is None or results_col is None:
        raise ValueError(f"Could not map checklist columns from header cells: {cells}")

    return item_col, type_col, results_col


def extract_checklist_items_from_checklist_xml(xml_path: Union[str, Path]) -> List[ChecklistRow]:
    """
    Extract checklist row `Item` labels from a class Checklist*.xml and return ordered rows with LABELSLUG.

    Implementation strategy:
    - Parse XML
    - Find the checklist table by header detection.
    - Identify column indexes for Item / Type of Inspection / Results.
    - For each row after the header:
      - Read Item label from Item column.
      - Read Type of Inspection from Type column.
      - Skip rows where Type column is empty (these are usually section headers).
    """
    xml_path = Path(xml_path)
    tree = ET.parse(xml_path)
    root = tree.getroot()

    tbl, header_row_index = _find_checklist_table(root)
    if tbl is None or header_row_index is None:
        raise ValueError(f"No checklist table header found in: {xml_path}")

    # Materialize rows so we can index.
    rows = [tr for tr in _iter_child_table_rows(tbl)]
    header_row = rows[header_row_index]

    header_tcs = [tc for tc in header_row if _local_name(tc.tag) == "tc"]
    item_col, type_col, _results_col = _extract_columns_from_header_row(header_tcs)

    labels: List[str] = []
    for tr in rows[header_row_index + 1 :]:
        tcs = [tc for tc in tr if _local_name(tc.tag) == "tc"]
        if len(tcs) <= max(item_col, type_col):
            continue

        item_text = _cell_text(tcs[item_col])

        if not item_text or item_text.lower() == "item":
            continue

        # Many templates don't include the type phrase in the item label,
        # but some may have weird repeats; filter conservatively.
        if "type of inspection" in item_text.lower():
            continue

        # Keep ordered list.
        labels.append(item_text)

    # Collapse consecutive duplicate labels (Word XML sometimes repeats due to formatting).
    deduped: List[str] = []
    for lab in labels:
        if not deduped or deduped[-1] != lab:
            deduped.append(lab)

    slugs, _ = make_labelslugs(deduped)

    out: List[ChecklistRow] = []
    for idx, (label, slug) in enumerate(zip(deduped, slugs)):
        out.append(ChecklistRow(index=idx, item_label=label, label_slug=slug))
    return out


def _load_general_manifest_items(templates_root: Path) -> List[str]:
    manifest = templates_root / GENERAL_CLASS_NAME / "checklist_manifest.json"
    if not manifest.exists():
        raise FileNotFoundError(
            f"General class needs {manifest} with an 'items' list "
            "(the General Word checklist has blank item/type cells)."
        )
    data = json.loads(manifest.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError(f"Invalid or empty 'items' in {manifest}")
    out = [str(x).strip() for x in items if str(x).strip()]
    if not out:
        raise ValueError(f"No non-empty strings in 'items' in {manifest}")
    return out


def extract_checklist_items_for_class(templates_root: Union[str, Path], class_name: str) -> List[ChecklistRow]:
    """
    Find Checklist*.xml under Templates/<class_name>/ and extract item rows.

    For ``General``, the exported XML often has no text in Item cells; if extraction
    yields zero rows, labels are loaded from ``Templates/General/checklist_manifest.json``
    in table order (must match row count in the .docx).
    """
    templates_root = Path(templates_root)
    class_dir = templates_root / class_name
    if not class_dir.exists():
        raise FileNotFoundError(f"Class template directory not found: {class_dir}")

    # There should be exactly one Checklist*.xml per class.
    xml_files = sorted(class_dir.glob("Checklist*.xml"))
    if not xml_files:
        raise FileNotFoundError(f"No Checklist*.xml found in {class_dir}")
    # If multiple exist, choose the first deterministically.
    rows = extract_checklist_items_from_checklist_xml(xml_files[0])
    if not rows and class_name == GENERAL_CLASS_NAME:
        items = _load_general_manifest_items(templates_root)
        slugs, _ = make_labelslugs(items)
        return [
            ChecklistRow(index=i, item_label=lab, label_slug=slug)
            for i, (lab, slug) in enumerate(zip(items, slugs))
        ]
    return rows

