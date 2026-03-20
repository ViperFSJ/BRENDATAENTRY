import os
import re
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Sequence, Union


def insert_photos_into_checklist_figures(
    checklist_docx_path: Union[str, Path],
    photo_paths: Sequence[Union[str, Path]],
) -> int:
    """
    Insert photos into picture placeholders in checklist by rewriting OpenXML image
    relationship targets (`a:blip r:embed` + `word/_rels/document.xml.rels`).

    This template stores figure boxes as drawing placeholders; text labels like
    "Figure 1:" are not always present as plain paragraph text, so XML-level replacement
    is more reliable than paragraph scanning.

    Returns number of images inserted.
    """
    checklist_docx_path = Path(checklist_docx_path)
    photos = [Path(p) for p in photo_paths if str(p).strip() != ""]
    if not photos:
        return 0

    with zipfile.ZipFile(checklist_docx_path, "r") as zin:
        file_data = {n: zin.read(n) for n in zin.namelist()}

    doc_xml_name = "word/document.xml"
    rels_xml_name = "word/_rels/document.xml.rels"
    if doc_xml_name not in file_data or rels_xml_name not in file_data:
        return 0

    doc_xml_bytes = file_data[doc_xml_name]
    rels_xml_bytes = file_data[rels_xml_name]

    # Preserve existing namespace prefixes when writing XML back.
    # Some Office parsers are sensitive to relationship/document namespace prefix rewrites.
    for event, (prefix, uri) in ET.iterparse(BytesIO(doc_xml_bytes), events=("start-ns",)):
        p = prefix or ""
        # ElementTree does not allow registration of internal-style prefixes (ns0, ns1, ...).
        if not re.fullmatch(r"ns\d+", p):
            ET.register_namespace(p, uri)
    for event, (prefix, uri) in ET.iterparse(BytesIO(rels_xml_bytes), events=("start-ns",)):
        p = prefix or ""
        if not re.fullmatch(r"ns\d+", p):
            ET.register_namespace(p, uri)

    doc_root = ET.fromstring(doc_xml_bytes)
    rels_root = ET.fromstring(rels_xml_bytes)

    # Namespace helpers
    doc_ns = doc_root.tag.split("}")[0].strip("{") if "}" in doc_root.tag else ""
    rel_ns = rels_root.tag.split("}")[0].strip("{") if "}" in rels_root.tag else ""

    def local(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    # Find all drawing image refs (blips) in appearance order.
    blips = [e for e in doc_root.iter() if local(e.tag) == "blip"]
    if not blips:
        return 0

    # Choose how many placeholders to fill.
    n_fill = min(len(blips), len(photos))
    if n_fill == 0:
        return 0

    # Build existing relationship id set.
    rel_elems = [e for e in rels_root.iter() if local(e.tag) == "Relationship"]
    existing_ids = {e.attrib.get("Id", "") for e in rel_elems}

    # Determine attribute key for embed (namespace-qualified in ElementTree).
    embed_attr_key = None
    if blips and blips[0].attrib:
        for k in blips[0].attrib.keys():
            if k.endswith("}embed") or k == "r:embed" or k == "embed":
                embed_attr_key = k
                break
    if embed_attr_key is None:
        # fallback common key
        embed_attr_key = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"

    # Determine image relationship type (constant for Office image rels).
    image_rel_type = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"

    inserted = 0
    # First image can reuse first existing rel/media target of first blip.
    # Additional images get new rels + media files.
    for i in range(n_fill):
        photo = photos[i]
        if not photo.exists():
            continue

        blip = blips[i]
        old_rid = blip.attrib.get(embed_attr_key, "")

        if i == 0 and old_rid:
            # Reuse existing relationship target file for first photo.
            # Find target media file for old rid.
            target = None
            for r in rel_elems:
                if r.attrib.get("Id") == old_rid:
                    target = r.attrib.get("Target")
                    break
            if target:
                media_name = "word/" + target.replace("\\", "/").lstrip("/")
                file_data[media_name] = photo.read_bytes()
                inserted += 1
                continue

        # Create new media part and relationship
        ext = photo.suffix.lower().lstrip(".") or "png"
        media_name = f"word/media/figure_auto_{i+1}.{ext}"
        file_data[media_name] = photo.read_bytes()

        # New relationship id
        rid = f"rIdAutoPhoto{i+1}"
        k = 1
        while rid in existing_ids:
            k += 1
            rid = f"rIdAutoPhoto{i+1}_{k}"
        existing_ids.add(rid)

        rel_tag = f"{{{rel_ns}}}Relationship" if rel_ns else "Relationship"
        rel_elem = ET.SubElement(rels_root, rel_tag)
        rel_elem.set("Id", rid)
        rel_elem.set("Type", image_rel_type)
        rel_elem.set("Target", f"media/{Path(media_name).name}")

        # Point this blip to new rel id.
        blip.attrib[embed_attr_key] = rid
        inserted += 1

    # Serialize updated XMLs
    file_data[doc_xml_name] = ET.tostring(doc_root, encoding="utf-8", xml_declaration=True)
    file_data[rels_xml_name] = ET.tostring(rels_root, encoding="utf-8", xml_declaration=True)

    with zipfile.ZipFile(checklist_docx_path, "w") as zout:
        for name, data in file_data.items():
            zout.writestr(name, data)

    return inserted

