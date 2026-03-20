import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .checklist_labelslug import make_labelslugs, slugify_label_base
from .checklist_xml import GENERAL_CLASS_NAME, ChecklistRow, extract_checklist_items_for_class


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _get_w_namespace(root: ET.Element) -> str:
    # Find the namespace from any {ns}tc tag.
    for el in root.iter():
        if _local_name(el.tag) == "tc":
            if "}" in el.tag:
                return el.tag.split("}")[0].strip("{")
    # Fallback to known Word namespace.
    return "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def _cell_text(tc_elem: ET.Element) -> str:
    parts: List[str] = []
    for t in tc_elem.iter():
        if _local_name(t.tag) == "t" and (t.text is not None):
            # Sometimes Word uses empty <w:t/> nodes; skip them.
            if t.text != "":
                parts.append(t.text)
    s = "".join(parts)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_input_date(value: Union[str, datetime]) -> datetime:
    if isinstance(value, datetime):
        return value
    s = (value or "").strip()
    fmts = [
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    raise ValueError(f"Unsupported date format: {value}")


def _format_date_for_placeholder(dt: datetime, placeholder_text: str) -> str:
    ph = (placeholder_text or "").strip().lower()
    has_comma = "," in ph or "month dd," in ph
    if has_comma:
        return dt.strftime("%B %d, %Y")
    return dt.strftime("%B %d %Y")


def _row_value_containers(tr_elem: ET.Element) -> List[ET.Element]:
    """
    Checklist template rows can include direct child `w:sdt` nodes between `w:tc` nodes.
    Use this ordered list for column indexing.
    """
    return [c for c in list(tr_elem) if _local_name(c.tag) in ("tc", "sdt")]


def _find_checklist_table_and_columns(root: ET.Element) -> Tuple[ET.Element, int, int, int]:
    """
    Returns:
      - tbl element
      - header_row_index within that tbl's <w:tr> sequence
      - item_col index
      - results_col index
    """
    for tbl in root.iter():
        if _local_name(tbl.tag) != "tbl":
            continue
        rows = [tr for tr in tbl.iter() if _local_name(tr.tag) == "tr"]
        for header_i, tr in enumerate(rows):
            cols = _row_value_containers(tr)
            if not cols:
                continue
            cells = [_cell_text(col) for col in cols]
            joined = " | ".join(cells).lower()
            if "item" in joined and "type of inspection" in joined and "comments" in joined and "result" in joined:
                item_col = None
                results_col = None
                for j, c in enumerate(cells):
                    c_norm = c.strip().lower()
                    if c_norm == "item" or c_norm == "item ":
                        item_col = j
                    if c_norm in ("results", "inspection results") or "result" in c_norm:
                        results_col = j
                if item_col is None or results_col is None:
                    raise ValueError("Header row found but failed to map columns")
                return tbl, header_i, item_col, results_col
    raise ValueError("Could not locate checklist table header in document.xml")


def _set_container_text(container: ET.Element, w_ns: str, value_text: str) -> None:
    # Replace any existing <w:t> nodes with selected value.
    t_nodes = [e for e in container.iter() if _local_name(e.tag) == "t"]
    if t_nodes:
        # Set first text run; clear any additional runs to avoid duplicated values.
        t_nodes[0].text = value_text
        for t in t_nodes[1:]:
            t.text = ""
        return

    # If this is an sdt, write into sdtContent.
    if _local_name(container.tag) == "sdt":
        sdt_content = None
        for el in container.iter():
            if _local_name(el.tag) == "sdtContent":
                sdt_content = el
                break
        if sdt_content is not None:
            p = ET.SubElement(sdt_content, _w(w_ns, "p"))
            r = ET.SubElement(p, _w(w_ns, "r"))
            t = ET.SubElement(r, _w(w_ns, "t"))
            t.text = value_text
            return

    # Otherwise create a basic paragraph/run/text in container (tc fallback).
    p_nodes = [e for e in container.iter() if _local_name(e.tag) == "p"]
    p = p_nodes[0] if p_nodes else ET.SubElement(container, _w(w_ns, "p"))
    r = ET.SubElement(p, _w(w_ns, "r"))
    t = ET.SubElement(r, _w(w_ns, "t"))
    t.text = value_text


def _fill_checklist_report_details(root: ET.Element, w_ns: str, fields: Dict[str, str]) -> None:
    """
    Fill top inspection-report detail rows by matching label text and writing into next value container.
    """
    label_to_key = {
        "Client:": "client_name",
        "Owner:": "owner_name",
        "RAE No.:": "raeq",
        "Job No.:": "job_no",
        "Equipment Type:": "equip_type",
        "Location:": "location",
        "Manufacturer:": "manufacturer",
        "Model:": "model",
        "Serial No.:": "serial_no",
        "Unit ID:": "client_unit_id",
        "Client Reference:": "client_reference",
        "Capacity:": "capacity",
        "Next Inspection:": "next_inspection_date",
        "Status:": "status",
        "Inspection Date:": "inspection_date",
        "Inspection Type:": "inspection_type",
    }

    # Special handling for LSD row: "LSD:" followed by province (XX) then LSD value.
    lsd_target = fields.get("lsd")
    province_target = fields.get("province")

    for tr in root.iter(_w(w_ns, "tr")):
        cols = _row_value_containers(tr)
        if not cols:
            continue
        col_texts = [_cell_text(c) for c in cols]

        # Generic label -> next value container
        for i, label in enumerate(col_texts):
            key = label_to_key.get(label)
            if not key:
                continue
            if i + 1 >= len(cols):
                continue
            value = fields.get(key, "").strip()
            if value == "":
                continue
            # Date fields should respect placeholder style.
            if key in ("inspection_date", "next_inspection_date"):
                try:
                    dt = _parse_input_date(value)
                    value = _format_date_for_placeholder(dt, _cell_text(cols[i + 1]))
                except Exception:
                    pass
            _set_container_text(cols[i + 1], w_ns, value)

        # LSD + province row handling
        if "LSD:" in col_texts:
            idx = col_texts.index("LSD:")
            # Typically two following value containers: province then LSD value
            if province_target and idx + 1 < len(cols):
                _set_container_text(cols[idx + 1], w_ns, province_target)
            if lsd_target and idx + 2 < len(cols):
                _set_container_text(cols[idx + 2], w_ns, lsd_target)


def _fill_checklist_header_equipment(root: ET.Element, w_ns: str, fields: Dict[str, str]) -> None:
    """
    In header sections, replace Equipment placeholder value with assigned RAEQ.
    """
    raeq = (fields.get("raeq") or "").strip()
    if not raeq:
        return
    t_nodes = [t for t in root.iter(_w(w_ns, "t"))]
    for i, t in enumerate(t_nodes):
        current = t.text or ""
        if "RAEQ######" in current:
            t.text = current.replace("RAEQ######", raeq)
            continue
        # Some templates split this placeholder across runs: "RAEQ#" + "#####".
        if "RAEQ#" in current:
            t.text = current.replace("RAEQ#", raeq)
            if i + 1 < len(t_nodes):
                nxt = t_nodes[i + 1]
                nxt_text = nxt.text or ""
                if nxt_text.strip("#") == "" and "#" in nxt_text:
                    nxt.text = ""


def _fill_basket_information(root: ET.Element, w_ns: str, fields: Dict[str, str]) -> None:
    """
    Fill third-page BASKET INFORMATION values by adjacent blank cells.
    """
    basket_map = {
        "Maximum Height": "basket_max_height",
        "Maximum Reach": "basket_max_reach",
        "Length": "basket_length",
        "Width": "basket_width",
        "Height": "basket_height",
    }
    for tr in root.iter(_w(w_ns, "tr")):
        cols = _row_value_containers(tr)
        if not cols:
            continue
        col_texts = [_cell_text(c) for c in cols]
        for i, label in enumerate(col_texts):
            key = basket_map.get(label)
            if not key:
                continue
            if i + 1 >= len(cols):
                continue
            value = (fields.get(key) or "").strip()
            if value == "":
                continue
            _set_container_text(cols[i + 1], w_ns, value)


def fill_checklist_results_in_dotx(
    template_dotx_path: Union[str, Path],
    output_docx_path: Union[str, Path],
    templates_root: Union[str, Path],
    class_name: str,
    results_by_label_slug: Dict[str, str],
    fields: Optional[Dict[str, str]] = None,
) -> None:
    """
    Fill checklist results in a class's checklist `.dotx` template by:
      - Extracting the ordered checklist items from the corresponding XML template
      - Parsing the checklist table from internal `word/document.xml`
      - For each row, matching the `Item` cell text and writing the chosen `OK/RR/N/A`
        into the adjacent `Results` cell.
    """
    template_dotx_path = Path(template_dotx_path)
    output_docx_path = Path(output_docx_path)

    expected_rows: List[ChecklistRow] = extract_checklist_items_for_class(templates_root, class_name)

    # Build helper mappings for duplicates:
    expected_slugs_by_item_label: Dict[str, List[str]] = defaultdict(list)
    expected_slugs_by_base: Dict[str, List[str]] = defaultdict(list)
    for r in expected_rows:
        expected_slugs_by_item_label[r.item_label].append(r.label_slug)
        expected_slugs_by_base[slugify_label_base(r.item_label)].append(r.label_slug)

    # Load template docx/dotx as zip, modify document.xml.
    doc_xml_name = "word/document.xml"
    file_data: Dict[str, bytes] = {}

    with zipfile.ZipFile(template_dotx_path, "r") as zin:
        # Read all parts first so we can write a consistent output zip.
        for name in zin.namelist():
            file_data[name] = zin.read(name)
        if doc_xml_name not in file_data:
            # Sometimes document.xml path includes directories; find it.
            candidates = [n for n in zin.namelist() if n.endswith(doc_xml_name)]
            if not candidates:
                raise FileNotFoundError(f"Could not find {doc_xml_name} inside {template_dotx_path}")
            doc_xml_name = candidates[0]

    doc_xml_bytes = file_data[doc_xml_name]
    doc_root = ET.fromstring(doc_xml_bytes)
    w_ns = _get_w_namespace(doc_root)

    # Fill inspection report detail fields (client/owner/raeq/etc.) before checklist rows.
    if fields:
        _fill_checklist_report_details(doc_root, w_ns, fields)
        _fill_basket_information(doc_root, w_ns, fields)

    _, header_i, item_col, results_col = _find_checklist_table_and_columns(doc_root)

    # Prepare counters for duplicates.
    seen_item_label_counts: Dict[str, int] = defaultdict(int)
    seen_base_counts: Dict[str, int] = defaultdict(int)

    # Iterate rows and write results.
    for tbl in doc_root.iter():
        if _local_name(tbl.tag) != "tbl":
            continue
        rows = [tr for tr in tbl.iter() if _local_name(tr.tag) == "tr"]
        if not rows:
            continue
        # Re-check that this is the same table by header match.
        # (We already found the header positions, but tbl scope helps avoid false positives.)
        # Find the table with matching header row at index header_i by locating the header keywords.
        if header_i < 0 or header_i >= len(rows):
            continue
        # quick check: do header row cells include 'Item'?
        header_tr = rows[header_i]
        header_tcs = [tc for tc in header_tr if _local_name(tc.tag) == "tc"]
        header_cells = [_cell_text(tc) for tc in header_tcs]
        joined = " | ".join(header_cells).lower()
        if not ("item" in joined and "type of inspection" in joined and "result" in joined and "comments" in joined):
            continue

        # Now fill each data row after header_i.
        if class_name == GENERAL_CLASS_NAME:
            # General template: Item/Type cells are blank; map by row order to manifest slugs.
            data_row_idx = 0
            for tr in rows[header_i + 1 :]:
                if data_row_idx >= len(expected_rows):
                    break
                row_cols = _row_value_containers(tr)
                if len(row_cols) <= max(item_col, results_col):
                    continue
                item_text = _cell_text(row_cols[item_col])
                if item_text.strip().lower() == "item":
                    continue
                slug = expected_rows[data_row_idx].label_slug
                data_row_idx += 1
                result = results_by_label_slug.get(slug)
                if not result:
                    continue
                results_cell = row_cols[results_col]
                _set_container_text(results_cell, w_ns, result)
        else:
            for tr in rows[header_i + 1 :]:
                row_cols = _row_value_containers(tr)
                if len(row_cols) <= max(item_col, results_col):
                    continue
                item_text = _cell_text(row_cols[item_col])
                if not item_text:
                    continue
                # Skip if this row is actually the repeated "Item" header.
                if item_text.strip().lower() == "item":
                    continue

                label_slug_list = expected_slugs_by_item_label.get(item_text)
                if label_slug_list:
                    i = seen_item_label_counts[item_text]
                    chosen_slug = label_slug_list[i] if i < len(label_slug_list) else label_slug_list[-1]
                    seen_item_label_counts[item_text] += 1
                else:
                    base = slugify_label_base(item_text)
                    base_list = expected_slugs_by_base.get(base, [])
                    j = seen_base_counts[base]
                    chosen_slug = base_list[j] if j < len(base_list) else (base_list[-1] if base_list else None)
                    seen_base_counts[base] += 1

                if not chosen_slug:
                    continue
                result = results_by_label_slug.get(chosen_slug)
                if not result:
                    continue

                results_cell = row_cols[results_col]
                _set_container_text(results_cell, w_ns, result)

        break

    # Serialize back.
    file_data[doc_xml_name] = ET.tostring(doc_root, encoding="utf-8", xml_declaration=True)

    # Fill header Equipment field with assigned RAEQ.
    if fields:
        for part_name in list(file_data.keys()):
            if not part_name.startswith("word/header") or not part_name.endswith(".xml"):
                continue
            header_root = ET.fromstring(file_data[part_name])
            header_ns = _get_w_namespace(header_root)
            _fill_checklist_header_equipment(header_root, header_ns, fields)
            file_data[part_name] = ET.tostring(header_root, encoding="utf-8", xml_declaration=True)

    # Convert package main content type from template->document so downstream docx tools
    # (and Word) treat output as a true .docx.
    ct_name = "[Content_Types].xml"
    if ct_name in file_data:
        ct_xml = file_data[ct_name].decode("utf-8", "ignore")
        ct_xml = ct_xml.replace(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        )
        file_data[ct_name] = ct_xml.encode("utf-8")

    # Write output zip.
    output_docx_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx_path, "w") as zout:
        for name, data in file_data.items():
            # Use same relative paths inside the zip.
            zout.writestr(name, data)

