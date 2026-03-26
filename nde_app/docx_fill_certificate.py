import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple, Union


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _detect_word_ns(root: ET.Element) -> str:
    if "}" in root.tag:
        return root.tag.split("}")[0].strip("{")
    # Fallback to WordprocessingML namespace
    return "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _w(ns: str, local: str) -> str:
    return f"{{{ns}}}{local}"


def _parse_input_date(value: Union[str, datetime]) -> datetime:
    if isinstance(value, datetime):
        return value
    s = (value or "").strip()
    # Accept common formats found in your workflow
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
    # The templates use placeholders like:
    # - "Month DD, YYYY"
    # - "Month DD YYYY"
    ph = (placeholder_text or "").strip().lower()
    has_comma = "," in ph or "month dd," in ph
    if has_comma:
        return dt.strftime("%B %d, %Y")
    return dt.strftime("%B %d %Y")


def _find_placeholder_text_in_sdt(sdt_elem: ET.Element, w_ns: str) -> Optional[str]:
    # Look for the first w:t inside sdtContent.
    for t in sdt_elem.iter(_w(w_ns, "t")):
        if t.text and t.text.strip():
            return t.text
    return None


def _find_placeholder_text_in_any(elem: ET.Element, w_ns: str) -> Optional[str]:
    for t in elem.iter(_w(w_ns, "t")):
        if t.text and t.text.strip():
            return t.text
    return None


def _set_sdt_text_value(sdt_elem: ET.Element, w_ns: str, value_text: str) -> None:
    def _set_run_black(run_elem: ET.Element) -> None:
        rpr = run_elem.find(_w(w_ns, "rPr"))
        if rpr is None:
            rpr = ET.SubElement(run_elem, _w(w_ns, "rPr"))
        color = rpr.find(_w(w_ns, "color"))
        if color is None:
            color = ET.SubElement(rpr, _w(w_ns, "color"))
        color.set(_w(w_ns, "val"), "000000")

    # Replace the first non-empty w:t inside sdtContent, or insert a new one.
    t_nodes = [t for t in sdt_elem.iter(_w(w_ns, "t")) if (t.text is not None and t.text.strip() != "")]
    if not t_nodes:
        # Fall back: insert inside sdtContent (as a simple paragraph/run/text).
        sdt_content = None
        for el in sdt_elem.iter():
            if _local_name(el.tag) == "sdtContent":
                sdt_content = el
                break
        if sdt_content is None:
            raise ValueError("Could not locate sdtContent to write value.")
        p = ET.SubElement(sdt_content, _w(w_ns, "p"))
        r = ET.SubElement(p, _w(w_ns, "r"))
        _set_run_black(r)
        t = ET.SubElement(r, _w(w_ns, "t"))
        t.text = value_text
        return

    # Replace all non-empty w:t nodes to be safe (some templates split runs).
    parent_map = {c: p for p in sdt_elem.iter() for c in p}
    for t in t_nodes:
        t.text = value_text
        run = parent_map.get(t)
        if run is not None:
            _set_run_black(run)


def _set_sdt_date_value(sdt_elem: ET.Element, w_ns: str, dt: datetime, placeholder_text: str) -> None:
    # Update the mapped date fullDate if present.
    date_elem = None
    for el in sdt_elem.iter(_w(w_ns, "date")):
        date_elem = el
        break
    if date_elem is not None:
        # Attribute is in the WordprocessingML namespace, commonly as {w}fullDate.
        date_elem.set(_w(w_ns, "fullDate"), dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    # Also update displayed placeholder text (w:t).
    formatted = _format_date_for_placeholder(dt, placeholder_text)
    _set_sdt_text_value(sdt_elem, w_ns, formatted)


def _set_tc_text_value(tc_elem: ET.Element, w_ns: str, value_text: str) -> None:
    def _set_run_black(run_elem: ET.Element) -> None:
        rpr = run_elem.find(_w(w_ns, "rPr"))
        if rpr is None:
            rpr = ET.SubElement(run_elem, _w(w_ns, "rPr"))
        color = rpr.find(_w(w_ns, "color"))
        if color is None:
            color = ET.SubElement(rpr, _w(w_ns, "color"))
        color.set(_w(w_ns, "val"), "000000")

    # Replace all non-empty w:t nodes in the cell.
    t_nodes = [t for t in tc_elem.iter(_w(w_ns, "t")) if t.text is not None and t.text.strip() != ""]
    if not t_nodes:
        # Insert minimal paragraph/run/text.
        p = ET.SubElement(tc_elem, _w(w_ns, "p"))
        r = ET.SubElement(p, _w(w_ns, "r"))
        _set_run_black(r)
        t = ET.SubElement(r, _w(w_ns, "t"))
        t.text = value_text
        return
    parent_map = {c: p for p in tc_elem.iter() for c in p}
    t_nodes[0].text = value_text
    run = parent_map.get(t_nodes[0])
    if run is not None:
        _set_run_black(run)
    for t in t_nodes[1:]:
        t.text = ""


@dataclass(frozen=True)
class CertificateField:
    label: str
    value_key: str  # key in fields dict


DEFAULT_FIELDS = [
    CertificateField(label="CLIENT:", value_key="client_name"),
    CertificateField(label="RAE NO.:", value_key="raeq"),
    CertificateField(label="EQUIPMENT TYPE:", value_key="equip_type"),
    CertificateField(label="INSPECTION DATE:", value_key="inspection_date"),
    CertificateField(label="EXPIRY DATE:", value_key="expiry_date"),
    CertificateField(label="MANUFACTURER:", value_key="manufacturer"),
    CertificateField(label="MODEL:", value_key="model"),
    CertificateField(label="SERIAL NO.:", value_key="serial_no"),
    CertificateField(label="UNIT NO.:", value_key="client_unit_id"),
    CertificateField(label="INSPECTOR:", value_key="inspector_name"),
    CertificateField(label="ENGINEER(S):", value_key="engineer_name"),
]


def _find_label_cell_and_value_sdt(
    root: ET.Element,
    w_ns: str,
    label_text: str,
) -> Tuple[ET.Element, ET.Element]:
    """
    Returns: (label_tc, value_sdt_element)
    Finds a w:tr row where a w:t equals label_text, then selects the next w:tc cell
    that contains a w:sdt and returns its first w:sdt.
    """
    label_text = label_text.strip()

    # Iterate table rows.
    # Note: in these templates, the adjacent value can be a direct child `<w:sdt>` of the row,
    # not wrapped in a `<w:tc>`. So we search by row children order.
    for tr in root.iter(_w(w_ns, "tr")):
        children = list(tr)

        label_child = None
        label_child_idx = None

        for i, child in enumerate(children):
            if _local_name(child.tag) != "tc":
                continue
            for t in child.iter(_w(w_ns, "t")):
                if t.text and t.text.strip() == label_text:
                    label_child = child
                    label_child_idx = i
                    break
            if label_child_idx is not None:
                break

        if label_child_idx is None:
            continue

        # Search forward among direct row children:
        # Some fields are stored in a direct sibling `<w:sdt>`, others store the placeholder text
        # directly in the next `<w:tc>` (without an enclosing sdt).
        for j in range(label_child_idx + 1, len(children)):
            ln = _local_name(children[j].tag)
            if ln == "sdt":
                return label_child, children[j]
            if ln == "tc":
                # Return the first table cell with non-empty placeholder text.
                first_t = None
                for t in children[j].iter(_w(w_ns, "t")):
                    if t.text and t.text.strip():
                        first_t = t.text.strip()
                        break
                if first_t:
                    return label_child, children[j]

        # Fallback: find any sdt later within the row.
        sdt_elems = list(tr.iter(_w(w_ns, "sdt")))
        if sdt_elems:
            return label_child, sdt_elems[0]

    raise ValueError(f"Could not find label '{label_text}' with a value element.")


def fill_certificate_dotx(
    template_dotx_path: Union[str, Path],
    output_docx_path: Union[str, Path],
    *,
    fields: Dict[str, str],
    templates_root: Optional[Union[str, Path]] = None,
) -> None:
    """
    Fill an EC-1210D certificate `.dotx` by label -> adjacent content control mapping.
    Writes a `.docx` (OpenXML package) as an output zip (same structure as input).
    """
    template_dotx_path = Path(template_dotx_path)
    output_docx_path = Path(output_docx_path)

    # Read & modify document.xml inside the .dotx package.
    with zipfile.ZipFile(template_dotx_path, "r") as zin:
        file_data: Dict[str, bytes] = {n: zin.read(n) for n in zin.namelist()}
        doc_xml_name = next((n for n in zin.namelist() if n.endswith("word/document.xml")), None)
        if not doc_xml_name:
            raise FileNotFoundError("word/document.xml not found in template.")

    doc_root = ET.fromstring(file_data[doc_xml_name])
    w_ns = _detect_word_ns(doc_root)

    # Fill known fields by label.
    for field in DEFAULT_FIELDS:
        if field.value_key not in fields:
            continue
        value = fields[field.value_key]
        label = field.label

        _label_tc, value_elem = _find_label_cell_and_value_sdt(doc_root, w_ns, label)
        value_kind = _local_name(value_elem.tag)

        placeholder_text = _find_placeholder_text_in_any(value_elem, w_ns) or ""

        if field.value_key in ("inspection_date", "expiry_date"):
            dt = _parse_input_date(value)
            if value_kind == "sdt":
                _set_sdt_date_value(value_elem, w_ns, dt, placeholder_text)
            else:
                formatted = _format_date_for_placeholder(dt, placeholder_text)
                _set_tc_text_value(value_elem, w_ns, formatted)
        else:
            value_text = str(value).strip()
            if value_text == "":
                value_text = "-"
            if value_kind == "sdt":
                _set_sdt_text_value(value_elem, w_ns, value_text)
            else:
                _set_tc_text_value(value_elem, w_ns, value_text)

    file_data[doc_xml_name] = ET.tostring(doc_root, encoding="utf-8", xml_declaration=True)

    # Convert package main content type from template->document for .docx consumers.
    ct_name = "[Content_Types].xml"
    if ct_name in file_data:
        ct_xml = file_data[ct_name].decode("utf-8", "ignore")
        ct_xml = ct_xml.replace(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
        )
        file_data[ct_name] = ct_xml.encode("utf-8")

    # Write output.
    output_docx_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_docx_path, "w") as zout:
        for name, data in file_data.items():
            zout.writestr(name, data)

